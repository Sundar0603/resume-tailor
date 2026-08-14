# Project Knowledge

Dense reference for Resume Tailor. Attach this to a new task session instead of
re-exploring the codebase.

Status as of the end of task 012 (Resume Generator). Baseline: **487 tests
passing** (339 before task 012). Update this file at the end of each task; do
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

`EntitySource.GENERATED` exists but **nothing in `src/` sets it yet** — the
Generator is the first component that will.

Public re-exports from `src/parser/__init__.py`: `ResumeParser`, all models,
`EntitySource`, `ParserError`.

---

## 3. Entity IDs

Format `{prefix}_{n:03d}`, 1-based, positional. Prefixes: `skill_`, `exp_`,
`proj_`, `edu_`.

Minted in exactly one place today — `src/parser/resume_parser.py:89-96` — after
all section parsers return:

```python
for i, proj in enumerate(projects, start=1):
    proj.id = f"proj_{i:03d}"
```

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
                              generated_resume: Resume) -> ValidationResult
```

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
- **Strict mode is enforced in Python** by `constraints.enforce_strict` — every
  technology/domain/skill must be in the source vocabulary, every number must
  appear in the source prose (numbers 0–10 are tolerated as rephrasing). It is
  a heuristic; it cannot catch a fabricated responsibility phrased in words the
  resume already uses.
- **Validates internally**: errors raise `GeneratorResponseValidationError`,
  warnings land on `generator.last_warnings`, soft failures on
  `generator.last_discarded`.
- **No retries**, matching the rest of the codebase.

Live baseline on `qwen3.6:latest`, `content/backend_resume.md` against
`tests/fixtures/job_descriptions/backend.md`: strict 66 s, aggressive 69 s, both
producing a resume with zero validator errors.

---

## 11. Known open items

- **`src/cli/_common.py` is not extracted.** `analyze.py` and `plan.py` already
  duplicate ~60 lines of provider bootstrap + error ladder. A third CLI command
  should trigger the extraction.
- **No bullet-level targeting.** Plan models address whole entities; there is no
  `highlight_indices: List[int]`. The Revision Engine may need it.
- **`backlog.txt`** holds three "Validation v2" test-coverage ideas.
- **The planner picks weak skills.** On the first live aggressive run it added
  JD *responsibility phrases* to skill categories as if they were skills —
  "Interoperability Strategies", "Optimization of Coding", "Application
  Software Development Lifecycle", "Broad Acceptance Criteria". They are
  structurally valid, so nothing rejects them, but they read badly on a resume.
  The fix belongs in the planner prompt (teach it that a skill is a noun a
  recruiter could filter on), **not** in a new generator LLM call.
- **Latency.** analyze + plan + generate is ~66–70 s against a 180 s budget,
  leaving roughly 110 s for LaTeX, compilation, the quality gate and up to
  three revisions. Tighter than it looks. The generator's three calls are
  independent of each other and could be issued concurrently if needed.
- **`resume-tailor generate` does not exist.** The CLI was out of scope for
  task 012; `tests/generator/verify_generation.py` is the only way to drive the
  generator live. That command should also trigger the `src/cli/_common.py`
  extraction.
