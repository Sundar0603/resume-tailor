# Task 011 — Resume Planner

## Context

The pipeline today ends at two independent structures: `ResumeParser` produces a
`Resume`, `JDAnalyzer` produces a `JobAnalysis`. Nothing yet decides how one should
be reshaped to fit the other.

Rather than hand an LLM a whole resume and ask for a rewrite, this task splits the
work in two: **plan**, then **execute**. The planner reads the resume and the job
analysis and emits a `ResumePlan` — a structured set of decisions saying _what_
should change and _why_, referencing every resume entity by id. It never writes a
word of resume prose. A later task's Resume Generator executes the plan.

The payoff is explainability and testability: every decision carries a `reasoning`
field, every plan is validated against the real resume before it is trusted, and
the prompt can be tuned against a plan that is small enough to read.

Target runtime is a local Ollama model. The end goal is one command in, tailored
resume out, inside three minutes. This task's CLI command is a debug view of the
middle stage, shaped to slot into that eventual command.

## Decisions taken (resolved with user before planning)

| Question                                       | Decision                                                                                                                                        |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `GENERATE` project has no id                   | `project_id: Optional[str]` + `generation_brief`; validator enforces the pairing                                                                |
| `highlights_to_emphasize` semantics            | Free-text **themes**, renamed `themes_to_emphasize`, on **both** experience and project plans (spec omitted it from `ProjectPlan` — a spec bug) |
| Where an added skill goes                      | Skills are planned **per category**, parallel to projects — supersedes the flat `skills_to_add: List[str]` in the spec                          |
| Legal actions per section                      | Summary `KEEP/REWRITE`; Experience `KEEP/REWRITE`; Projects and Skill categories all four                                                       |
| CLI input                                      | `resume-tailor plan --resume <path> --jd <path> [--mode]`. No stdin, no caching flags                                                           |
| Skill removal naming a skill not in the resume | Drop the entry and note it in the printed output; do **not** fail the run                                                                       |

## Scope

New package `src/planner/` mirroring `src/analyzer/` exactly, plus one CLI command.
Out of scope per the task file: generation, markdown, LaTeX, PDF, quality gate,
revision engine.

---

## Files

### `src/planner/exceptions.py` (new)

Flat hierarchy in the style of `src/analyzer/exceptions.py` — docstring-only bodies,
no custom `__init__`.

```
PlannerError
├── InvalidPlannerResponse      empty / unexpected provider response
├── InvalidPlannerJSON          response not parseable as JSON
├── ResumePlanValidationError   failed Pydantic schema validation
├── UnknownPlanningMode         caller passed a mode that does not exist
└── PlanConsistencyError        schema-valid but inconsistent with the resume
    ├── UnknownEntityReference
    ├── DuplicatePlanEntry
    ├── MissingPlanEntry
    ├── ImmutableSectionViolation
    └── PlanningModeViolation
```

The fourth level is what the analyzer doesn't need — it has no external referent to
check the LLM's output against; the planner has the `Resume`.

### `src/planner/models.py` (new)

Every model carries `model_config = ConfigDict(extra="forbid", validate_assignment=True)`.
Python 3.9 — `typing.List/Optional`, mutable defaults as bare `[]`.

```python
class PlanAction(str, Enum):      KEEP, REWRITE, REMOVE, GENERATE      # UPPER = "UPPER"
class PlanningMode(str, Enum):    AGGRESSIVE, STRICT                   # + .parse() classmethod, AGGRESSIVE default
class SectionPriority(IntEnum):   CRITICAL=1, HIGH=2, MEDIUM=3, LOW=4
```

Allowed-action sets as module constants, enforced by a `field_validator` on `action`
that names the section in the error:

```python
SUMMARY_ACTIONS         = {KEEP, REWRITE}
EXPERIENCE_ACTIONS      = {KEEP, REWRITE}
PROJECT_ACTIONS         = {KEEP, REWRITE, REMOVE, GENERATE}
SKILL_CATEGORY_ACTIONS  = {KEEP, REWRITE, REMOVE, GENERATE}
```

Models:

```python
class SummaryPlan:
    action, priority, reasoning, keywords_to_include: List[str] = []

class SkillCategoryPlan:
    category_id: Optional[str] = None       # None iff GENERATE
    action, priority
    new_category_name: Optional[str] = None # required on GENERATE,
                                            # optional rename on REWRITE
    skills_to_add:    List[str] = []        # non-empty on GENERATE
    skills_to_remove: List[str] = []
    reasoning

class ExperiencePlan:
    experience_id: str
    action, priority
    rewrite_strategy: Optional[str] = None
    keywords_to_include:  List[str] = []
    themes_to_emphasize:  List[str] = []
    reasoning

class ProjectPlan:
    project_id: Optional[str] = None        # None iff GENERATE
    action, priority
    rewrite_strategy:  Optional[str] = None
    generation_brief:  Optional[str] = None # GENERATE only
    keywords_to_include: List[str] = []
    themes_to_emphasize: List[str] = []
    reasoning

class ResumePlan:
    mode: PlanningMode = AGGRESSIVE         # injected by the planner, not requested from the LLM
    summary_plan:     SummaryPlan
    skills_plans:     List[SkillCategoryPlan] = []
    experience_plans: List[ExperiencePlan]   = []
    project_plans:    List[ProjectPlan]      = []
```

**`SectionPriority` is an `IntEnum`, so `SectionPriority("CRITICAL")` fails.** Every
plan model needs a `@field_validator("priority", mode="before")` mapping member names
to values and passing anything else through untouched so Pydantic reports the real
error. `canonical.py` normalizes first; this validator is the backstop. This is the
single likeliest implementation slip in the module.

Model-level validators (raise `ValidationError` → wrapped as `ResumePlanValidationError`):

- `GENERATE` ⇒ id is `None` **and** the brief/name field is non-empty; any other action
  ⇒ id non-empty **and** brief/name is `None`.
- `REWRITE` ⇒ `rewrite_strategy` non-empty; `KEEP`/`REMOVE` ⇒ it is `None`.

`ResumePlan` has no `education_plan`/`contact_plan`/`metadata` field, so `extra="forbid"`
rejects them — but `planner.py` pre-checks for those keys so the error is the specific
`ImmutableSectionViolation`, not a generic schema failure.

### `src/planner/prompts.py` (new)

Follows `src/analyzer/prompts.py`: one module-private template constant, one pure
builder. Sections in order: role → task → planning rules → mode block → prohibitions
→ consistency rules → JSON schema skeleton → field definitions → tagged inputs →
closing `Return ONLY the JSON object.`

```python
def build_planning_prompt(resume, job_analysis, mode=PlanningMode.AGGRESSIVE) -> str
def _resume_projection(resume) -> Dict[str, Any]   # private
```

`_resume_projection` sends **only**: `summary`; per skill category `id/category/skills`;
per experience `id/company/role/duration/technologies/domains/highlights`; per project
`id/name/type/technologies/highlights`. Deliberately excluded: `contact` and `metadata`
(PII, irrelevant), `education` (immutable — sending it invites the model to plan against
it), `source`, `employment_type`, `location`, `repository`. Smaller prompt, faster on
Ollama, no personal data leaving the machine.

Serialized with `json.dumps(..., indent=2, ensure_ascii=False)` (dict-literal key order
is stable) and `job_analysis.model_dump_json(indent=2)`.

Since `str.format` is used, **every literal brace in the schema skeleton must be doubled**
(`{{`/`}}`), as in `src/analyzer/prompts.py:43`. Only `{mode}`, `{mode_rules}`, `{resume}`,
`{job_analysis}` stay single. Substituted values are not rescanned, so their braces are safe.

Two mode blocks as constants: aggressive lists what is permitted; strict states that
`GENERATE` is forbidden anywhere and that nothing may require inventing metrics,
employers, projects, or responsibilities.

### `src/planner/canonical.py` (new)

Warranted for the same reason as `src/analyzer/canonical.py` — pinned sampling makes
output stable, not _comparable_ — and here it is additionally load-bearing for
correctness, since `IntEnum` cannot ingest `"CRITICAL"`. Same contract: returns a new
dict, never mutates input, touches only recognised keys, passes unexpected types
through, idempotent.

Normalizes: action casing (+ a _small_, documented alias map — over-forgiving aliases
hide prompt failures); priority names/`"P1"`/`"1"`/`1` → int; `""`/`"null"`/`"N/A"` →
`None` on the optional scalars; prose fields (`reasoning`, `rewrite_strategy`,
`generation_brief`) via NFKC + whitespace collapse + quote strip, **keeping** terminal
periods since these are sentences; `keywords_to_include`/`themes_to_emphasize`/
`skills_to_add`/`skills_to_remove` cleaned, deduped case-insensitively, sorted;
`experience_plans` sorted by id, `project_plans`/`skills_plans` sorted with `GENERATE`
entries (null id) last.

Reuses `canonical_text` from `src/analyzer/canonical.py` rather than reimplementing it.

### `src/planner/planner.py` (new)

```python
PLANNER_NUM_CTX = 16384      # resume + analysis + ~90-line schema; 8192 would truncate
PLANNER_MAX_TOKENS = 8192

def planner_options() -> Dict[str, Any]:
    return deterministic_options(num_ctx=PLANNER_NUM_CTX, max_tokens=PLANNER_MAX_TOKENS)

class ResumePlanner:
    def __init__(self, provider: LLMProvider) -> None: ...
    def plan(self, resume, job_analysis, mode=PlanningMode.AGGRESSIVE) -> ResumePlan:
        resolved = PlanningMode.parse(mode)                    # accepts "strict", "STRICT", enum
        prompt   = build_planning_prompt(resume, job_analysis, resolved)
        raw      = self._invoke_provider(prompt)
        data     = canonicalize(self._parse_json(raw))
        self._reject_immutable_sections(data)
        plan     = self._validate(data, resolved)
        self._validate_against_resume(plan, resume, resolved)
        return plan
```

`_invoke_provider` / `_parse_json` / `_validate` mirror `src/analyzer/analyzer.py:104-156`
line for line with planner exceptions substituted — including the
`except PlannerError: raise` / `except Exception: raise PlannerError(...) from exc`
funnel. No retry loop; the analyzer has none and determinism comes from pinned sampling.
`_validate` sets `data["mode"] = resolved.value` unconditionally so a hallucinated mode
cannot survive.

Stateless, reusable across calls, and must never mutate the `Resume`.

Reused as-is, not copied: `LLMProvider` (`src/analyzer/provider.py:20`),
`extract_json_object` (`src/analyzer/_json_extract.py:20`), `deterministic_options`
(`src/analyzer/sampling.py:63`).

### `src/planner/__init__.py` (new)

Docstring with a `Public API::` block, relative imports sorted by module, explicit
`__all__` ordered semantically — matching `src/analyzer/__init__.py`.

### `src/cli/plan.py` (new) + one line in `src/cli/main.py`

```
resume-tailor plan --resume content/x.md --jd job.md [--mode aggressive|strict]
```

Flow: `_print_header` → config guard (`resume-tailor doctor` hint, as `analyze` does)
→ `PlanningMode.parse` → `ResumeParser().parse(resume)` → read JD file →
`ProviderFactory.create` → `JDAnalyzer.analyze` → `ResumePlanner.plan` → `_pretty_print`.

Printer helpers copy `src/cli/analyze.py:48-65` (`_print_header`, `_print_section`,
`_print_list`) plus `_print_field` and `_print_divider`. `_pretty_print(plan, resume)`
takes the resume to resolve ids to labels — experience blocks titled by company, project
blocks by name (or `New project` for `GENERATE`), skill blocks by category. Prints
`action.value` and `priority.name` (`.name` is why `IntEnum` still shows `CRITICAL`).
`Mode:` printed once under the header. Any skill removals discarded during validation
are listed under a `Discarded:` label.

**The `ResumePlan` is never written to disk.** Register with `app.command("plan")(plan)`
in `src/cli/main.py:40`, alongside `doctor` and `analyze`.

Error ladder copies `analyze`'s ordering (`AuthenticationError` → `ConnectionError` →
`RateLimitError` → `ProviderResponseError` → `ProviderError`) with the planner leg
prepended: `InvalidPlannerResponse`, `InvalidPlannerJSON`, `ResumePlanValidationError`,
`PlanConsistencyError`, `PlannerError`.

---

## Validation ruleset → exception

Evaluated in this order; every message names the offending id.

| #     | Rule                                                                                                              | Raises                                 |
| ----- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| 1     | Empty / whitespace-only provider response                                                                         | `InvalidPlannerResponse`               |
| 2     | Provider raises any non-`PlannerError`                                                                            | `PlannerError` (chained)               |
| 3     | No parseable JSON object in the response                                                                          | `InvalidPlannerJSON`                   |
| 4     | Top-level `education_plan` / `contact_plan` / `metadata` etc.                                                     | `ImmutableSectionViolation`            |
| 5     | Any other unknown key (`extra="forbid"`)                                                                          | `ResumePlanValidationError`            |
| 6     | `summary_plan` absent                                                                                             | `ResumePlanValidationError`            |
| 7     | `priority` absent, null, or unrecognised                                                                          | `ResumePlanValidationError`            |
| 8     | `action` not a `PlanAction` member                                                                                | `ResumePlanValidationError`            |
| 9     | `action` illegal for that section (e.g. `REMOVE` on summary or experience)                                        | `ResumePlanValidationError`            |
| 10    | `reasoning` missing or empty                                                                                      | `ResumePlanValidationError`            |
| 11    | `REWRITE` without strategy, or `KEEP`/`REMOVE` with one                                                           | `ResumePlanValidationError`            |
| 12    | `GENERATE` with a non-null id, or missing its brief / category name                                               | `ResumePlanValidationError`            |
| 13    | Non-`GENERATE` plan with a null id                                                                                | `ResumePlanValidationError`            |
| 14–15 | Duplicate `experience_id`, `project_id`, or `category_id`                                                         | `DuplicatePlanEntry`                   |
| 16–17 | Id not present in the resume                                                                                      | `UnknownEntityReference`               |
| 18–20 | A resume experience / project / skill category received no plan (`GENERATE` plans excluded from the covering set) | `MissingPlanEntry`                     |
| 21    | `skills_to_remove` names a skill absent from that category                                                        | **none** — dropped, reported in output |
| 22    | Same skill in both `skills_to_add` and `skills_to_remove` of one category                                         | `PlanConsistencyError`                 |
| 23    | `mode == STRICT` and any plan action is `GENERATE`                                                                | `PlanningModeViolation`                |
| 24    | `GENERATE` skill category with an empty `skills_to_add` *(added in task 012)*                                     | `ResumePlanValidationError`            |
| 25    | `KEEP` / `REMOVE` skill category setting `new_category_name` *(added in task 012; `REWRITE` may now rename)*      | `ResumePlanValidationError`            |
| 26    | `mode == STRICT` and `skills_to_add` names a skill absent from the whole resume *(added in task 012)*             | **none** — dropped, reported in output |
| 27    | `skills_to_add` names an activity or is too general — both modes *(added in task 012)*                            | **none** — dropped, reported in output |

> **Rule 27, added in task 012.** A live run produced skill categories full of
> job-description prose: "Interoperability Strategies", "Defect Handling",
> "Code Quality", "Optimization of Coding", "SDLC". The planner prompt now
> forbids this and lists those exact strings as negative examples — and
> qwen3.6 emitted several of them anyway, which is why the rule is also
> enforced in Python (`_looks_like_an_activity`). The heuristic is
> deliberately conservative: a multi-word phrase whose head noun names an
> activity is dropped, and words that could head a real skill
> ("architecture", "testing", "design", "services") are left out of the
> denylist. It applies only to *additions* — a skill already on the resume is
> the candidate's own wording and is never second-guessed. It never empties a
> `GENERATE` category, which would breach rule 24 and report a confusing
> schema error instead of this one.

> **Amended in task 012.** Rule 12 originally made `new_category_name` a
> `GENERATE`-only field. `REWRITE` may now set it to rename a category so its
> heading matches the language of the job — "Backend" becoming "Backend &
> Distributed Systems". A blank rename is folded to `None` by `canonicalize()`
> and means "keep the name". Rule 24 exists because the Resume Generator
> applies skill categories in pure Python with no LLM call, so an empty
> generated category would reach the rendered resume; the validator only warns
> about one (`EMPTY_SKILL_CATEGORY`).

Notes:

- Rule 21 is the decided-on soft failure. Matching is casefolded and
  whitespace-normalised via `canonical_text`, so only genuine mismatches are dropped.
- `skills_to_add` naming a skill already present is a harmless model tic — filtered
  silently, documented in the docstring.
- Rule 23 is the only _structurally_ checkable strict-mode rule. "No fabricated metrics"
  is unenforceable at the plan layer; it propagates via the prompt's strict block and
  via `ResumePlan.mode` for the future Generator to honour.

---

## Tests — `tests/planner/`

`__init__.py`, `conftest.py`, `test_planner.py` (transport + schema), `test_validation.py`
(semantic), `test_canonical.py`, `test_prompts.py`. No pytest config change needed
(`testpaths = ["tests"]`).

`conftest.py` carries `FakeProvider` / `FailingProvider` in the exact style of
`tests/analyzer/test_analyzer.py:36-59` (subclass the `LLMProvider` ABC — the suite does
not use `unittest.mock` for anything subclassable), plus a `CapturingProvider` recording
prompt and options, and code-built factories `make_resume()` / `make_job_analysis()` /
`make_payload(**overrides)` returning a deep copy each call. No fixture files — negative
tests are then one-line mutations of a valid payload.

`make_resume()` models the real shape: **one company, two roles** (`exp_001` intern,
`exp_002` full-time), two projects, two skill categories, one education entry.

Spec-required cases, one test each: valid plan; unknown experience/project/category id;
`education_plan` rejected; missing / null / unrecognised priority; duplicate ids;
malformed JSON; empty response; unknown field; missing `reasoning`; illegal action per
section; strict forbids `GENERATE`; aggressive allows it.

Beyond the spec: missing plan entries; `GENERATE` id/brief pairing both ways; provider
raising; `mode="strict"` lowercase string accepted; unknown mode → `UnknownPlanningMode`;
**planner does not mutate the resume** (deep-copy, run, assert equality); provider
receives `PLANNER_NUM_CTX`; canonicalize idempotent and non-mutating; prompt contains
`exp_001`/`proj_001` but **not** the contact email, phone, name, or `edu_001`; prompt is
byte-identical across two builds; rendered prompt contains single-brace `"summary_plan": {`
proving the doubling is right.

Assertions use bare `pytest.raises(X)` — the suite never uses `match=`.

---

## Verification

```bash
python -m pytest tests/planner -q          # new suite
python -m pytest -q                        # nothing else regressed
resume-tailor plan --resume content/<your>.md --jd tests/fixtures/job_descriptions/backend.md
resume-tailor plan --resume content/<your>.md --jd tests/fixtures/job_descriptions/backend.md --mode strict
```

Against the real Ollama model, confirm: the plan covers every `exp_*`, `proj_*` and
`skill_*` id; strict produces no `GENERATE`; aggressive may; the printed output resembles
the example in `tasks/011-resume-planner.md:409-481`; nothing is written to disk
(`git status` clean). Time the run — it feeds the three-minute end-to-end budget.

---

## Risks

1. **`IntEnum` priority coercion** — without the `mode="before"` validator every real
   call fails. Note also that `model_dump_json()` renders priority as `1`, not
   `"CRITICAL"`; harmless while the plan is never persisted, a trap if the Generator
   ever round-trips it.
2. **Prompt size vs local context** — realistically 3–6k tokens. `num_ctx=16384` is
   headroom, but some small models cap at 8192 and Ollama silently truncates the _front_
   of the prompt, which is where the planning rules live. If rules get ignored on a small
   model, move the prohibitions block next to the closing line.
3. **`json_mode: True`** (inherited from `deterministic_options`) can make some Ollama
   models emit structurally valid but semantically empty plans — all `KEEP`, all `MEDIUM`.
   If that appears, suspect `json_mode`, not the prompt.
4. **Bullet-level targeting is gone** — free-text themes mean the plan cannot say "rewrite
   highlight #2 of exp_001". If the Generator later needs it, add
   `highlight_indices: List[int]` with a bounds check. Cheap now, expensive after prompt tuning.
5. **Who mints the id for a `GENERATE`d project or skill category** is undecided, as is
   whether they get `source=EntitySource.GENERATED` (the field exists at
   `src/parser/models.py:13` and is currently unused). Leave a note in the docstring for
   the Generator task.
6. **`src/cli/plan.py` duplicates ~60 lines** of provider bootstrap and error ladder from
   `analyze.py`. Accept it here; the third copy is when extraction into
   `src/cli/_common.py` pays — which is also the natural seam for the eventual one-shot command.
7. **No determinism harness for the planner** — `tests/analyzer/test_determinism.py` has
   no counterpart and the spec doesn't ask for one. Natural follow-up task, not smuggled
   into this one.
8. **Spec drift to record**: the task file's `SkillsPlan`, flat `skills_to_add`, and
   `highlights_to_emphasize` are superseded by the decisions above. I will update
   `tasks/011-resume-planner.md` to match what was built.
