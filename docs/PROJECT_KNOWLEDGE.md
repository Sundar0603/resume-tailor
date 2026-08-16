# Project Knowledge

Dense reference for Resume Tailor. Attach this to a new task session instead of
re-exploring the codebase.

Status as of the end of task 013 (Markdown Serializer). Baseline: **736 tests
passing** (636 after task 012). Update this file at the end of each task; do
not rewrite it.

---

## 1. Pipeline and stage status

```
Markdown Resume
  → Resume Parser        ✅ 002, 003, 004
  → Resume Validator     ✅ 005
  → JD Analyzer          ✅ 006, 010
  → Resume Planner       ✅ 011
  → Resume Generator     ✅ 012
  → Markdown Serializer  ✅ 013
  → LaTeX Renderer       ⬜
  → pdflatex Compiler    ⬜
  → Quality Gate         ⬜
  → Revision Engine      ⬜
  → Reporter             ⬜
```

Supporting stages already built: provider config + keyring (007), five providers
+ factory (008), `resume-tailor doctor` (009), `resume-tailor analyze` (010),
`resume-tailor plan` (011).

Budgets from `docs/ARCHITECTURE.md`: typical run 45–90 s, hard max 180 s, max 4
LLM generations, max 3 revisions. Revision order per section: Summary 1,
Projects 2, Skills 3, Experience 4. Education never revised.

**Separation of concerns that must not blur:** the Analyzer extracts, the
Planner decides *what changes and why*, the Generator writes *the words*, the
Renderer produces LaTeX from a frozen template (AI never touches LaTeX), the
Quality Gate judges the compiled PDF.

---

## 2. Domain models — `src/parser/models.py`

Every model is Pydantic v2 with `ConfigDict(extra="forbid", validate_assignment=True)`.
An unexpected key is an error, not a warning.

**Naming traps:**
- The work-experience model is `Experience`, **not** `WorkExperience`.
- `Resume.summary` is a plain `str`. There is **no** `Summary` model.
- The skill-category id prefix is `skill_`, **not** `skillcat_`.

```python
class EntitySource(str, Enum):        # :13
    CANONICAL = "CANONICAL"
    GENERATED = "GENERATED"

class Metadata:                       # :20
    resume: str; template: str; version: str        # all required

class Contact:                        # :31
    name: str; phone: str; email: str; linkedin: str; github: str   # all required

class SkillCategory:                  # :44
    id: str = ""; source: EntitySource = CANONICAL
    category: str                     # required
    skills: List[str] = []
    def skill_count() -> int

class Experience:                     # :60
    id: str = ""; source: EntitySource = CANONICAL
    company: str; role: str; employment_type: str; duration: str   # required
    location: Optional[str] = None
    technologies: List[str] = []; domains: List[str] = []; highlights: List[str] = []
    def word_count() -> int           # words across highlights

class Project:                        # :82
    id: str = ""; source: EntitySource = CANONICAL
    name: str; type: str              # both required
    repository: Optional[str] = None
    technologies: List[str] = []; domains: List[str] = []; highlights: List[str] = []
    def word_count() -> int

class Education:                      # :102
    id: str = ""; source: EntitySource = CANONICAL
    institution: str; degree: str; major: str; duration: str       # required
    cgpa: Optional[str] = None; location: Optional[str] = None

class Resume:                         # :118
    metadata: Metadata; contact: Contact; summary: str             # required
    skills: List[SkillCategory] = []; experiences: List[Experience] = []
    projects: List[Project] = []; education: List[Education] = []
```

`Resume` helpers: `get_skills(category)`, `all_skills()`, `total_skills()`,
`total_experiences()`, `total_projects()`, `total_education()`,
`total_highlights()`, `word_count()`.

`EntitySource.GENERATED` is set only by the Generator, on projects and skill
categories it creates. Everything the Parser produces is `CANONICAL`.

Public re-exports from `src/parser/__init__.py`: `ResumeParser`, all models,
`EntitySource`, `ParserError`.

---

## 3. Entity IDs

Format `{prefix}_{n:03d}`, 1-based, positional. Prefixes: `skill_`, `exp_`,
`proj_`, `edu_`.

Minted through `src/entity_ids.py`, the single home for the convention:

```python
assign_sequential_ids(projects, PROJECT_PREFIX)   # Parser: number positionally
mint_id(PROJECT_PREFIX, existing)                 # Generator: one new id
mint_ids(PROJECT_PREFIX, existing, count)         # Generator: several
```

The Parser calls `assign_sequential_ids` after all section parsers return
(`src/parser/resume_parser.py`); the Generator calls `mint_id` for each entity
it creates.

IDs are **runtime-only**: they never appear in the Markdown source, and they are
regenerated on every parse. They exist so the Planner, Generator, Revision
Engine and Quality Gate can reference entities without matching on prose.

The validator only enforces *non-empty and unique within type* — not the format.

**Trap for anyone minting new ids:** use `max(existing) + 1`, not `count + 1`.
If `proj_001` is removed and a new project is generated, `count + 1` yields
`proj_002`, which already exists.

---

## 4. Validator contract — `src/validation/`

```python
ResumeValidator().validate(*, source_resume: Resume,
                              generated_resume: Resume,
                              mode: str = "STRICT") -> ValidationResult
```

`mode` was added in task 012 and defaults to strict, so any caller that does
not pass one keeps the original behaviour. It relaxes exactly one rule:
experience `role` is immutable in strict and mutable in aggressive. A
`PlanningMode` member may be passed directly — it is a `str` Enum — but the
validation layer deliberately does not import from `src.planner`.

Instance method, keyword-only, stateless, reads no files, mutates nothing.
**It raises nothing.** Every problem comes back inside `ValidationResult`.
`src/validation/exceptions.py` is an empty placeholder.

```python
ValidationIssue(code: ValidationCode, message: str,
                entity_id: Optional[str], field: Optional[str])
ValidationResult(is_valid: bool, errors: [...], warnings: [...], info: [...])
```

`is_valid == (len(errors) == 0)`. `info` is always empty today.

**Constants** (`validator.py:28-38`):

| Constant | Value |
|---|---|
| `_REQUIRED_EXPERIENCE_COUNT` | 2 (exactly) |
| `_MIN_PROJECT_COUNT` | 2 |
| `_MIN_SKILL_CATEGORY_COUNT` | 1 |
| `_MIN_EDUCATION_COUNT` | 1 |
| `_SUMMARY_MIN_WORDS` / `_SUMMARY_MAX_WORDS` | 20 / 120 |
| `_MAX_EXPERIENCE_HIGHLIGHTS` | 8 |
| `_MAX_PROJECT_HIGHLIGHTS` | 6 |

**Errors (hard fail):**

- **Contact** — all five fields present and byte-identical to source.
- **Summary** — non-empty after strip.
- **Skills** — ≥1 category; each needs a non-empty unique id and a non-empty
  `category`; no duplicate skill strings within a category.
- **Experience** — exactly 2; each needs an id, non-empty
  `company`/`role`/`duration`, non-None `technologies`/`domains`, non-empty
  `highlights`. `company`/`role`/`duration` compared **positionally** against
  the source and must match exactly.
- **Projects** — ≥2; each needs an id, a `name`, non-empty `highlights`.
  **Not** compared to source, because projects may be GENERATED.
- **Education** — ≥1; each needs an id, `institution`, `degree`;
  `institution`/`degree`/`major`/`duration` compared **positionally** and must
  match exactly.
- **Runtime IDs** — a second pass re-checks non-empty + unique across
  experiences/projects/education/skills. This duplicates the per-entity checks,
  so a missing id produces **two** errors.
- **Entity sources** — every `source` must be a valid `EntitySource` member.

**Warnings (never affect `is_valid`):** `SUMMARY_TOO_SHORT`,
`SUMMARY_TOO_LONG`, `TOO_MANY_EXPERIENCE_HIGHLIGHTS`,
`TOO_MANY_PROJECT_HIGHLIGHTS`, `EMPTY_SKILL_CATEGORY`.

`ValidationCode` (`src/validation/codes.py`) has 26 members. Never use raw
string literals for codes.

**Positional comparison is the sharpest edge here.** Reordering experiences or
education silently produces `MODIFIED_IMMUTABLE_FIELD` on every field, not a
"reordered" diagnostic.

---

## 5. Analyzer output — `src/analyzer/models.py`

`JobAnalysis` is deliberately flat, with no nested objects and no free-text
field, so it can be compared for determinism:

```python
company: Optional[str] = None
role: str = Field(min_length=1)
seniority: Optional[str] = None
required_skills: List[str]          # required
preferred_skills: List[str] = []
technologies: List[str] = []
domains: List[str] = []
responsibilities: List[str] = []
qualifications: List[str] = []
nice_to_have: List[str] = []
keywords: List[str]                 # required
```

---

## 6. Plan models — `src/planner/models.py`

```python
PlanAction(str, Enum)      = KEEP | REWRITE | REMOVE | GENERATE          # :16
PlanningMode(str, Enum)    = AGGRESSIVE | STRICT                         # :25
SectionPriority(IntEnum)   = CRITICAL=1 HIGH=2 MEDIUM=3 LOW=4            # :53
```

`PlanningMode.parse(value)` (:32) is case-insensitive, strips whitespace, raises
`UnknownPlanningMode`. Use it rather than `PlanningMode(...)`.

**Per-section action allowlists** (:63-82) — enforced by `_validate_action`:

| Section | Allowed |
|---|---|
| `summary_plan` | KEEP, REWRITE |
| `experience_plans` | KEEP, REWRITE |
| `project_plans` | all four |
| `skills_plans` | all four |

An experience can never be added, removed or reordered. Education, contact and
metadata have no plan at all.

```python
SummaryPlan:        action, priority, reasoning, keywords_to_include            # :109
SkillCategoryPlan:  category_id?, action, priority, new_category_name?,
                    skills_to_add, skills_to_remove, reasoning                  # :141
ExperiencePlan:     experience_id, action, priority, rewrite_strategy?,
                    keywords_to_include, themes_to_emphasize, reasoning         # :194
ProjectPlan:        project_id?, action, priority, rewrite_strategy?,
                    generation_brief?, keywords_to_include,
                    themes_to_emphasize, reasoning                              # :246
ResumePlan:         mode, summary_plan, skills_plans,
                    experience_plans, project_plans                             # :311
```

**Pairing invariants**, enforced by `@model_validator(mode="after")`:

- `GENERATE` ⇒ the id field is `None`, and the generate-only field
  (`generation_brief` for projects, `new_category_name` for skills) is
  non-empty.
- Any other action ⇒ the id field is non-empty and the generate-only field is
  `None`.
- `REWRITE` ⇒ `rewrite_strategy` non-empty; any other action ⇒ it must be
  `None`. (Note `SkillCategoryPlan` has **no** `rewrite_strategy`.)

**Guarantees the Generator can rely on** (enforced in `planner.py:207-330`):

- Every resume experience, project and skill category has **exactly one** plan
  entry — total coverage, no duplicates, all ids resolve.
- `skills_to_add ∩ skills_to_remove == ∅`.
- A `skills_to_remove` naming an absent skill is silently dropped and reported
  via `planner.last_discarded` — the Generator sees an already-filtered plan.
- STRICT ⇒ no `GENERATE` anywhere.
- `ResumePlan.mode` is overwritten by the caller's mode after validation
  (`planner.py:172-191`), so a hallucinated mode cannot survive.

The plan is **never persisted to disk**. The eventual one-shot command chains
analyze → plan → generate in memory.

---

## 7. Provider layer

**Interface** — `src/analyzer/provider.py:20` (note: it lives in the analyzer
package, not in `src/providers/`):

```python
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str: ...

    @classmethod
    def required_configuration(cls) -> List[str]: return []
```

One method, returns raw text. There is **no tool/function calling anywhere** —
JSON is requested in the prompt and extracted from the reply.

**Option vocabulary** (documented at `provider.py:41-70`; each provider
translates what it supports and silently ignores the rest): `system_prompt`,
`temperature`, `top_p`, `top_k`, `seed`, `num_ctx`, `json_mode`, `max_tokens`,
`stop_sequences`, `extra_headers`.

There is **no `temperature=` kwarg** on any component. Sampling always travels
as this dict.

**`src/analyzer/sampling.py`:**

```python
DETERMINISTIC_OPTIONS = MappingProxyType({
    "temperature": 0.0, "top_p": 1.0, "top_k": 1, "seed": 42,
    "num_ctx": 8192, "max_tokens": 4096, "json_mode": True,
})
def deterministic_options(**overrides) -> Dict[str, Any]   # fresh mutable copy
```

The planner layers `planner_options()` = `deterministic_options(num_ctx=16384,
max_tokens=8192)` — same greedy knobs, bigger budget.

**Concrete providers** — `src/providers/`: `ollama.py`, `openai.py`,
`anthropic.py`, `gemini.py`, `openrouter.py`, plus `factory.py`
(`ProviderFactory.create(config, credentials)`, `available_providers()`,
`required_fields(provider)`) and `base.py`.

Ollama specifics (`src/providers/ollama.py:78-105`): `json_mode` → `format="json"`,
`max_tokens` → `num_predict`, and a load-bearing `"think": False`.

**Two exception families, both caught by the CLI:**
- `src/providers/base.py`: `ProviderError` → `AuthenticationError`,
  `ConnectionError`, `RateLimitError`, `ProviderResponseError`.
- Per-package trees (see §8).

---

## 8. House conventions

**Package shape.** Each AI component is a package with the same file split:

| File | Contains |
|---|---|
| `exceptions.py` | one `<Package>Error(Exception)` base + flat subclasses, docstring-only bodies |
| `models.py` | Pydantic models and enums only |
| `prompts.py` | prompt construction only — no LLM calls, no parsing, no validation |
| `canonical.py` | deterministic normalisation of the raw parsed JSON |
| `sampling.py` | the option dict for that component |
| `<component>.py` | the orchestrator class |
| `__init__.py` | explicit ordered `__all__` |

`src/analyzer/_json_extract.py` (`extract_json_object`) strips code fences and
finds the first balanced `{...}`. It is private by name but **reused by the
planner** — reuse it, don't reimplement.

**Exception trees:**
```
PlannerError → InvalidPlannerResponse, InvalidPlannerJSON,
               ResumePlanValidationError, UnknownPlanningMode,
               PlanConsistencyError → UnknownEntityReference, DuplicatePlanEntry,
                                      MissingPlanEntry, ImmutableSectionViolation,
                                      PlanningModeViolation
AnalyzerError → InvalidAnalyzerResponse, InvalidAnalyzerJSON,
                JobAnalysisValidationError
ConfigError   → ConfigNotFoundError, ConfigParseError, ConfigValidationError
```
Outlier: `ParserError` lives in `src/parser/metadata_parser.py:12`, not in a
`parser/exceptions.py`.

**Orchestrator pipeline** (copy this shape) — `src/planner/planner.py:132-143`:

```python
prompt = build_prompt(...)
raw    = self._invoke_provider(prompt)      # wraps all provider errors
data   = canonicalize(self._parse_json(raw))
self._reject_forbidden_keys(data)
obj    = self._validate(data, mode)         # caller's mode overwrites the model's
self._validate_against_resume(obj, resume, mode)
```

`_invoke_provider` re-raises the package's own error untouched and wraps every
other `Exception`; an empty response is `Invalid...Response`; a `JSONDecodeError`
is `Invalid...JSON`. **There is no retry logic anywhere in `src/`, by design.**

**Coding standards** (`docs/CODING_STANDARDS.md`): type hints everywhere;
docstring on every public function; no function over 50 lines; Pydantic models;
never access config directly; no duplicated logic; every module has tests.

**Python 3.9.** `pyproject.toml` says `requires-python = ">=3.9"` and the venv is
3.9. Use `typing.List` / `typing.Optional`; `X | Y` unions will not parse.

**Test conventions:**
- Fakes subclass the `LLMProvider` ABC. The suite **never uses `unittest.mock`**.
  `tests/planner/conftest.py` defines `FakeProvider` (canned string),
  `FailingProvider` (raises), `CapturingProvider` (records prompts + options).
- Bare `pytest.raises(X)` — the suite never uses `match=`.
- Fixtures are Python factory functions returning `copy.deepcopy`, not files —
  `make_resume()`, `make_job_analysis()`, `make_payload(**overrides)`.
  The only on-disk fixtures are `tests/fixtures/job_descriptions/*.md` and
  `tests/fixtures/model_based_responses/`.
- `verify_*.py` scripts are live-model checks and are **not collected** by
  pytest.
- Layout: `tests/{analyzer,cli,config,parser,planner,providers,validation}/`.

**CLI shape** (`src/cli/plan.py`): Typer app, commands registered by plain
function reference in `src/cli/main.py:40-42`. Ordered failure gates each print
`✗ …` and `raise typer.Exit(code=1)`. One `try` block catches component
exceptions most-specific-first, then the provider family. The CLI never builds
prompts, parses JSON, or validates models.

---

## 9. Hard-won lessons

From `feedback/resume-planner-verdict.md`. Do not re-litigate these without
re-running the experiment that produced them.

1. **Ollama reasoning models need `"think": False`.** Without it they burn the
   entire token budget on hidden reasoning and return empty content. Fixed in
   `src/providers/ollama.py:102`.

2. **JSON schema field order is load-bearing.** When one prompt skeleton
   contains several similar-but-distinct shapes, small local models reproduce
   them *positionally* — the slot a field sits in matters more than its name.
   `reasoning` must sit immediately after `priority` in all four planner shapes.
   When it didn't, qwen3.6 carried the skills-shaped layout into
   `project_plans` and emitted `"new_category_name": null` where `reasoning`
   belonged, killing the whole plan reproducibly. Pinned by
   `tests/planner/test_determinism.py::TestSchemaFieldOrder`, and explained in
   the comment at `src/planner/prompts.py:51-68`.

3. **Model sweep.** `qwen3.6:latest` works (19–83 s per plan). `qwen2.5:7b` and
   `gemma4:12b` each fail differently.

4. **Latency is unstable.** At the slow end, analyze + plan alone consume 1.5–2
   minutes of the 3-minute budget, leaving under a minute for generation, LaTeX
   and revision.

5. **Analyzer and Planner are deterministic by decision; the Generator is not.**
   Greedy decoding (`top_k=1`) produces flat, repetitive prose — correct for
   decisions, a quality cost for resume bullets. Raising `temperature` while
   `top_k=1` stays pinned changes nothing; both must be relaxed together.

6. **Offline tests are not evidence.** The planner shipped with 318 green tests
   while every real invocation failed. Every component needs a live check.
   Task 012 confirmed the value: 461 offline tests were green, and the *first*
   live strict-mode run failed immediately on a gap none of them covered — the
   planner proposing a brand-new skill through `skills_to_add` in strict mode.
   That became rule 26.

7. **A rule enforced in one layer must be enforced in every layer that can
   breach it.** Strict mode's promise is "no new facts". The planner enforced
   it for `GENERATE` and the generator enforced it for prose, but
   `skills_to_add` slipped between them. When adding a mode rule, walk every
   path that writes to the resume.

---

## 10. Gotchas that have already cost time

- **`config/config.yaml` is inert.** Nothing in `src/` reads it. It exists only
  because `docs/ARCHITECTURE.md` mandates the path. Real config is
  `~/.resume-tailor/config.toml` via `src/config/manager.py`, with API keys in
  the OS keyring via `src/config/credentials.py`.
- **`SectionPriority` serialises as `3`, not `"MEDIUM"`.** `model_dump_json()`
  on a plan emits ints. Any prompt embedding a plan needs a hand-built
  projection.
- **`uv` is not on PATH** in this environment. Run tests with
  `.venv/bin/python -m pytest`.
- **`docs/ARCHITECTURE.md` says Python 3.12+**, `pyproject.toml` says `>=3.9`,
  and the venv is 3.9. The venv wins.
- **`docs/ARCHITECTURE.md` references a `ROADMAP.md` that does not exist**, and
  it is marked *Frozen* with a rule that implementation diverging from it is
  "considered incorrect unless the architecture has been explicitly updated
  first". Both ARCHITECTURE and `docs/COMPONENT_SPECIFICATIONS.md` still
  describe the Generator as `Resume + JDAnalysis + Mode → Resume`, with no
  Planner stage and no `ResumePlan` — a divergence that must be corrected in the
  docs as part of task 012.
- **`docs/IMPLEMENTATION_GUIDE.md` is a stub** — eight bare headings.
- **Not installed:** Rich, PyMuPDF, PyYAML.

---

## 10b. Resume Generator (task 012)

`src/generator/` — `exceptions`, `models`, `sampling`, `prompts`, `canonical`,
`constraints`, `generator`, `__init__`.

```python
ResumeGenerator(provider).generate(
    source_resume=..., job_analysis=..., resume_plan=...,
    mode=None,                        # defaults to resume_plan.mode
    temperature=GENERATOR_TEMPERATURE,
) -> Resume
```

- **Three LLM calls, not one**: summary, all experiences, all projects. A
  section whose plan is entirely KEEP makes no call at all — an all-KEEP plan
  generates with zero calls.
- **Skills make no call ever.** The planner already emits literal
  `new_category_name` and `skills_to_add` strings. Skills are applied in pure
  Python, ordered JD-keywords-first.
- **Non-deterministic by design**: `generator_options()` sets `temperature=0.4`
  with `top_k=40` and `top_p=0.9`. Both must move together — raising
  temperature while `top_k=1` stays pinned does nothing.
- **Immutable fields are re-imposed in Python**, never trusted from the model:
  `company`, `duration`, `employment_type`, `location`, `id`, `source`, and
  `role` in strict mode.
- **Strict mode is enforced in Python**, in two layers:
  - *Filtered, not raised on* — generated `technologies` and `domains` are
    restricted to a vocabulary, preserving the model's ordering. **Strict:
    source only.** **Aggressive: source ∪ job** (`job_vocabulary`, built from
    `JobAnalysis`'s structured term lists — not `responsibilities` or
    `qualifications`, which are prose and would admit nearly any word). A term
    in neither the resume nor the job is invention, not tailoring: `Jest`
    reached a generated resume exactly that way before aggressive had any
    vocabulary at all. Filtering makes the invalid state unreachable rather
    than merely detected — raising instead would discard a whole 65-second
    generation over one stray label.
  - *Raised on* — `constraints.enforce_strict` is the backstop: any surviving
    unsupported term, and any number not in the source prose (0–10 tolerated
    as rephrasing), raises `GenerationConstraintError`. It is a heuristic; it
    cannot catch a fabricated responsibility phrased in words the resume
    already uses.
- **Weak terms never displace real ones.** `src/vocabulary.py` judges whether
  a proposed `domains` / `technologies` / skill entry is worth taking. Two
  independent tests, unioned as `is_weak_term`:
  - `is_too_general` — refuses a phrase where *every* significant word is
    generic software-process vocabulary. Lenient by construction: one specific
    word saves it. "Application Software Development" fails; "SOC Automation"
    survives on "SOC"; "Sales Planning" survives on "Sales".
  - `looks_like_an_activity` — refuses a phrase that is specific but names
    doing rather than knowing: "Interoperability Strategies", "Defect
    Handling". In "A of B" the head is A, so "Optimization of Coding" is
    judged on "optimization".

  **The retention rule matters as much as the tests.** When any proposal is
  refused, the resume's own terms are retained alongside the survivors;
  a response with nothing refused replaces outright. Without this, a model
  proposing six empty phrases and one thin real one leaves the field holding
  only the thin one — observed live, where five rich domains collapsed to a
  lone "API Versioning". Genuine retargeting still works: a job naming real
  domains throughout has nothing refused, so it replaces cleanly.

  The rationale, from the live run that motivated it: the backend JD names
  exactly **one** technology in 83 lines (OCI) and its extracted "domains" are
  its own section headings. There was no competitor for the slot, so swapping
  out "SOC Platforms" bought nothing. Replacement is right when something
  specific is competing for the space.
- **Nothing is deleted unless something replaces it.** Applied at every point
  the generator can remove content:
  - *Skills inside a category* — a plan wanting to remove more than it offers
    has its removals cancelled. Removing five to add one is a loss, not a
    trade.
  - *Whole skill categories and projects* — each successful `GENERATE` funds
    exactly one `REMOVE`. Removals past that budget are cancelled.
  - *Domains and technologies* — the retention rule above.

  Every cancellation is reported on `last_discarded`. This means the generator
  can only grow the resume; **shrinking to fit one page belongs to the Quality
  Gate**, which should trim for page-fit rather than guessed relevance.

- **A lopsided trade splits instead of clubbing.** When a plan wants to remove
  more than it adds *and* named the incoming group, the original category is
  left intact and the incoming skills get their own new `GENERATED` category.
  Merging "Performance Profiling" into a category holding "Distributed
  Systems, API Design, Caching" would put unrelated things under one heading.
  With no rename supplied, the additions were meant to sit beside the existing
  skills, so they merge in place.

- **Everything the Quality Gate can trim is ordered strongest-first**, because
  it trims from the bottom to fit one page. The rule to apply when adding any
  new list to the resume: the last element must be the one you would give up.
  - *Skill categories and projects* — sorted by plan priority. `sorted()` is
    stable, so equal priorities keep plan order.
  - *Skills within a category* — job keywords first, then source order, in the
    order `required_skills → technologies → preferred_skills → keywords`.
    Applied **once at the end of `_apply_skills`**, not on each path that
    produces a category: `KEEP`, a cancelled removal and a cancelled lopsided
    rewrite all return the source category untouched and would otherwise ship
    in source order.
  - *Highlights (bullets)* — the prompts ask for strongest-first and forbid
    padding to the ceiling, and `_order_highlights` then **enforces** it with a
    stable re-sort. Two signals only: how many of the job's terms the bullet
    uses, plus `METRIC_WEIGHT` (2) if it carries a number. Ties keep the
    model's order, so the scoring corrects clear mistakes without overruling
    judgement it cannot see. Applied as a post-pass in `generate()` so `KEEP`
    experiences and projects are ordered too.

    This matters most for experiences: the two of them can never be *deleted*
    (the validator requires exactly two), but their bullets can be trimmed, so
    the order *within* each one decides what survives.

    Note the planner cannot help here, and `highlight_indices` from task 011
    would not have worked: the planner rates *source* bullets, the generator
    *rewrites* them into new ones, and the mapping between old and new is N:M.
    A priority attached to source bullet 3 has nothing to attach to afterwards.
  - *Experiences are deliberately never reordered* — the validator compares
    them positionally against the source, and a resume reads
    reverse-chronologically regardless of relevance.

- **Aggressive asks for one quantified outcome per experience and project.** A
  bullet carrying a number is the one a reviewer believes. The prompt states
  believability guardrails explicitly — the figure must follow from the work
  described, be round and modest, stay in the ordinary range for what it
  measures, never invent a checkable fact about the employer (headcount,
  revenue, customers), and reuse a source number where one fits.
  `_report_unquantified` counts compliance and notes any section that came
  back without a number.

  **Counted, not judged.** Whether a number is believable cannot be checked
  mechanically — "cut latency 40%" and "cut latency 97%" are identical to a
  regular expression. Strict mode never reaches this check: it forbids
  introducing any number not already in the source.

- **Mid-sentence capitalisation is corrected, not requested.** A model working
  a job's vocabulary into prose Capitalises it — "rigorous Software Testing and
  Code Quality assurance during Production Support" reads like a brochure.
  `decapitalise_mid_sentence` fixes it over the summary and every highlight.

  Three things make it safe:
  - **Keyed to `GENERIC_TERMS`.** Only those words are lowercased, and a real
    proper noun is never in that set — `Java`, `Redis`, `Terraform`, `Zoho`
    pass through untouched.
  - **Acronyms are skipped.** An all-uppercase word (`API`, `REST`, `OCI`) is
    never altered, nor is a word starting a sentence.
  - **Runs move as a unit**, and the source's own capitalisations are
    protected. Lowercasing half a phrase leaves "system Design", which reads
    worse than the original; and "Backend Software Engineer" / "Security
    Operations Center" contain generic words but are the candidate's own
    title-casing. `_source_capitalisations` collects them and a greedy
    longest-match keeps them, even when they sit inside a longer run.

- **The summary must keep its anchors.** The prompt requires the employer, the
  years of experience and the named technologies to survive a rewrite —
  trading "2 years at Zoho building platforms in Java, Spring Boot and Redis"
  for "Application Software Development professional" gives up everything that
  made the resume credible and gains a job title. `_report_lost_anchors`
  checks it afterwards and notes any loss on `last_discarded`. **Reported, not
  raised**: the summary is one paragraph, so there is no "move it to the
  bottom" available and no safe way to graft a fact back into prose, and prose
  judgement is not a correctness rule.

- **An emptied skill category is dropped**, reported via `last_discarded`. A
  heading with nothing under it renders worse than no heading, and the
  validator only *warns* (`EMPTY_SKILL_CATEGORY`), so it would otherwise ship.
  Emptying every category raises.
- **Validates internally**: errors raise `GeneratorResponseValidationError`,
  warnings land on `generator.last_warnings`, soft failures on
  `generator.last_discarded`.
- **No retries**, matching the rest of the codebase.

Live baseline on `qwen3.6:latest`, `content/backend_resume.md` against
`tests/fixtures/job_descriptions/backend.md`: strict 46 s, aggressive 41 s
(sharing one JD analysis), both with zero validator errors and zero warnings.
Skill retention against that job: strict 21/21 kept, aggressive 20/21 with 3
added.

---

## 10c. Markdown Serializer (task 013)

`src/renderer/` — `exceptions.py`, `markdown_serializer.py`, `__init__.py`.
The renderer package is where LaTeX and PDF rendering will also land.

```python
MarkdownSerializer().serialize(resume) -> str      # complete document, one trailing newline
ResumeParser().parse_string(raw) -> Resume         # new; parse() now delegates to it
```

No LLM call, no file I/O, no mutation. `parse` was reduced to
`return self.parse_string(self._read_file(file_path))` — a pure extraction,
since everything after the read already operated on the raw string.

**Only schema fields are emitted.** `id` and `source` are runtime-only and
never written. This is the deliberate asymmetry of the stage: the Markdown is
the canonical *content*, the Resume model is the canonical *runtime state*, and
the two are not the same set of fields.

**Round-trip guarantees, and the one place they stop.** Parse → serialize →
parse is byte-stable and strictly `==` for anything the Parser produced,
including all three `content/*.md`. It is only *semantically* equal for
Generator output, and the gap is not fixable:

- `source=GENERATED` has no Markdown representation, so it re-parses as
  `CANONICAL`.
- `mint_id` uses `highest + 1`, so a generated resume can hold `[proj_002,
  proj_005]`; `assign_sequential_ids` renumbers those to `[proj_001, proj_002]`
  on re-parse.

So **a serialized generated resume is not a substitute for the object** — do
not write it to disk and re-read it as a way of passing a resume between
stages, or the Quality Gate and Revision Engine lose the lineage they use to
decide what may be touched. Tests compare with `id`/`source` excluded
(`tests/renderer/conftest.py::semantically_equal`).

**Three parser behaviours the serializer exists to route around.** All were
verified against `src/helpers/_section_utils.py`, and all fail *silently*:

- A bare `Key:` where a scalar is expected swallows the next field's whole
  line — `get_scalar`'s `\s*` spans the newline. This, not tidiness, is why an
  absent optional field must be omitted rather than written as
  `Repository: None` or `Repository:`.
- An empty string in a bullet list (`- ` strips to `-`) fails the bullet test
  and hits `get_list`'s `break`, **discarding every later bullet in that list**.
- A line that is exactly `---` does the same, and `SummaryParser` deletes it
  outright.

Each raises `SerializationError` naming the entity id and field. `---`
separators *are* emitted between sections and between sibling entity blocks,
matching `content/*.md` — safe only because they land after the last bullet of
a block, never inside a run.

**Front-matter values are quoted only when they need it.** The metadata parser
does `yaml.safe_load` then `str()`, which retypes bare scalars: `version: 1.10`
→ `1.1`, `template: no` → `"False"`. `_yaml_value` emits bare when
`str(safe_load(...))` reproduces the string and `json.dumps` otherwise, so
ordinary output stays byte-identical to the schema's own examples.

**Field order follows the task doc and `RESUME_SCHEMA.md`, not `content/*.md`.**
The canonical files write `Location` before `Duration` in Experience, and put
`Duration` last in Education. The parser is order-agnostic, so both parse
identically — but serialized output will diff against its own source file on
exactly those lines and nothing else. Verified: the only diff against
`content/cybersecurity_resume.md` is those two field moves.

Live check: `tests/renderer/verify_round_trip.py` drives parse → analyze →
plan → generate → serialize → parse against the real provider, since the
offline suite covers the serializer's logic but cannot produce a realistic
*input*.

---

## 11. Known open items

- **`src/cli/_common.py` is not extracted.** `analyze.py` and `plan.py` already
  duplicate ~60 lines of provider bootstrap + error ladder. A third CLI command
  should trigger the extraction.
- **No bullet-level targeting in the plan.** Plan models address whole entities; there is no
  `highlight_indices: List[int]`. The Revision Engine may need it.
- **`backlog.txt`** holds three "Validation v2" test-coverage ideas.
- **Vocabulary control covers fields, not prose — accepted.** `technologies`
  and `domains` are filtered against the vocabulary; the words *inside* a
  highlight are not. A live aggressive run wrote "Automated infrastructure
  provisioning with Terraform" into a generated project, and Terraform appears
  in neither the resume nor the job description.

  **Decided (with the user): this is acceptable inside a `GENERATED` entity.**
  The project was already invented from a generation brief, so one more
  invented tool inside it costs nothing — the candidate owns the whole entry in
  an interview either way, and Terraform is a real tool that fits the work
  described.

  The distinction that still matters is *where* it lands. The same thing inside
  a `CANONICAL` experience attaches an invented tool to real work at a named
  employer, which invites a question with no answer behind it. The field-level
  filter makes that less likely but does not prevent it in bullet prose.
  Deleting a noun from a sentence is not something the generator can safely do,
  and recognising "this word is a technology" needs a lexicon the project does
  not have. Strict mode is unaffected: `enforce_strict` checks every number in
  prose, and its term check covers the fields.

- **Weak-term filtering is conservative on purpose.** `src/vocabulary.py`
  spares words that could anchor a real domain or skill, so vague entries
  still get through ("Performance Profiling", "Cloud Architecture"). Widening
  the lists trades a weak term left on the resume for a real one deleted —
  the wrong trade. Improve the prompts before touching the lists.
- **Mid-sentence capitalisation** was a live-run regression that prompt rules
  alone never held at temperature 0.4. It is now enforced in Python; the
  prompt rule stays as the first line of defence.
- **Latency.** analyze + plan + generate is ~66–70 s against a 180 s budget,
  leaving roughly 110 s for LaTeX, compilation, the quality gate and up to
  three revisions. Tighter than it looks. The generator's three calls are
  independent of each other and could be issued concurrently if needed.
- **`resume-tailor generate` does not exist.** The CLI was out of scope for
  task 012; `tests/generator/verify_generation.py` is the only way to drive the
  generator live. That command should also trigger the `src/cli/_common.py`
  extraction. The serializer is what it will write its output with.
- **Nothing writes `generated.md` yet.** Task 013 built the serializer but no
  caller. The Resume object still never leaves memory.
- **`""` and `None` are indistinguishable through Markdown.** An optional
  scalar holding `""` is omitted and re-parses as `None`. Emitting
  `Location: ` with a trailing space would preserve it, at the cost of trailing
  whitespace and a value the parser strips to `""` anyway. Accepted: an empty
  optional field and an absent one mean the same thing on a resume.
- **Leading/trailing whitespace inside a field value does not survive.** The
  parser strips it. The serializer emits values verbatim and does not raise,
  because the loss is cosmetic — unlike the three silent-truncation cases,
  which do raise.
