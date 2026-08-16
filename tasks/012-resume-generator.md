# Task 012 — Resume Generator

## Context

The Generator is the first component that performs actual resume
transformation. Everything before it reads, extracts or decides; the Generator
writes.

It consumes a source `Resume`, a `JobAnalysis`, and a `ResumePlan`, and returns
a new `Resume` that follows the plan. It produces no Markdown, no LaTeX and no
PDF — those belong to the Renderer.

The payoff: after this task the pipeline can produce a tailored resume object
end to end, and the Validator has something real to validate.

Read `docs/PROJECT_KNOWLEDGE.md` first. It carries the model definitions,
validator contract, plan invariants, provider vocabulary and house conventions
that this task assumes throughout.

---

## Decisions taken (resolved with the user before planning)

| Question | Decision |
|---|---|
| Is experience `role` mutable? | **Yes, in AGGRESSIVE mode only.** Retitling "Software Engineer" → "Backend Engineer" to match the JD is the point. STRICT keeps the source role. Requires a Validator change (§Files). |
| One LLM call or several? | **Three**: summary, all experiences, all projects. Skills need no call. |
| Do skills need an LLM call? | **No.** The Planner already emits literal `new_category_name` and `skills_to_add` strings. A skill is a name, not prose. Two gaps in `SkillCategoryPlan` are closed upstream instead. |
| How is STRICT enforced? | **Prompt + Python post-check that raises** `GenerationConstraintError`. Prompt-only is untestable. |
| Does the Generator validate? | **Yes, internally.** Errors raise `GeneratorResponseValidationError`; warnings are exposed on the instance. |
| Which `mode` wins, the argument or `ResumePlan.mode`? | The plan's. An explicit argument that disagrees raises `GeneratorError`. |
| Retries? | **None**, consistent with the Analyzer and Planner. |

---

## Scope

**In**

- `src/generator/` package.
- `ResumeValidator` gains a `mode` parameter so `role` can be mutable in
  AGGRESSIVE.
- Two `SkillCategoryPlan` rules closed in the Planner.
- A shared entity-ID minter, replacing the Parser's inline loop.
- `tests/generator/`, plus a live verification script.
- Doc corrections: `docs/ARCHITECTURE.md` and
  `docs/COMPONENT_SPECIFICATIONS.md` still describe a Generator with no
  `ResumePlan` and no Planner stage.

**Out**

Markdown serializer, LaTeX rendering, PDF compilation, Quality Gate, Revision
Engine, ATS scoring, visual analysis, and the `resume-tailor generate` CLI
command. The `src/cli/_common.py` extraction belongs to the CLI task.

---

## Public API

```python
generator = ResumeGenerator(provider)

generated = generator.generate(
    source_resume=source_resume,
    job_analysis=job_analysis,
    resume_plan=resume_plan,
    mode=None,                       # defaults to resume_plan.mode
    temperature=GENERATOR_TEMPERATURE,
)
```

Returns a `Resume`. Never mutates `source_resume`. Holds no state between
calls — the Revision Engine will call it repeatedly.

---

## Files

Python 3.9 typing throughout (`typing.List`, `typing.Optional`; no `X | Y`).

### `src/entity_ids.py` (new)

```python
def mint_id(prefix: str, existing: Iterable[str]) -> str
```

Returns `{prefix}_{n:03d}` where `n` is the highest parseable numeric suffix in
`existing`, plus one. Ids that do not parse are ignored. **Max + 1, not
count + 1** — otherwise removing `proj_001` and generating a replacement
collides with `proj_002`.

Refactor `src/parser/resume_parser.py:89-96` to use it, so there is one
convention rather than two.

### `src/validation/validator.py` (modified)

```python
def validate(self, *, source_resume: Resume, generated_resume: Resume,
             mode: str = "STRICT") -> ValidationResult
```

- `mode` is keyword-only and **defaults to strict**, so every existing caller
  and test is unaffected. `PlanningMode` is a `str` Enum, so a `PlanningMode`
  value passes through unchanged; normalise case-insensitively inside
  `src/validation/`.
- Do **not** import from `src.planner`. That would put a domain dependency in
  the validation layer for no benefit.
- Immutable experience fields become `("company", "duration")` always, plus
  `"role"` when the mode is not aggressive (currently hardcoded at
  `validator.py:333,384`).
- Also pin `employment_type` and `location`, which are unchecked today and
  which the Generator will now be constructing.

### `src/planner/models.py` (modified)

Two rules in `SkillCategoryPlan._check_generate_pairing` (`models.py:171`):

1. `GENERATE` requires **non-empty `skills_to_add`**. Today a named category
   with zero skills is legal and the Validator only *warns*
   (`EMPTY_SKILL_CATEGORY`), so an empty category would ship.
2. `REWRITE` may set an optional `new_category_name`, so a category can be
   renamed to match JD language. Still forbidden on `KEEP` and `REMOVE`.

A third rule was added in `src/planner/planner.py` after the first live run
caught it. In **strict mode**, a `skills_to_add` entry naming a skill that
appears nowhere in the resume is dropped and reported via `last_discarded`,
matching how rule 21 handles an impossible removal. Strict forbids `GENERATE`,
but nothing stopped a `REWRITE` from smuggling a brand-new skill in this way —
and the Generator applies skill plans verbatim, so it reached the resume as a
claim the candidate never made. The vocabulary is deliberately wide (skills
plus every technology and domain on any experience or project), because strict
mode does permit *reorganizing* existing information.

Update the schema comment in `src/planner/prompts.py` and the rule table in
`tasks/011-resume-planner.md`. **No field reordering** — the skills shape
already lists `new_category_name` after `reasoning`, which is the order
`tests/planner/test_determinism.py::TestSchemaFieldOrder` pins.

### `src/generator/exceptions.py` (new)

```
GeneratorError
├── InvalidGeneratorResponse
├── InvalidGeneratorJSON
├── GeneratorResponseValidationError
└── GenerationConstraintError
```

Docstring-only bodies, matching `src/planner/exceptions.py`. No SDK error ever
reaches a caller.

### `src/generator/models.py` (new)

The per-section LLM response shapes only — never `Resume`. Standard
`ConfigDict(extra="forbid", validate_assignment=True)`.

```python
class SummaryResponse:      summary: str

class ExperienceContent:    experience_id: str
                            role: str
                            technologies: List[str]
                            domains: List[str]
                            highlights: List[str]
class ExperienceResponse:   experiences: List[ExperienceContent]

class ProjectContent:       project_id: Optional[str]   # None for GENERATE
                            name: str
                            type: str
                            technologies: List[str]
                            domains: List[str]
                            highlights: List[str]
class ProjectResponse:      projects: List[ProjectContent]
```

Prose and identifying fields only. The model never returns `source`, never
returns a minted id, never returns an action.

### `src/generator/sampling.py` (new)

```python
GENERATOR_NUM_CTX = 16384
GENERATOR_MAX_TOKENS = 4096
GENERATOR_TEMPERATURE = 0.4
GENERATOR_TOP_K = 40
GENERATOR_TOP_P = 0.9

def generator_options(temperature: float = GENERATOR_TEMPERATURE) -> Dict[str, Any]
```

Built on `deterministic_options(...)`. `top_k` and `top_p` must be relaxed
alongside `temperature` — raising temperature while `top_k=1` remains pinned is
a no-op. `seed=42` is kept so a fixed temperature still reproduces.
`json_mode` stays on. Returns a fresh dict each call.

### `src/generator/prompts.py` (new)

```python
def build_summary_prompt(resume, job_analysis, plan, mode) -> str
def build_experiences_prompt(resume, job_analysis, plan, mode) -> str
def build_projects_prompt(resume, job_analysis, plan, mode) -> str
```

Pure functions, byte-stable for identical inputs. Each embeds only the slice of
the plan it needs, plus shared mode rules.

Carried over from the Planner: brace-doubling in the `str.format` templates; a
hand-built plan projection rather than `model_dump_json()`, which renders
`SectionPriority` as `3` instead of `MEDIUM`; and **uniform field ordering
across the repeated JSON shapes**, pinned by a test and carrying the same
explanatory comment as `src/planner/prompts.py:51-68`.

Mode rules must state explicitly:
- **AGGRESSIVE** — `role` may be retitled to match the JD, but the employer,
  dates and employment type may not change, and seniority must not be inflated.
- **STRICT** — `role` is fixed; no technology, skill, metric or achievement may
  appear that is not already in the source resume.

Prompts also state the budgets the Validator checks: summary 20–120 words,
≤8 experience highlights, ≤6 project highlights.

### `src/generator/canonical.py` (new)

Light normalisation of each parsed section response before validation: strip
strings, drop empty list entries, coerce `null` to `[]`. A non-zero temperature
produces small formatting variance that should not fail a generation.

### `src/generator/constraints.py` (new)

The STRICT post-check, kept out of `generator.py` to respect the 50-line rule.

```python
def source_vocabulary(resume: Resume) -> Set[str]
def enforce_strict(source: Resume, generated: Resume) -> None
```

- Vocabulary = case-insensitive set of all `technologies`, `domains`,
  `all_skills()`, and the tokens of every highlight and the summary.
- Generated `technologies` and `domains` are **filtered** to this vocabulary in
  `generator.py` before the check runs, preserving the model's ordering, with a
  fallback to the source list when filtering would empty them. Strict mode
  explicitly permits reordering and subsetting existing information, so this is
  the intended behaviour — and it makes the invalid state unreachable rather
  than merely detected. Raising here instead discards a 65-second generation
  over one vague label lifted from the JD.
- Any term that still survives is a genuine violation →
  `GenerationConstraintError` naming it. This is the backstop, and after
  filtering it should never fire on terms.
- Every numeric token (`\d[\d,]*(?:\.\d+)?%?`) in a generated highlight or the
  summary must appear in the source text — otherwise
  `GenerationConstraintError`.
- AGGRESSIVE skips all of it.

This is a heuristic, not a proof. It catches the failure modes the tests
describe and nothing more.

### `src/generator/generator.py` (new)

`ResumeGenerator(provider)`, mirroring `ResumePlanner`'s pipeline and its
no-retry policy.

State, reset at the top of every call: `self.last_warnings: List[ValidationIssue]`
and `self.last_discarded: List[str]`. Nothing else — each call is independent.

Work on `source_resume.model_copy(deep=True)`; the source is never touched.

Section order:

1. **Skills — pure Python, no LLM.** `KEEP` copies. `REWRITE` applies
   `skills_to_add` / `skills_to_remove`, renames if `new_category_name` is set,
   and preserves the existing id and `source`. `REMOVE` drops the category.
   `GENERATE` mints `skill_NNN`, uses `new_category_name` + `skills_to_add`,
   and sets `source=GENERATED`. Skills are ordered JD-keywords-first, then
   source order — deterministic, no model needed.

2. **Summary** — one call. `KEEP` copies verbatim.

3. **Experiences** — one call covering both. `KEEP` copies. `REWRITE` replaces
   `technologies`, `domains`, `highlights`, and `role` in AGGRESSIVE only.
   `company`, `duration`, `employment_type`, `location`, `id` and `source` are
   re-imposed from the source in Python after parsing — never trusted from the
   model.

4. **Projects** — one call covering all non-`KEEP`, non-`REMOVE` entries.
   `KEEP` copies, `REMOVE` drops, `REWRITE` preserves id and `source`.
   `GENERATE` mints `proj_NNN`, sets `source=GENERATED`, takes `type` from the
   model, and forces `repository=None` — a URL cannot be invented. If fewer
   than two projects survive, raise `GenerationConstraintError` before calling
   the Validator, so the failure names the real cause.

5. **Reassemble** — `metadata`, `contact` and `education` deep-copied from the
   source unchanged.

6. **STRICT post-check** via `constraints.enforce_strict`.

7. **Validate** — `ResumeValidator().validate(source_resume=..., generated_resume=...,
   mode=mode)`. Non-empty `errors` raises `GeneratorResponseValidationError`;
   `warnings` are stored on `self.last_warnings`.

Every LLM call reuses `extract_json_object` from
`src/analyzer/_json_extract.py` and wraps provider failures exactly as
`ResumePlanner._invoke_provider` does (`planner.py:149-170`): re-raise
`GeneratorError` untouched, wrap every other `Exception`, empty response →
`InvalidGeneratorResponse`, `JSONDecodeError` → `InvalidGeneratorJSON`.

### `src/generator/__init__.py` (new)

Explicit `__all__`, ordered like `src/planner/__init__.py`.

---

## Validation ruleset → exception

| # | Rule | Exception |
|---|---|---|
| 1 | Provider returned empty or whitespace | `InvalidGeneratorResponse` |
| 2 | Provider raised anything else | `GeneratorError` |
| 3 | Response is not parseable JSON | `InvalidGeneratorJSON` |
| 4 | Response fails its section Pydantic model | `InvalidGeneratorResponse` |
| 5 | Response omits an entity the plan required | `InvalidGeneratorResponse` |
| 6 | Response references an id not in the plan | `InvalidGeneratorResponse` |
| 7 | `mode` argument disagrees with `resume_plan.mode` | `GeneratorError` |
| 8 | STRICT: technology/domain/skill absent from source vocabulary | `GenerationConstraintError` |
| 9 | STRICT: numeric token absent from source text | `GenerationConstraintError` |
| 10 | Fewer than two projects survive `REMOVE` | `GenerationConstraintError` |
| 10b | No skill categories survive | `GenerationConstraintError` |
| 10c | One skill category is left with no skills | **none** — dropped, reported in `last_discarded` |
| 10d | A REMOVE is not funded by a successful GENERATE | **none** — cancelled, reported in `last_discarded` |
| 10e | A REWRITE removes more skills than it adds | **none** — removals cancelled; named additions split into a new category |
| 11 | Generated resume fails `ResumeValidator` | `GeneratorResponseValidationError` |

Rules 8 and 9 are skipped entirely in AGGRESSIVE. STRICT never sees a
`GENERATE` action — the Planner already blocks it with `PlanningModeViolation`.

---

## Tests — `tests/generator/`

`conftest.py` — fakes subclassing the `LLMProvider` ABC (no `unittest.mock`),
including a `SequencedProvider` that returns a different canned response per
call, since there are now three. Factories `make_resume()`,
`make_job_analysis()`, `make_plan(**overrides)` returning deep copies.

| File | Covers |
|---|---|
| `test_ids.py` | `mint_id` format, max+1 after a removal, unparseable ids ignored, empty input |
| `test_prompts.py` | each builder embeds the right plan slice, mode rules differ, brace-doubling survives |
| `test_constraints.py` | vocabulary construction, new technology rejected, new skill rejected, fabricated metric rejected, rephrased-but-supported content accepted, AGGRESSIVE skips |
| `test_generator.py` | the bulk — see below |
| `test_determinism.py` | prompt byte-stability, schema field order, `generator_options()` returns an independent copy with `top_k`/`top_p` relaxed |

`test_generator.py` must cover: all four actions in every section that supports
them · a generated skill category takes its name and skills straight from the
plan with a minted id and `GENERATED` · a renamed `REWRITE` category keeps its
original id and source · `role` changes in AGGRESSIVE and is re-imposed in
STRICT · contact, education, metadata, company, duration, employment_type and
location identical to source · exactly two experiences, never reordered · fewer
than two projects raises · existing ids and sources survive rewrites · minting
is max+1 · the source resume is unmutated (compare against a pre-call deep
copy) · a mode mismatch raises · each provider failure maps to the right
exception · two successive calls share no state.

`test_determinism.py` deliberately does **not** assert five-iteration output
identity. The Generator is non-deterministic by decision
(`feedback/resume-planner-verdict.md` §2).

`tests/generator/verify_generation.py` — non-collected live script against
`qwen3.6:latest`, matching `tests/planner/verify_determinism.py`. Offline tests
alone are not evidence: the Planner shipped with 318 green tests while every
real invocation failed.

---

## Verification

```bash
.venv/bin/python -m pytest tests/generator -q
.venv/bin/python -m pytest tests/validation -q   # role/mode change must not regress
.venv/bin/python -m pytest tests/planner -q      # SkillCategoryPlan change must not regress
.venv/bin/python -m pytest tests/parser -q       # ID minter refactor must not regress
.venv/bin/python -m pytest -q                    # baseline: 339 passing
.venv/bin/python tests/generator/verify_generation.py   # live, needs the Ollama tunnel
```

Live checks, both modes, against a real JD:

- STRICT output introduces no technology and no number absent from the source.
- AGGRESSIVE output may retitle a role, without changing the employer.
- Both pass `ResumeValidator` with zero errors.
- Total generation time is recorded, to see what is left of the 180 s budget.

**Recorded result** — `qwen3.6:latest`, `content/backend_resume.md` against
`tests/fixtures/job_descriptions/backend.md`:

| Mode | Time | Result |
|---|---|---|
| STRICT | 65.1 s | PASS — no fabricated terms or metrics, no warnings |
| AGGRESSIVE | 68.9 s | PASS — 1 generated project, 1 generated skill category |

Four separate defects surfaced only in live runs, none caught by the offline
suite, which was green throughout:

1. The planner adding unsupported skills through `skills_to_add` in strict mode
   → planner rule 26.
2. The planner filling skill categories with JD prose ("Interoperability
   Strategies", "Defect Handling") → planner rule 27, prompt and Python.
3. The generator putting a JD phrase into an experience's `domains`, killing a
   65-second strict generation → term filtering in `generator.py`.
4. A `REWRITE` leaving a skill category with no skills → dropped and reported.

That is the argument for this script existing.

---

## Risks

1. **Latency.** Three sequential calls at 19–83 s each, on top of analyze and
   plan, against a 180 s budget. It may not fit. The three calls are
   independent and could be issued concurrently later — measure before
   optimising.
2. **Mutable `role` weakens the immutability contract.** A model could inflate
   "Software Engineer" to "Staff Engineer" and the Validator cannot detect it.
   Mitigated only by the prompt. Add a rule if it shows up in live runs.
3. **The metric heuristic will produce false positives.** A rephrased "three
   services" → "3 services" reads as fabrication. Expect noise in STRICT.
4. **Field-order regressions** kill whole sections silently on small models.
   The determinism test is the only guard; do not reorder schema fields
   casually.
5. **Skill quality now rests entirely on the Planner.** With no Generator pass
   over skills, a badly chosen `skills_to_add` ships verbatim, and "react"
   stays lowercase. If live runs show weak selection, fix the Planner prompt —
   do not add a fourth call.

---

## Definition of Done

- `ResumeGenerator` accepts `source_resume`, `job_analysis`, `resume_plan`,
  `mode` and `temperature`, and returns a `Resume`.
- KEEP / REWRITE / REMOVE / GENERATE handled in every section that allows them.
- STRICT constraints enforced in Python, not only in the prompt.
- AGGRESSIVE permits new technologies, skills, categories, projects and metrics,
  and role retitling.
- Immutable fields identical to source; exactly two experiences; ≥2 projects.
- Generated entities carry application-minted ids and `EntitySource.GENERATED`.
- Existing ids and sources preserved on rewrite.
- The source resume is never mutated.
- Output passes `ResumeValidator` with zero errors in both modes.
- Full suite green, and the live script produces a valid resume in both modes.
