# Project Knowledge

Dense reference for Resume Tailor. Attach this to a new task session instead of
re-exploring the codebase.

Status as of the end of task 018 (Reporter).
Baseline: **1398 tests passing, 1 skipped** (1340 after task 017); 83 of those
need a TeX distribution and skip when none is on PATH. Update this file at the end of each task; do not rewrite
it.

---

## 1. Pipeline and stage status

```
Markdown Resume
  → Resume Parser        ✅ 002, 003, 004
  → Resume Validator     ✅ 005
  → JD Analyzer          ✅ 006, 010
  → Resume Planner       ✅ 011
  → Resume Generator     ✅ 012
  → Markdown Serializer  ✅ 013   (side branch → generated.md)
  → LaTeX Renderer       ✅ 014   (fed the Resume object, not Markdown)
  → pdflatex Compiler    ✅ 015
  → Quality Gate         ✅ 016
  → Revision Engine      ✅ 017
  → Reporter             ✅ 018
```

**The reference chain.** This is the current, canonical data path — keep it up
to date, and run it on every change.

```text
Source Resume + Job Description + Mode
      ↓
JD Analyzer ──────────────→ JobAnalysis ─┐
      ↓                                  │
Resume Planner ──────────→ ResumePlan ───┤
      ↓                                  │
Resume Generator ←───────────────────────┘
      ↓
Resume Object ──────→ Markdown Serializer → generated.md   (side branch)
      ↓
LaTeX Renderer  →  resume.tex
      ↓
PDF Compiler  →  resume.pdf
      ↓
Quality Gate  →  QualityGateResult
      ↓
Revision / Shortening  →  a one-page Resume   (only when the gate failed)
      ↓
Reporter  →  report.md + changes.md + report.json   (side branch, no LLM)
```

**The Markdown Serializer branches off the Resume Object; it is not a link in
the path.** An earlier drawing placed it between the Resume Object and the
LaTeX Renderer. That is not buildable: the Renderer consumes a `Resume`, so
an in-path serializer means `serialize → parse`, which silently destroys the
entity lineage the Revision Engine depends on. Measured, and pinned by a test —
see §10g. The serializer still runs on every pass and still emits
`generated.md`; it just does not feed the Renderer.

`src/pipeline/` runs this chain end to end, and `tests/pipeline/` exercises it
offline on every change.

Supporting stages already built: provider config + keyring (007), five providers
+ factory (008), `resume-tailor doctor` (009), `resume-tailor analyze` (010),
`resume-tailor plan` (011).

Budgets from `docs/ARCHITECTURE.md`: typical run 45–90 s, hard max 180 s, max 4
LLM generations, max 3 revisions. Revision order per section: Summary 1,
Projects 2, Skills 3, Experience 4. Education never revised.

**Separation of concerns that must not blur:** the Analyzer extracts, the
Planner decides *what changes and why*, the Generator writes *the words*, the
Renderer produces LaTeX from a frozen template (AI never touches LaTeX), the
Compiler only answers "did the engine produce a readable PDF", the Quality Gate
judges the compiled PDF.

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

8. **Measure against an exact baseline, or measure nothing.** Validating the
   strict entry manifest, the first A/B built its no-manifest baseline by
   string-removing the manifest from the new prompt. That left one extra blank
   line. Under greedy decoding it was enough to change the output, and the A/B
   came back 4/4 both ways — "the fix does nothing". With the baseline
   reconstructed byte-exactly, the same test read 0/4 without and 4/4 with.

   The same flaw then hid a real regression in the other direction: the manifest
   *broke* aggressive mode, 4/4 → 0/4 with unbalanced JSON, because aggressive
   must hedge every count with "plus one entry per GENERATE" — reintroducing the
   ambiguity the manifest exists to remove. Hence strict-only, and hence
   `_entry_manifest` returning exactly `""` elsewhere, pinned by
   `TestEntryManifest::test_the_aggressive_prompt_has_no_stray_blank_line`.

   Two habits follow. A prompt A/B must diff the two prompts and confirm the
   only difference is the thing under test. And a prompt change must be measured
   in **every** mode it touches, not just the one being fixed.

10. **A mode boundary drawn from one pairing is a hypothesis, not a result.**
   The planner's entry manifest was made strict-only on measured evidence: on
   the cybersecurity pairing it took strict 0/4 → 4/4 and aggressive 4/4 → 0/4.
   The conclusion recorded from that — "aggressive never exhibits the shape
   bleed" — was an over-read. The first real end-to-end run found aggressive
   failing 0/4 on backend+backend with exactly that bleed.

   What the numbers had actually shown was narrower: the *strict* manifest is
   wrong for aggressive, because its exact counts leave nowhere to put a
   GENERATE entry. An aggressive-shaped manifest fixes the bleed with no
   regression anywhere (24/24 across three pairings, both modes).

   This is lesson 8 one level up. That one says measure every *mode* a prompt
   change touches; this adds: and every *pairing* you intend to generalise
   over. Three resumes and three JDs is cheap — roughly 20 minutes of local
   inference — against a mode being silently broken for months.

   Corollary, from the same episode: when a fix makes a failing case pass,
   check it did not do so by disabling the feature. The aggressive manifest
   could have scored 4/4 by suppressing GENERATE entirely and quietly turning
   aggressive into strict; it was only trustworthy once the plans were shown to
   still contain GENERATE entries.

9. **A rule enforced in one layer must be enforced in every layer that can
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
- **Python is 3.9.** `pyproject.toml` says `>=3.9` and the venv is 3.9.
  (ARCHITECTURE used to claim 3.12+; corrected in its v1.1 amendment.)
- **`docs/ARCHITECTURE.md` is *Frozen***: implementation diverging from it is
  "considered incorrect unless the architecture has been explicitly updated
  first". So when the code is right and the doc is wrong, **amend the doc and
  log it** — v1.1 added an Amendment Log for exactly this. `ROADMAP.md` still
  does not exist and is now marked as such.
  `docs/COMPONENT_SPECIFICATIONS.md` has *not* had the same pass and may still
  describe the Generator as `Resume + JDAnalysis + Mode → Resume` with no
  Planner stage.
- **`docs/IMPLEMENTATION_GUIDE.md` is a stub** — eight bare headings.
- **Not installed:** Rich, PyMuPDF, PyYAML. `pdfminer.six` **is** installed as
  of task 016 (see §10f); PyMuPDF was evaluated and rejected as AGPL-3.0.

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

## 10d. LaTeX Renderer (task 014)

`src/renderer/latex_renderer.py`, beside the Markdown serializer. Same shape:
stateless class, banner-comment sections, `List[str]` builders, Python 3.9
typing, no LLM call, no mutation.

```python
LatexRenderer(template_directory="templates").render(resume) -> str
LatexRenderer().render_to_file(resume, "output/resumes/latex") -> Path
```

`render_to_file` writes `{metadata.resume}.tex` and is **the first thing in
`src/` that writes a file** other than config. `output/` is gitignored.

**The templates were not templates.** `templates/` held three hardcoded copies
of the author's real resume — no `{{FOO}}`, no jinja, nothing to preserve. Task
014 was therefore two jobs: author the templates, then write the renderer. The
originals now live untouched in `templates/masterTemplates/`, and
`backend.tex` / `fullstack.tex` / `cybersecurity.tex` are the placeholder
copies. Their preambles (lines 1–156: documentclass, packages, colors,
`\titleformat`, every `\resume*` macro) are byte-identical to the masters, and
`tests/renderer/test_latex_templates.py` pins that.

**Names resolve directly.** `templates/{metadata.template}.tex`, no mapping
dict — which is why the copies are named `backend`/`fullstack`/`cybersecurity`
rather than the masters' `backendDeveloper`/`fullStackDeveloper`.

**Eleven placeholders, all required** (`REQUIRED_PLACEHOLDERS`): five contact
fields plus `CONTACT_EMAIL_URL`, then `SUMMARY`, `SKILLS`, `EXPERIENCE`,
`PROJECTS`, `EDUCATION`. Both directions are checked — a template missing one
raises, and a leftover `{{...}}` after substitution raises. The four structural
placeholders receive **one pre-built block each**, assembled in Python, because
those sections are macro trees (`\resumeSubheading`, nested `\resumeItem`
lists), not string slots.

**Five fields are deliberately dropped**, because the template's design has
nowhere to put them: `Experience.employment_type`, `Experience.technologies`,
`Experience.domains`, `Project.type`, `Project.domains`. They stay runtime-only,
feeding the Planner and Generator without reaching the PDF. This makes the task
doc's "preserve technology order / domain order" requirement **vacuous for
experience** — projects keep theirs via the title parenthetical. Pinned by
`TestDroppedFields` so the omission stays deliberate rather than becoming a
regression someone "fixes".

**Escaping runs before transliteration, and this order is load-bearing.**
Several transliterations emit LaTeX markup of their own (`…` → `\ldots{}`,
`•` → `$\bullet$`); escaping afterwards turned that markup into literal
backslashes and braces. Caught by a test, not by reading. Escaping itself is a
**single regex pass** over the ten specials, so the replacement for `\` cannot
be re-escaped by a later rule — the classic sequential-`replace` bug.

**URLs use a second, narrower escaper.** Inside `\href`'s first argument only
`\ % # { }` are escaped; `_`, `&`, `~`, `?` and `=` must survive or the link
stops resolving. Running a URL through the body-text escaper is the standard
way to corrupt one.

**Unicode: transliterate a known table, raise on the rest.** Output is pure
ASCII, verified. An unknown character raises `RenderingError` naming the field
rather than being dropped.

**An empty list environment is a LaTeX error, not an empty list.**
`\begin{itemize}` with no `\item` fails to compile, so:
- An entity with no highlights emits **no** `\resumeItemListStart` at all.
- Experiences, projects and education **raise** when empty, because the
  *template* opens those environments and the renderer cannot close over
  nothing. The validator already requires 2 experiences and ≥1 education, so
  this is a backstop.
- Skills are safe either way: the template supplies the single `\item`.

**Two things the design gives up, both accepted:**
- **Bold metrics are gone.** The masters hand-bold figures
  (`by \textbf{70\%}`); generated highlights are plain escaped strings. Every
  rendered resume reads flatter than the master. Auto-bolding numbers is a
  layout decision and belongs to the Quality Gate, not here.
- **`CERTIFICATIONS` is static template text** in the backend/fullstack copies.
  The Resume model has no certifications field, so the renderer never touches
  that section. `cybersecurity.tex` has none, matching its master.

**cybersecurity's experience style was normalised.** Its master uses
`\resumeSingleSubheading{Company - Role}{Duration}{}{}`; the copy uses
`\resumeSubheading` like the other two so the renderer emits one block shape
and needs no per-template branching. The master keeps its original look.

**Do NOT emit per-bullet negative vspace. This was tried and it silently broke
the layout.** The masters use `\vspace{-4px}` / `-8px` after project *titles*
and `-12pt` at a section end — structural, one per title. They also sprinkle
negative vspace after *individual bullets*, but only sporadically, hand-placed
document by document to squeeze one particular resume onto one page.

An intermediate renderer reproduced that mechanically: `\vspace{-12px}` after
every project bullet. Roughly -9pt per bullet exceeds the inter-item gap, so
consecutive multi-line bullets **printed on top of each other**. The user caught
it by looking at the PDF.

**Every automated signal said it was fine, and one of them said it was better:**
- pdflatex: exit 0, no warnings — negative vspace never reports overfull.
- Brace balance, ASCII, placeholder checks: all green.
- **Page count went 2 → 1** — because the text was collapsing onto itself
  rather than fitting. The metric improved *because* of the defect.
- A test asserting `pages == 1` passed on the broken document, locking the bug
  in. An assertion satisfiable by destroying the layout is worse than none.

The lesson generalises past LaTeX: **when the success metric can be satisfied by
breaking the thing being measured, the metric is not evidence.** Page count is a
compression measure, and text overlap is infinite compression. `test_latex_overlap.py`
now pins the structural invariant (no trailing `\vspace{-` on a bullet line),
which needs no TeX distribution.

Hand-tuning spacing to reach one page is exactly the layout optimization the
**Quality Gate** owns. The renderer emits structural spacing and stops.

### Toolchain

**TinyTeX**, installed at `~/Library/TinyTeX` (no sudo; `bin/universal-darwin`
appended to `~/.zshrc` and `~/.bash_profile`). Packages beyond the base
install: `preprint` (fullpage), `titlesec`, `marvosym`, `enumitem`, `hyperref`,
`babel-english`, `tools`, `fontawesome5`, `graphics`, `pgf`, `xcolor`,
`cormorantgaramond`, `charter`, `psnfss`, `symbol`, `zapfding`, `etoolbox`,
`fontaxes`. Add a missing one with `tlmgr install <pkg>`; find which package
owns a missing file with `tlmgr search --global --file /<name>.sty`.

`tests/renderer/test_latex_compilation.py` compiles for real and **skips
cleanly when pdflatex is absent**, so the suite still runs anywhere. It pins
one page for all three canonical resumes, compiles every template, compiles
every escaped special character and every transliterated glyph, and asserts
pdflatex reports no `Missing character` — a glyph the font lacks is dropped
silently in the PDF, so the warning is the only signal that content was lost.
Eight tests, ~5 s.

Verified: all three canonical resumes and all five live-generated ones compile
with zero overfull/underfull boxes and zero missing glyphs. **Page counts run to
two**, and that is the honest number — the masters reach one page only through
the hand-tuning described above. Fitting is the Quality Gate's work, and §11
records how much of it there is.

Ad-hoc tailored output lives in `output/tex/` as
`{resume}_{mode}.tex`, written by calling `render()` and saving directly rather
than `render_to_file`, whose `{metadata.resume}.tex` naming would collide
between modes.

Baseline after this task: **825 tests passing** (736 after task 013).

---

## 10e. PDF Compiler (task 015)

`src/compiler/` — `exceptions.py`, `models.py`, `pdf_compiler.py`, `__init__.py`.
A package of its own, **not** part of `src/renderer/`. The renderer's docstring
used to promise "PDF compilation will join them here"; it does not, and that
sentence has been corrected. Rendering produces source, compiling drives a
toolchain, and `docs/ARCHITECTURE.md` lists them as separate modules.

```python
PDFCompiler(engine="pdflatex", timeout_seconds=120).compile(
    latex_source, output_directory="output/compile/attempt_1", job_name="resume"
) -> CompilationResult
resolve_engine("pdflatex") -> str      # public; doctor uses it too
```

No LLM call, no config, no mutation. The first module in `src/` to import
`subprocess`, `tempfile` or `shutil`.

**It raises; it does not report.** `CompilationResult` has no `success` field
because the flag would be `True` on every object that can exist. This is the
one place the house "docstring-only exception bodies" rule is broken:
`CompilationFailedError` carries `exit_code`, `log_path` and `tex_path` as
attributes, because when nothing is returned the diagnostics have nowhere else
to travel and the Revision Engine needs the log path.

```
CompilerError
├─ InvalidCompilationRequest        # empty job name, or one containing a separator
├─ LatexEngineNotFoundError         # no process ever ran
└─ CompilationFailedError           # the engine ran and did not deliver
   ├─ PDFNotGeneratedError
   └─ CompilationTimeoutError
```

Catching `CompilationFailedError` catches all three post-launch failures.

**One temporary directory per call, and that single choice does four jobs.**
Isolation, safe concurrency, "no state from the previous attempt survives", and
no `.aux`/`.out` pollution all fall out of it — by construction, not by cleanup.
Artifacts are copied into the caller-owned `output_directory` afterwards. The
caller owns attempt numbering; the compiler only owns `job_name`.

**Artifacts are preserved *before* the exception is raised.** This ordering is
the whole reason a failed attempt is debuggable — the workspace is about to be
deleted, and the log is the only evidence. True on every failure path, timeout
included. `log_path` always names a file that exists: TeX's own `.log` when it
wrote one, otherwise the captured stdout written to the same path.

**Determinism needed an actual fix, not just a promise.** pdflatex stamps the
wall clock into `/CreationDate` and derives the document `/ID` from it, so
identical source produced byte-different PDFs. `SOURCE_DATE_EPOCH=0` and
`FORCE_SOURCE_DATE=1` are pinned in the engine's environment.
A/B'd before committing to it: **without the pinning two compiles of the same
source differ; with it they are byte-identical.** Pinned by
`TestRealDeterminism`.

**Success is exit 0 *and* a readable PDF — both, because either alone lies.**
Under `nonstopmode` the engine routinely writes a *partial* PDF and exits
non-zero, so PDF-existence alone passes broken documents; and exit 0 does not
prove a file appeared. "Readable" is `is_file()` + non-zero size + the `%PDF-`
magic bytes. No PDF library is involved — PyMuPDF is not installed, and page
counting is the Quality Gate's job.

Note the existing renderer test helper trusted PDF existence and **ignored the
exit code entirely**. Tightening this surfaced no hidden defect: all 8 of its
tests still pass.

**Four flags, every invocation** (`ENGINE_FLAGS`): `-interaction=nonstopmode`
(never block on input), `-halt-on-error` (the log ends at the cause),
`-file-line-error` (`file:line:` — parseable by the Quality Gate),
`-no-shell-escape` (disables `\write18`). The first two match what the renderer
tests already used; the last two are new.

**Timeout, because the budget is real.** A hung compile would eat the whole
180 s run. `DEFAULT_TIMEOUT_SECONDS = 120`; the process is killed and its
artifacts kept. Measured cost is nowhere near it — **~0.5 s per resume**.

**Single pass, deliberately.** These templates use no `\ref`, no
`\tableofcontents` and no hyperref bookmarks, so a second run cannot change the
output. Acting on a "Rerun to get … right" request would be a quality decision.

**The test seam is a `runner` callable, not a mock.** The compiler takes
`runner(argv, cwd, timeout, env) -> (exit_code, output)`, defaulting to the real
subprocess call. `tests/compiler/conftest.py` supplies `FakeRunner`,
`TimeoutRunner` and `WorkspaceProbe`, which write real artifacts into the real
workspace so the compiler's own checks run against real files. Same idea as
`FakeProvider` subclassing `LLMProvider`. The task doc asked for the subprocess
to be mocked; this reaches every branch without a mocking library, and the 49
unit tests need no TeX distribution at all. Engine resolution is exercised with
a genuinely absent name and with `sys.executable`, so even that needs no fake.

`test_compilation_integration.py` (11 tests) drives real pdflatex and skips on
`shutil.which`, matching `test_latex_compilation.py:30-32` — there are no pytest
markers registered in `pyproject.toml`, so `skipif` *is* this project's
"integration test" marker.

**Both earlier copies of the subprocess logic are now consumers.**
`tests/renderer/test_latex_compilation.py` and
`tests/renderer/verify_latex_render.py` both call `PDFCompiler`. Their logs now
come from TeX's transcript rather than captured stdout — verified to be a
superset: compiling a canonical resume gives 658 log lines against 46 of stdout,
and the only stdout-exclusive lines are the banner and path-list line wrapping,
no diagnostics. It also carries `Output written on …`, which `PAGE_COUNT` needs.

**`resume-tailor doctor` now reports the toolchain** (an addition beyond the
task's DoD). It prints the resolved engine path, or a `✗` with a TinyTeX
remediation. **Diagnostic only — it never changes the exit code**, because a
missing TeX distribution still leaves analysis, planning and generation working.
The summary line is now conditional: "All checks passed." only when the engine
is present, otherwise "Provider checks passed. The LaTeX toolchain needs
attention." Only the path is reported; running the engine to read its version
would put a subprocess call in the CLI layer, which that module does not do.
This is why `resolve_engine` is public rather than a private method.

This environment is exactly the case that motivated it: **pdflatex is not on
PATH in a non-login shell.** TinyTeX lives at
`~/Library/TinyTeX/bin/universal-darwin` and is added in `~/.zshrc` /
`~/.bash_profile`, so tooling that shells out with plain `bash` silently skips
every compilation test. Run the suite with that directory prepended to `PATH`,
or the 19 TeX tests do not actually run.

**An engine that resolves but cannot run** — the exec bit set on something that
is not a binary — used to leak a bare `OSError` ([Errno 8] Exec format error).
Now `LatexEngineNotFoundError`. Found by probing whether pdflatex ever writes to
stderr (it does not, in any of valid / broken / missing-package runs, and it
always writes a `.log` — so discarding captured stdout on success loses
nothing).

Baseline after this task: **902 tests passing** (825 after task 014), 883 + 19
skipped without a TeX distribution.


---

## 10f. Quality Gate (task 016)

`src/quality/` — `exceptions.py`, `models.py`, `geometry.py`, `log_analysis.py`,
`checks.py`, `quality_gate.py`, `__init__.py`. Its own package, like the
compiler.

```python
QualityGate(extractor=None, overfull_tolerance_points=0.0)
    .evaluate(pdf_path, latex_path, compiler_result) -> QualityGateResult
    .evaluate_compilation_failure(error) -> QualityGateResult
```

No LLM, no config, no network, no writes, no mutation.

**There are two entry points, and the second is not optional.** The Compiler
*raises* on failure and `CompilationResult` has no `success` field, so a result
object can only ever describe a compilation that worked. Without
`evaluate_compilation_failure`, the `COMPILATION_FAILED` code would be
unreachable outside its own unit test. It takes the `CompilationFailedError`,
reads the preserved log, and opens no PDF — there is none.

**Both stages always run**, and `ARCHITECTURE.md` was amended to 1.2 to say so.
It previously specified Stage 2 as running only when Stage 1 failed, and
`COMPONENT_SPECIFICATIONS.md` additionally listed orphan words as a Stage 1
check — impossible, since the log carries no geometry. Geometry analysis costs
milliseconds; short-circuiting would only hide overlap until the Revision
Engine had spent one of three attempts on the page count.

### The dependency, and why it is the smallest one

**`pdfminer.six`**, pinned `>=20231228,<20251227`. MIT. It **adds no new
packages**: `cryptography` (49.0.0) and `charset-normalizer` (3.4.9) were
already installed. The upper pin is load-bearing — releases from **20251227**
declare `requires-python >=3.10`, and this project is 3.9; pip resolves to
20251107 today, but the pin makes that explicit rather than a future surprise.

Nothing else was available: the venv had no PDF library, and `pdftotext`,
`mutool`, `qpdf`, `gs` and `pdftk` are absent system-wide. TinyTeX ships none of
them. PyMuPDF was rejected as AGPL-3.0, pdfplumber as a Pillow-laden layer over
the same engine, pypdf because it has no line bboxes.

### Two extraction passes, because the checks need opposite things

- **Analysed** (`extract_pages`, default `LAParams`) — line grouping and real
  spaces. Orphans, section attribution, overflow.
- **Raw** (`PDFPageAggregator(laparams=None)` driven directly) — unanalysed
  `LTChar`. Overlap only.

**Layout analysis is what hides superimposed text**: two colliding rows get
merged into one line, and the merged boxes then never intersect. Measured on
the fixture, the analysed pass loses all the collisions. Note
`extract_pages(..., laparams=None)` does **not** give a raw pass — pdfminer
substitutes a default `LAParams()` when it is `None`, so the aggregator has to
be driven by hand.

Three traps in the raw pass: there are **no space glyphs** (TeX kerns via `TJ`,
so a heading extracts as `TECHNICALSKILLS` and must be compared space-stripped);
the only font-size-independent baseline is `LTChar.matrix[5]`, which is
undocumented API and is therefore pinned by a test asserting the ~13.55pt body
leading; and pdfminer logs `CropBox missing` at WARNING, silenced on its own
logger rather than the root.

### Thresholds were measured, not chosen

Calibrated against the nine compiled resumes in `output/compile/` (all
known-good) and `tests/fixtures/latex/overlapping_bullets.tex`, which re-adds
`\vspace{-12px}` after every bullet and reproduces §10d exactly: **1 page, 0
overfull boxes, text colliding.**

| Constant | Value | Measured separation |
|---|---|---|
| `OVERLAP_TOLERANCE_POINTS` | 0.5 | **0 overlapping pairs across all nine**; fixture reports collisions at 1.79, 3.79, 4.69pt. Any value in (0, 1.79) works. |
| `ORPHAN_MAX_WORDS` | 1 | 5 genuine orphans across the nine. Rejects the 2-word skills line `Databases: MySQL`. |
| `ORPHAN_PRECEDING_FILL_RATIO` | 0.85 | Real orphans sit at 0.904–0.932. |

**The orphan fill guard is honest but not load-bearing.** No single-word final
line in the corpus had a low preceding fill, so the guard defends against a
case the sample does not contain. It must stay well under 0.904 because the
template sets `\raggedright`: an unjustified line can legitimately stop a whole
word short, around 0.87.

**Overlap detection is not the same-block rule the plan first proposed.** The
real collisions turned out to be *cross-block* — a bullet's last line hitting
the next section heading — so restricting comparison to one block would have
missed all of them. The rule is: vertically adjacent rows whose ink overlaps by
more than the tolerance **and** whose horizontal ranges intersect. Requiring
both axes is what keeps `\resumeSubheading`'s right-aligned dates (same
baseline, disjoint columns) from registering.

### Section attribution anchors on rules, not heading text

Each `\section` emits exactly one full-width `\titlerule`, so **the rules are
the section boundaries**; heading text only *names* them. Narrow rects are link
underlines and are filtered by width. A heading sits *above* its own rule, so it
is named directly — otherwise the marker walk files every heading under the
previous section, which showed up as `PROJECTS` wrongly reported as overflowing.

The same rules give the text-column width (553.7pt), which is more robust than
the widest-line extent: on a page where every line is short, the extent makes
each line look completely full and silently disables the orphan fill guard.

### Metrics exist so the Revision Engine can act

`page_count`, `overfull_hbox_count`, `max_overfull_points`,
`missing_glyph_count`, `overlap_count`, `orphan_word_count`,
`rule_collision_count`, `total_text_lines`, `overflow_line_count`,
`overflow_height_points`, `overflowing_sections`, `lines_per_section`.

**No `duration_seconds`**, unlike `CompilationResult` — determinism requires
`first == second`, and a wall-clock field breaks it on every run.

**Measured overflow across the nine** (page 1 holds ~70 lines):

| | page 2 lines | |
|---|---|---|
| seven of nine | 3–9 | ≈2–4 bullets |
| backend_aggressive | 26 | ≈10 bullets |
| cybersecurity_aggressive | 15 | ≈6 bullets |

So trimming is a small job for most resumes. Worth knowing before
over-engineering the Revision Engine.

### The trim loop was prototyped, and it works

Driven end to end against real artifacts: compile → evaluate → drop the last
bullet → repeat. `backend_strict` reaches one page and **passes** after two
bullets and three compiles (~1.5s, zero LLM calls). `cybersecurity_strict` does
the same and passes with its three orphan warnings still reported.

**Two constraints the prototype discovered, both needed by task 017:**

- **Never remove an entity's last bullet.** The first attempt broke compilation
  outright: emptying an `itemize` is a LaTeX error, exactly as §10d's renderer
  notes warn. The floor is not only the Validator's minimums.
- **Trimming is coarser than one line per bullet.** Spill went 7 → 7 → 0:
  removing one bullet changed nothing, the next cleared the page. The
  `\resumeSubHeadingListStart` blocks move as a unit rather than reflowing line
  by line. Another reason the recompile loop beats predicting.

### Shortening probably needs no LLM at all

§10b ordered everything trimmable strongest-first *for this purpose*, so "drop
the last bullet" is well defined; at ~0.5s per compile, a trim → recompile →
re-gate loop converges in seconds with zero LLM calls, leaving the 3-revision
budget for real quality problems. Two limits: the Validator's floor (exactly 2
experiences, ≥2 projects, ≥1 skill category, ≥1 education, non-empty highlights),
and the **Summary, which is prose with no last element** — a deterministic
trimmer cannot compress it, only delete it wholesale.

**Resolved (2026-08-30): the revision path needs no LLM at all.** *Still true in
practice — see §10h, where all six live runs converge with zero LLM calls — but
task 017 built the compression path anyway, as defence in depth for a resume
this measurement does not cover.* The summary is
sized correctly at *generation* time instead — 35-45 words, anchors mandatory
(`SUMMARY_TARGET_MIN_WORDS`/`MAX_WORDS`) — which removes the one job that would
have needed a model during revision. Measured: the deterministic trim loop
converges on all three worst live runs — backend_aggressive in 8 bullets,
fullstack_aggressive in 7, cybersecurity_strict in 6 — reaching one page and
passing the gate with zero LLM calls.

**Revision order is not deletion order.** Summary is `revision_order = 1`, but a
deterministic trimmer cannot compress prose, only delete it, which is the worst
trade available. For deterministic trimming the order is Projects → Skills →
Experience.

**Retention floors, set by the user 2026-08-30 — SUPERSEDED 2026-08-31, see
§10h.** The floors below were measured infeasible: three of six live runs could
not reach one page under them. Task 017 relaxed them and the relaxed set is what
ships. Recorded here because the reasoning is still worth reading, and because
the *reason* they failed (a skill category renders as one row, so category
floors buy almost nothing) still holds.

| unit | floor (superseded) |
|---|---|
| bullets per project | 3 |
| bullets, full-time experience | 5 |
| bullets, internship | 3 |
| skill categories | 5 |
| skills within a category | 2 |

**"Failure is not an option" — SUPERSEDED 2026-08-31, see §10h.** This section
required the engine to always deliver a one-page resume. Task 017 reverses it:
the floors are hard, and an unreachable one-page target raises
`OnePageInfeasibleError` rather than being met by breaching one. What survives
is the other half — the engine must return the *changed* resume and must never
report the original failing resume as a success.

**Artifacts.** The Revision Engine owns attempt numbering and layout — it owns
the loop, and the Compiler was built so "the caller owns attempt numbering".
Persist checkpoints, not every iteration: `output/runs/<name>/attempt_1/`,
`final/`, plus a `revision_trail.json` recording each removal with the resulting
page count and spill. Eight intermediate PDFs nobody opens is clutter; the trail
is what gets read.

### The floors and "always one page" cannot both hold by removing bullets

Measured across the six live runs, counting everything the floors allow —
bullets above floor, whole projects removable to the Validator's minimum,
surplus skill categories, and skills trimmed to 2 per category:

| run | spill (lines) | freeable | verdict |
|---|---|---|---|
| backend_strict | 7 | ~3 | **short by 4** |
| backend_aggressive | 18 | ~15 | **short by 3** |
| cybersecurity_strict | 13 | ~13 | just enough |
| cybersecurity_aggressive | 16 | ~20 | ok |
| fullstack_strict | 0 | — | already passes |
| fullstack_aggressive | 16 | ~14 | **short by 2** |

`backend_strict` is the binding case. Note its generated projects hold
`[3, 2]` bullets — one is **already below** the floor of 3, so the floor is not
satisfied by current output, let alone after trimming.

Removing whole skill categories barely helps: a category renders as one row, so
the section is 6-10 lines for 5-8 categories and trimming every category to 2
skills saves only 1-2 lines.

### Bullet length: implemented 2026-08-30, and what it took

Three rules added to **both** the experience and project templates:

```
- Keep each highlight to 15 words or fewer. At most two highlights in your whole
  answer may exceed that, and only where the content genuinely needs it.
- Cut filler, never facts. Numbers, technologies, product names and concrete
  outcomes always stay; phrases like "ensuring seamless integration across
  enterprise applications" go.
- Shorter highlights are not licence to write more of them.
```

**A soft rule does not work, and the reason is the binary threshold.** The first
attempt said "aim for about 15 words; a few may run longer." The model read that
as permission: 13-20 of every 15-21 bullets still exceeded 15 words. Medians fell
from 21-26 to 17-22 — genuinely shorter prose that bought **zero lines**, because
anything over ~15 words wraps to two lines regardless. `fullstack_strict`
actually *regressed* from 1 page to 2: its bullets shrank from 24 to 17 words
(still two lines each) while gaining one more bullet, for a net +2 lines.

Making the allowance **countable** ("at most two in your whole answer") is what
worked. Note it is not obeyed literally — 9-14 bullets still exceed 15 words —
but it moves medians to 16-19 and that is where the lines come from.

**Median word count is the misleading metric here.** The one that predicts pages
is *how many bullets cross the one-line threshold*.

Results across the six runs:

| run | median words | bullets | spill | pages |
|---|---|---|---|---|
| backend_strict | 26 → 18 | 14 → 14 | 7 → **0** | 2 → **1** ✓ |
| backend_aggressive | 24 → 16 | 19 → 17 | 18 → 13 | 2 |
| cybersecurity_strict | 21 → 17 | 19 → 17 | 13 → 5 | 2 |
| cybersecurity_aggressive | 24 → 16 | 20 → 20 | 16 → 16 | 2 |
| fullstack_strict | 24 → 16 | 14 → 14 | 0 → 0 | **1** ✓ |
| fullstack_aggressive | 22 → 19 | 19 → 15 | 16 → 7 | 2 |

**Quantified outcomes survived** — counts went *up* in several runs (13 in
cybersecurity_aggressive), so the "cut filler, never facts" rule held.

**This makes the floors feasible.** Re-running the budget check with the shorter
bullets, 5 of 6 runs can now reach one page within the user's retention floors,
against 2 of 6 before. Only `backend_aggressive` remains short, by ~4 lines.

### The resolution: cut bullet *length*, not bullet *count*

Measured on a real PDF: **a rendered line holds 14-15 words** (108-114 characters
at 11pt in the 553.7pt column). Generated bullets run a **median of 23 words**, so
essentially every bullet wraps to two lines.

A resume carries 14-20 bullets. Bringing them under ~14 words makes each a single
line, saving **14-20 lines** — more than the entire 7-18 line spill, and without
deleting any content.

So both the floors and the one-page guarantee are satisfiable by shortening
bullets at *generation* time, exactly as the summary was retargeted, rather than
deleting more at revision time. It also keeps the revision path LLM-free.

**Carry the summary lesson across:** the band matters more than the target. A
10-word band (35-45) made the model abandon JSON entirely; a 20-word band gave
the length actually wanted. Any bullet budget must be a range with room in it,
measured in both modes across all three pairings before it ships.

**Which experience to trim — DECIDED with the user, 2026-08-30: intern bullets
first, then full-time.** Keyed on `Experience.employment_type`, which every
resume carries (`exp_001` Full Time, `exp_002` Internship in all three) and
which the renderer deliberately drops — so it is available at runtime with **no
coupling to the Planner**, unlike `ExperiencePlan.priority`. This supersedes the
earlier "oldest first" suggestion: same outcome on today's resumes, but semantic
rather than positional, so it survives a resume listing jobs in another order.

**Stated invariant: an internship section is always present.** Confirmed by the
user, not inferred. No fallback is built for its absence — an untestable branch
is worse than a documented assumption — but the trimmer should fail loudly
rather than silently mis-order if it ever stops holding.

**It is a priority, not a shield.** The internship carries only 3 bullets and a
list cannot be emptied, so intern-first yields **at most 2 bullets** while
convergence needs 6-8. Projects, skills and full-time will always be reached.

### Severity: not every finding blocks

`QualityIssue` carries a `severity`, and `passed` is **"no ERROR issues"**, not
"no issues" — the Validator's errors-vs-warnings split. `SEVERITY_BY_CODE` is
the single mapping; `result.errors` and `result.warnings` are convenience views.

**`ORPHAN_WORD` is the only WARNING, and this diverges from the task doc on
purpose.** The brief lists orphan words as a failure. Measured: three of the
nine known-good resumes contain orphans while being clean in every other
respect. `cybersecurity_strict`, trimmed to one page, is otherwise perfect and
carries `'60%.'`, `'validation.'` and `'verification.'` — failing it on those
would be wrong, so they are reported and do not block. Everything else blocks:
an overfull hbox puts text in the margin, a missing glyph means content was
silently dropped, and overlap or a rule through text is a broken page.

Issues sort errors first, so the blocking problem is the first thing read.

### Error versus failure

```
QualityGateError
├─ GeometryUnavailableError   # pdfminer not importable
├─ PDFUnreadableError         # missing, not a PDF, no pages, unparseable
└─ QualityAnalysisError       # log/PDF page counts disagree
```

A failure is `passed=False`; an error raises. An analyzer failure is **never**
reported as a pass. Note the Compiler deliberately accepts a degenerate
`%PDF-1.4\n` with no pages ("the compiler is not the Quality Gate and must not
care") — judging that file is this package's job, and the honest verdict is
`PDFUnreadableError`.

### Testing

`tests/quality/` — 110 tests. `conftest.py` supplies `FakeExtractor`,
`FailingExtractor` and geometry builders, so **every Stage 2 rule is testable
with no PDF, no pdflatex and no pdfminer** — the same seam idea as `FakeRunner`.
Geometry is built in PDF user space (y increases upward), which is easy to get
backwards.

`test_quality_gate_integration.py` (12 tests, `skipif` on pdflatex) carries the
mandatory regression: the broken fixture is **1 page with 0 overfull boxes and
still fails**, on `TEXT_OVERLAP`. It also re-runs the nine known-good PDFs as a
standing false-positive check.

---

## 10g. Pipeline wiring (chain connection)

`src/pipeline/` — `exceptions.py`, `models.py`, `pipeline.py`, `__init__.py`.

```python
ResumePipeline(provider, template_directory="templates",
               quality_gate=None, compiler=None)
    .run(source_resume, job_description, mode, output_directory, job_name)
        -> PipelineResult
    .run_from_file(resume_path, job_description_path, ...)
```

It holds **no logic of its own** — every stage is already tested in isolation.
It exists so the *seams* are tested: whether one stage's output is actually
accepted by the next. That is the break that survives a thousand green unit
tests.

`PipelineResult` keeps **every** intermediate artifact (analysis, plan,
generated resume, markdown, latex, compilation, quality). When a resume comes
out wrong the question is always *which stage did it*, and a result carrying
only the final PDF makes that unanswerable.

**One provider serves every stage**, so a run cannot silently mix models.

**Stage exceptions are not wrapped.** A `PlannerError` reaching the caller
unchanged is more useful than a generic "pipeline failed", and each tree is
already documented. The single exception it *handles* is
`CompilationFailedError` — the Quality Gate has a verdict for that case, so the
run ends in a judgement rather than a traceback, with `compilation=None`.

### Why the Markdown Serializer branches instead of chaining

An earlier version of the chain drew the Markdown Serializer **between** the
Resume Object and the LaTeX Renderer. **It cannot sit there.**
`LatexRenderer.render` takes a `Resume`, not Markdown, so putting it in the data
path means `serialize → parse`, and that round trip is lossy by construction
(§10c). The chain was corrected; this records why, so it is not re-drawn the
old way later.

Measured, not assumed:

```text
before round-trip: [('proj_007', 'GENERATED'), ('proj_002', 'CANONICAL')]
after  round-trip: [('proj_001', 'CANONICAL'), ('proj_002', 'CANONICAL')]
```

`source=GENERATED` has no Markdown representation, and ids are renumbered
positionally on parse. That lineage is exactly what the Revision Engine uses to
decide what it may touch — an invented project may be dropped, a canonical one
may not — so the serializer runs as a **side branch** emitting `generated.md` as
an artifact, and the Renderer is fed the Resume object.

Pinned by `TestTheSerializerIsASideBranch`, so nobody "simplifies" the pipeline
by routing through Markdown later.

### Live baseline: all six runs, both modes, all three resumes

Measured 2026-08-30 on `qwen3.6:latest`, after the aggressive-manifest fix and
the summary retarget. Full chain each time. Artifacts under
`output/runs/<resume>_<mode>/`.

| run | pass | pages | overfull | glyphs | overlap | orphans | lines | spill |
|---|---|---|---|---|---|---|---|---|
| backend_strict | ✗ | 2 | 0 | 0 | 0 | — | 64 | 7 |
| backend_aggressive | ✗ | 2 | 0 | 0 | 0 | — | 74 | 18 |
| cybersecurity_strict | ✗ | 2 | 0 | 0 | 0 | — | 69 | 13 |
| cybersecurity_aggressive | ✗ | 2 | 0 | 0 | 0 | — | 72 | 16 |
| fullstack_strict | **✓** | **1** | 0 | 0 | 0 | — | 59 | 0 |
| fullstack_aggressive | ✗ | 2 | 0 | 0 | 0 | — | 72 | 16 |

Wall clock 65-79s, five LLM calls each. Zero overfull boxes, zero missing
glyphs, zero overlaps throughout.

**Effect of the summary retarget** (band 20-120 → 35-55), same six runs before
and after:

| run | summary words | summary lines | total lines | spill |
|---|---|---|---|---|
| backend_strict | 66 → 47 | 6 → 5 | 65 → 64 | 11 → **7** |
| backend_aggressive | 59 → 36 | 6 → 4 | 76 → 74 | 20 → **18** |
| cybersecurity_strict | 71 → 40 | 7 → 4 | 72 → 69 | 16 → **13** |
| cybersecurity_aggressive | 55 → 50 | 6 → 5 | 73 → 72 | 18 → **16** |
| fullstack_strict | 52 → 50 | 5 → 4 | 60 → 59 | 0 → 0 |
| fullstack_aggressive | 60 → 43 | 5 → 4 | 73 → 72 | 18 → **16** |

Summaries now land at 36-50 words against 52-71 before, and spill drops 2-4
lines per run. Real but modest — it closes roughly a fifth of the gap, which
matches the estimate. The Revision Engine still does the bulk of the work.

**One anchor loss, reported not silent.** `fullstack_aggressive` swapped the
source's named technologies (Java, Spring Boot, Vue.js, Redis, MySQL) for the
job's (Python, FastAPI, LLM Integration). `_report_lost_anchors` caught it and
it surfaced on `generator_discarded` — which is the designed behaviour, since
prose judgement is not a correctness rule and there is no safe way to graft a
fact back into a sentence. Whether it is *caused* by the shorter budget cannot
be established: the pre-change artifacts for that run were overwritten. Note
also that a false alarm looks similar — cybersecurity's summaries carry no years
of experience because the **source** has none, not because anything was lost.

**Page-1 capacity is ~70 text lines.** That is what the Revision Engine trims
toward; the spill column is how far each run has to come down.

### Soft failures must be captured, or they vanish

`PipelineResult` carries `planner_discarded`, `generator_discarded` and
`generator_warnings`. Both stages record these on **themselves** and reset them
on the next call, so a pipeline that does not copy them out loses them
silently — which is exactly what the first live run showed. They are the only
record that the planner dropped a removal naming an absent skill, or that the
generator cancelled a lopsided trade, dropped an emptied category, or wrote a
summary that lost its anchors. None of that is visible in the finished resume.

### Testing

`tests/pipeline/` — 14 tests, offline. `conftest.py` supplies `ScriptedProvider`,
a hand-written `LLMProvider` subclass that dispatches on a marker in the prompt
and returns a canned, schema-valid reply for each of the five calls a run makes.
Replies are **derived from the source resume**, not hardcoded, so they cannot
drift out of sync with the fixtures.

**Trap, already hit:** the obvious markers `"experiences": [` and
`"projects": [` both appear in the *resume context embedded in every generator
prompt*, so dispatching on them silently routes the projects call to the
experiences handler. The markers must come from each prompt's response-schema
block (`"experience_id": "<the id given in the plan>"` and
`"project_id": "<the id given in the plan, or null`).

Confirmed by the chain test, matching §10b: **an all-KEEP plan makes exactly two
LLM calls** (analyze, plan) and none to the generator; a rewriting plan makes
five.

`scripts/live_run.py` is the real thing: one resume, one JD, real LLM calls,
dumping every stage to `output/runs/<name>/` as numbered files
(`00_source_resume.json` … `10_run_summary.md`). Use it to inspect a hand-off.

`verify_pipeline.py` is the lighter live counterpart, not collected by pytest. §9 lesson
6 is why it exists — the planner once shipped with 318 green tests while every
real invocation failed. The offline test proves the stages fit together; only
the live one proves the chain survives a real model's output.

---
---

## 10h. Revision / Shortening Engine (task 017)

`src/revision/` — `exceptions.py`, `models.py`, `floors.py`, `measure.py`,
`deletion.py`, `facts.py`, `prompts.py`, `sampling.py`, `compression.py`,
`revision_engine.py`, `__init__.py`. Its own package, like the compiler and the
gate.

```python
RevisionEngine(provider=None, template_directory="templates",
               renderer=None, compiler=None, quality_gate=None,
               max_compression_passes=3)
    .revise(*, source_resume, current_resume, quality_result,
              output_directory, job_name="resume") -> RevisionResult
```

`provider=None` disables compression entirely, leaving a fully offline,
deterministic engine. Everything else is injectable, matching `ResumePipeline`.

### Four decisions that supersede §10f

Taken with the user on 2026-08-31. `tasks/017-revision-engine.md` and §10f
disagreed on all four; the task doc won each time.

| | §10f said | ships as |
|---|---|---|
| floors | project bullets 3, **categories** 5, skills/category 2 | project bullets 2, **individual skills** 5, projects ≥2 |
| non-convergence | always deliver a one-page resume | raise `OnePageInfeasibleError` |
| LLM | "the revision path needs no LLM at all" | deterministic-first, compression as defence in depth |
| loop bound | — (`ARCHITECTURE.md`: `max_revisions: 3`) | deletions uncapped, **LLM passes** capped at 3 |

The floor relaxation is what makes the one-page guarantee reachable: §10f's own
budget table had `backend_strict` short by 4 lines under the tight floors.
Uncapping deletions is safe because each step strictly shrinks the resume, so
the loop provably terminates; the cap belongs on the LLM calls, which are what
the 180-second budget actually pays for.

**Floors as shipped** (`src/revision/floors.py`, the single home — a test
asserts no other module defines one). They sit *above* the Validator's minimums,
which remain the hard backstop.

| unit | minimum |
|---|---|
| projects | 2 |
| bullets per project | 2, then the project goes whole |
| individual skills, total | 5 |
| protected leading skill categories | 1 (highest priority, never trimmed) |
| internship bullets | 3 |
| full-time bullets | 5 |
| work experiences | exactly 2 |
| bullets in any entity | 1, independent of every other floor |

### Decide and apply are separate, and that is what makes it testable

`deletion.next_removal(resume)` returns the single next legal move or `None`;
`deletion.apply_removal(resume, step)` returns a new resume. Both pure, neither
mutating. The whole deletion policy is therefore exercisable with no renderer,
no compiler, no PDF and no TeX — 48 tests that run in 0.1 s. `removal_plan` and
`freeable_lines` are the same two functions dry-run to exhaustion, so
`freeable_lines` can never disagree with what the engine would actually do.
There is one policy, not a policy and a separate model of it.

### The estimates never decide

`measure.py` estimates rendered lines from a **character budget of 108**, read
off a real PDF in task 016 (a line in the 553.7 pt column holds 14–15 words or
108–114 characters). It sizes the work and picks compression candidates. It
never decides whether the resume fits: every step is rendered, compiled and
re-judged, and `result.passed` is the only stopping signal.

That is not caution, it is measurement. The live trails show it plainly —
spill per attempt, `backend_aggressive`:

```text
13 → 7 → 7 → 7 → 2 → 0
```

Three consecutive removals changed nothing, then one cleared five lines. The
`\resumeSubHeadingListStart` blocks move as a unit rather than reflowing line by
line, exactly as §10f measured. An engine converging on arithmetic would have
declared four of those five steps useless and given up.

Pinned by `test_revision_integration.py::TestTrimmingIsCoarserThanOneLinePerBullet`,
which asserts at least one step frees nothing.

### Removal order, and two readings resolved

```text
Projects → Skills → Experience (Internship → Full-Time)
```

**Projects are trimmed to the floor everywhere before any project is removed.**
The task doc's sentence is global — "Projects must be shortened bullet-by-bullet
before the entire project is removed" — and the per-project reading would delete
a whole two-bullet project while a four-bullet project sat untouched: strictly
more content lost for the same page saving.

**A skills step is never one skill.** A category renders as one wrapping row, so
removing one skill from a twelve-skill category frees nothing. With a floor of
five *individual* skills a 21-skill resume offers sixteen nominal removals worth
almost no lines; taken one at a time that is sixteen wasted recompiles before
Experience is reached. Each skills step therefore removes exactly enough
trailing skills to drop that category's rendered line count, or empties it
outright. `backend_aggressive` converged on a skills step that removed the
one-skill `Databases` category — the cheapest line available.

**The intern-first rule is a no-op on today's resumes.** The floor is 3 and every
internship carries exactly 3, so every experience removal lands on the full-time
role. Documented and pinned, not a defect: §10f flagged the weaker version
("at most 2 bullets"), and the floor closes the gap to zero.

### Measured: all six live runs converge with zero LLM calls

`scripts/replay_revision.py` reloads each run's
`output/runs/<name>/04_generated_resume.json` and drives it through the real
renderer, real pdflatex and the real Quality Gate. No inference, no cost.

| run | pages | spill | steps | attempts | LLM | wall |
|---|---|---|---|---|---|---|
| backend_strict | 1 → 1 | 0 | 0 | 0 | 0 | — |
| backend_aggressive | 2 → **1** | 13 → 0 | 5 | 5 | 0 | 2.7 s |
| cybersecurity_strict | 2 → **1** | 5 → 0 | 2 | 2 | 0 | 1.1 s |
| cybersecurity_aggressive | 2 → **1** | 16 → 0 | 5 | 5 | 0 | 2.7 s |
| fullstack_strict | 1 → 1 | 0 | 0 | 0 | 0 | — |
| fullstack_aggressive | 2 → **1** | 7 → 0 | 2 | 2 | 0 | 1.1 s |

Six of six. §10f's prediction holds, and the LLM compression path is dead code
on real content — which is why it needs synthetic tests and why a live run will
never exercise it. It stays because "no real resume has needed it yet" is not
"no resume can".

`tests/revision/test_revision_integration.py` runs exactly this on every change,
plus the three canonical resumes, with a provider that raises if touched.

**Confirmed live, 2026-09-03.** All six pairings were re-run end to end through
`scripts/live_run.py` against the real provider — fresh analysis, planning and
generation, then revision. Every one lands on one page:

| run | pages | passed | removals | revision LLM calls | wall |
|---|---|---|---|---|---|
| backend_strict | 1 | ✅ | fit already | — | 66.2 s |
| backend_aggressive | 1 | ✅ | 5 | 0 | 75.4 s |
| cybersecurity_strict | 1 | ✅ | 2 | 0 | 70.5 s |
| cybersecurity_aggressive | 1 | ✅ | 5 | 0 | 78.8 s |
| fullstack_strict | 1 | ✅ | fit already | — | 63.5 s |
| fullstack_aggressive | 1 | ✅ | 2 | 0 | 71.8 s |

The three that read `passed: False, pages: 2` in §10g — `cybersecurity_strict`,
`cybersecurity_aggressive`, `fullstack_aggressive` — are the ones this engine
fixed. Wall-clock is dominated entirely by generation; revision costs ~1–3 s.

Determinism held across a repeated run: every LLM reply came back byte-identical
(6675 / 10254 / 307 / 2330 / 2302 chars) and the trail was step-for-step the
same.

`live_run.py` now also writes `11_final_resume.json`, `12_final.tex` and
`13_final.pdf`. Without them the run directory lied: the pipeline compiles
*before* revision, so `07_resume.pdf` is the two-page draft sitting next to a
`passed: true` summary. **A run directory that does not record its own final
artifact will be read as if the draft were the deliverable.**

### The compression path

Reached only when deletion is exhausted and the page still overflows.

- **One consolidated call per pass**, never one per bullet. Pinned.
- **Skills are skipped.** A skill category is not prose; shortening it means
  either deleting skills (that is deletion) or renaming a technology (that is
  mutating a protected fact by definition). A deliberate divergence from the
  task doc's priority list, pinned by a test.
- **Only bullets that already wrap** are eligible. A one-line bullet sent for
  shortening spends facts and buys no space.
- **The prompt omits rather than forbids.** The model never sees the summary,
  education, contact or unselected bullets, so it cannot rewrite them. An id it
  invents is rejected on the way back in.
- **Sampling is greedy** (`compression_options()` = `deterministic_options`
  with a 2048-token budget), unlike the Generator. Compression is constraint
  satisfaction, not writing, so determinism beats variety.

### §11's "no technology lexicon" is false for this one job

§11 records that "recognising 'this word is a technology' needs a lexicon the
project does not have". True for open-ended prose. Not true here: the resume
names its own technologies in `Experience.technologies`,
`Project.technologies`, the skills section and the project names.
`facts.build_lexicon(resume)` is built from those, longest-first so
`Spring Boot` is recognised before `Spring`. Per-run, precise, cannot go stale.

Two classes of fact, verified differently because they fail differently:

- **numerics** — exact string match, whitespace-insensitive (`30 ms` = `30ms`)
  and guarded against a leading digit so `40%` is not satisfied by `140%`.
  Plus the reverse check the task doc implies but does not name: **a number in
  the reply that was not in the original is a fabrication and rejects the
  compression.** That single check is what catches `40% → 50%` twice.
- **terms** — case-insensitive with non-alphanumeric boundaries, so
  `Reduced API Latency` may become `cut API latency` while `Redis → caching`,
  `Spring Boot → a framework` and `OAuth 2.0 → authentication` are all rejected.
  `Java` is not satisfied by `JavaScript`.

Terms shorter than three characters are not protected. `Go` is the known
casualty, accepted: protecting it would protect every "go".

A rejected compression is **not an error** — the original bullet is kept and the
run continues. Rejections are recorded on `RevisionResult.compression_outcomes`,
because a pass that silently kept every bullet and a pass that never happened
look identical in the finished resume.

### The test seam with no precedent in the repo

Every other component here can be faked with canned data. A *convergence loop*
cannot: a canned verdict either always passes or never does. And there was no
compiler in the repo that succeeds without TeX —
`tests/pipeline/test_end_to_end.py::_never_compiles` fakes only a failing
engine.

`tests/revision/conftest.py` supplies the missing half. `StubCompiler` writes
the **real** rendered LaTeX to disk; `CountingGate` reads it back and measures
it. The pairing is faithful rather than convenient: nothing tells the gate what
the resume contained, so a renderer that stopped emitting bullets would break
these tests rather than sail past them.

**One trap, hit during the build.** The first `CountingGate` counted
`\resumeItem{` *occurrences*. That is monotone in deletion and completely blind
to compression — shortening a bullet leaves the macro exactly where it was — so
every compression test failed while the compression path was working correctly.
It now brace-matches each macro's argument and sums `estimated_lines` over the
text. The general lesson is the §10d one again from the other side: **a metric
that cannot move when the thing under test works is not a test.**

### Artifacts

The engine owns attempt numbering; the compiler owns only the job name.

```text
<output_directory>/
    work/                  every attempt compiles here, overwritten
    attempt_<n>/           checkpoints only
    final/                 the accepted resume
    revision_trail.json    every step, including the non-checkpoints
```

Checkpoints are written when the gate passes, after each compression pass, and
on the last attempt before giving up — that last one for the same reason the
compiler preserves its log before raising: the workspace is the only evidence
and it is about to be overwritten. Intermediate attempts share `work/`, per
§10f: eight PDFs nobody opens is clutter, the trail is what gets read.

`OnePageInfeasibleError` carries `spill`, `steps_taken`, `pdf_path` and
`trail_path`, breaking the house docstring-only-exception rule for the same
reason `CompilationFailedError` does: nothing is returned, so the diagnostics
have nowhere else to travel.

### Pipeline wiring

`ResumePipeline(provider, template_directory, quality_gate, compiler, reviser,
revise=True)`. When the gate fails, the engine runs and `result.quality` becomes
the **final** verdict.

- `generated_resume` deliberately keeps its *pre-revision* meaning. When a
  resume comes out wrong the question is always which stage did it, and
  overwriting the generator's output makes that unanswerable.
  `result.final_resume` is what was delivered.
- **Revision is skipped after a compilation failure.** There is no page to
  measure, and the defect is in the document rather than its length.
- **`CompilationFailedError` is not caught inside the engine**, unlike in the
  pipeline. Overflow is the failure this engine handles; a resume that stops
  compiling means a removal broke the document, which is a defect and must
  surface with its log path rather than be absorbed as "still too long".

### Found by this task: generation can arrive already below a floor

The floors govern *trimming*. Nothing in the Generator knows about them, so a
generated resume can arrive below one, and the engine can only decline to make
it worse.

| run | unit | floor | arrived at |
|---|---|---|---|
| `cybersecurity_aggressive` | full-time bullets | 5 | **4** |
| `fullstack_strict` | internship bullets | 3 | **2** |

Both still converge and still pass; the resume is simply thinner than the policy
intends. The invariant the engine can actually promise, and the one the tests
assert, is **"never below the floor, and never below where it started"**.

Closing the gap belongs to *generation*, exactly as bullet length and summary
length were closed there rather than at revision time. Pinned by
`TestGenerationCanArriveBelowAFloor` so it stays visible instead of becoming
folklore.


### Skill-category priority already reaches the deletion policy

A live backend run removed the whole `Databases` row, which reads like a
priority bug and is not one. The chain was already complete:

`Planner` assigns each `skills_plan` a priority → `Generator._apply_skills`
sorts by it, most relevant first ("so the Quality Gate can trim from the
bottom") → `deletion._next_skill_removal` walks categories **bottom-up**.

`SkillCategory` does not carry the priority, so **position is the priority** by
the time revision sees the resume. That is a faithful proxy only because the
Generator's sort is the last thing to touch the ordering — anything that
reorders categories afterwards would silently invert the deletion policy.

`Databases` was removed because the backend JD contains **zero** data-storage
signal (`sql`, `database`, `postgres`, `mysql`, `redis`, `query`, `schema`,
`storage`, `orm`, `persistence` — all zero occurrences), so the Planner ranked
it priority 3, the lowest in the plan, and the source category held one skill
(`MySQL`). Lowest priority, last position, first removed. Working as designed.

**What was missing was the guarantee, not the ordering.** The only skills floor
was resume-wide (≥5 total), so a hungry enough run could have gutted the
*top* category. `floors.PROTECTED_SKILL_CATEGORIES = 1` now makes the leading
category untouchable, and `removable_skills` is bounded twice — by the
resume-wide floor and by how many skills sit outside the protected span.

Verified by construction rather than assertion: the same generated resume with
`Databases` moved to the front (what a DB-heavy posting's priority would
produce) still converges to one page in 5 steps with 0 LLM calls, and takes
`Monitoring & Observability` — the new bottom row — instead. `MySQL` survives.

Raising the constant above 1 costs freeable lines and can turn a convergent
resume into a `RevisionError`. It is a floor, and it belongs in `floors.py`
with the rest.


---

## 10i. Reporter (task 018)

`src/report/` — `exceptions.py`, `models.py`, `reconcile.py`, `gate.py`,
`markdown.py`, `reporter.py`, `__init__.py`. The directory name matches the one
`ARCHITECTURE.md` reserved; the class is `Reporter`, not the `ReportGenerator`
of its Core Interfaces list, because every orchestrator here is named after its
component and "generator" already means something else in this pipeline.

```python
Reporter().build(result: PipelineResult) -> Report
Reporter().render_report(report) -> str      # report.md
Reporter().render_changes(report) -> str     # changes.md
Reporter().render_json(report) -> str        # report.json
Reporter().write(report, directory) -> Dict[str, str]
```

No LLM, no provider parameter, no subprocess, no Markdown parsing, no mutation.
`render()`/`write()` split follows `LatexRenderer`: the caller owns the run
directory, and the three files land flat beside `generated.md` and
`revision_trail.json`.

**Its input is `PipelineResult`, not the task doc's eight arguments.** The
result already carries every one of them — `mode`, `source_resume`,
`job_analysis`, `resume_plan`, `generated_resume`, `quality`, `revision`, and
`final_resume` as a property. Three names in the task doc's suggested signature
do not exist in this repo at all: `Mode` is `PlanningMode`, there is no
`RevisionTrail` model (the trail is `List[RevisionStep]`), and
`quality_gate_results` did not exist — see below.

### The plan is intent; the resume is outcome

This is the whole reason `reconcile.py` exists, and the one thing a naive
Reporter gets wrong. A `ResumePlan` records what the Planner *wanted*. The
Generator then declines part of it (§10b): a `REMOVE` is cancelled unless a
`GENERATE` funded it, a lopsided skill trade is cancelled, an emptied category
is dropped. The Revision Engine then removes more content to reach one page.
Reading the plan at face value states removals that never happened and misses
removals nobody planned.

The join is by **entity-id set membership** across the source, generated and
final resumes, plus the `EntitySource` the Generator stamped. Both are recorded
facts, so this is a join and not a judgement.

| planned | in generated | in final | effective |
|---|---|---|---|
| REMOVE | yes | yes | `REMOVAL_CANCELLED` |
| REMOVE | no | no | `REMOVED` |
| KEEP | yes | yes | `KEPT` |
| REWRITE | yes | yes | `REWRITTEN` |
| anything | yes | no | `TRIMMED_FOR_PAGE_FIT` |
| KEEP/REWRITE | no | no | `DROPPED_UNPLANNED` |

`DROPPED_UNPLANNED` should never occur. It is reported rather than smoothed
into `REMOVED` because it would mean a stage dropped an entity silently.

**A `GENERATE` plan entry cannot be joined from the plan side**: it carries
`project_id=None` / `category_id=None` by model invariant, so there is nothing
to match on. The join runs the other way, off the id the Generator minted and
the `EntitySource` it stamped. No pairing between a `GENERATE` entry and a
resulting entity is ever invented.

### `RevisionResult.gate_results` is new, and the report needed it

The engine computed a full `QualityGateResult` on **every** attempt and kept
only the latest on `_Run.quality`; `pipeline.py` then reassigned
`quality = revision.quality`, so even the pre-revision verdict was lost. The
trail's per-step `page_count`/`spill`/`passed` shows convergence but not *which
check* failed, so the per-attempt, per-check history the task doc asks for was
unbuildable.

Two additive fields close it, with no behaviour change:

- `RevisionResult.gate_results: List[QualityGateResult]` — appended in
  `_attempt`, one per attempt, in order.
- `PipelineResult.initial_quality: Optional[QualityGateResult]` — the verdict
  that triggered the revision.

The reported history is `[initial_quality] + revision.gate_results`. Note the
engine numbers its attempts from 1 and so does the pipeline's own compile, so
each attempt carries a `label` ("initial compile", "revision attempt 1") —
without it a report shows two "attempt 1"s.

`revision_trail.json` is unaffected: `_Run.write_trail` builds an explicit
payload rather than dumping the result, so the nine gate results do not bloat
the one artifact that actually gets read.

### Checks are read, never re-decided

`result.passed` is copied verbatim rather than recomputed from the per-check
lines, so the report cannot disagree with the gate about the outcome. Each
check's status comes from the issues themselves:

| line | source |
|---|---|
| Compile | no `COMPILATION_FAILED` issue |
| Page count | `metrics.page_count`; FAIL iff `INVALID_PAGE_COUNT` |
| Overfull boxes | issue presence, count from `overfull_hbox_count` |
| Missing glyphs | issue presence, count from `missing_glyph_count` |
| Layout overlap | issue presence, count from `overlap_count` |
| Rule/text collision | issue presence, count from `rule_collision_count` |
| Orphan words | issue presence, count from `orphan_word_count` |

**Severity comes from the issue, not from the check name.** Reading each
issue's own `severity` means `ORPHAN_WORD` renders as a non-blocking WARNING
with no special case, and cannot drift if `SEVERITY_BY_CODE` ever changes.

**A check that never ran is not a check that passed.** A compilation failure
returns a Stage 1 verdict with every geometry metric at zero, so overlap, rule
collisions and orphans would read "0 findings" when no PDF was ever opened.
Those render `NOT_REACHED`, gated on `stage_reached`. This is the same class of
error as §10d's page-count-went-2→1: a metric that looks clean because the
measurement never happened.

### N:M bullets, so no diff

`ARCHITECTURE.md` showed `changes.md` as a before/after line diff of one
bullet. That is not buildable. The Generator rewrites a whole entity at once,
so N source bullets map onto M new ones with no correspondence between them —
the same reason task 011's `highlight_indices` would not have worked (§10b).
`changes.md` lists `bullets_before` and `bullets_after` in full, unpaired, and
diffs neither. Amended in `ARCHITECTURE.md` 1.5.

Set diffs over *structured fields* are a different matter and are reported
exactly: technologies, domains and skills added and removed, order-preserving,
computed as list comprehensions rather than by iterating a `set()` — a `set()`
would make the output order-unstable and break determinism.

**"Metrics Added" and "Achievements Added" are not reported**, though
`ARCHITECTURE.md` listed both. Deciding what counts as a metric or an
achievement is a judgement, and the Reporter is forbidden from judging resume
content. Logged in the Amendment Log rather than quietly skipped.

### Determinism, and the test that nearly missed it

No timestamps, no durations, no random ids — same rule as `QualityGateResult`
and `RevisionResult`, and for the same reason: `first == second` has to hold.

Two subtler hazards:

- **`SectionPriority` serialises as `3`, not `"MEDIUM"`** (§10). `PlanEntry`
  stores `priority` as the enum's *name*, and the raw plan is deliberately not
  embedded in `report.json`. Pinned by a test asserting `"priority 3"` never
  appears in `report.md`.
- **Artifact paths are absolute and vary per run.** `RevisionSummary` stores
  them relative to the run directory, derived from `trail_path`'s parent.
  **A determinism test that builds twice into the same directory does not catch
  this** — it needs two different roots, which is what
  `test_two_run_directories_produce_the_same_json` does.

### `live_run.py` no longer hand-rolls a report

`10_run_summary.md` was ~60 lines of report logic inline in a script: quality
verdict, revision table, soft failures. The Reporter subsumes all of it, and
the script now writes `14_report.md`, `15_changes.md` and `16_report.json`.

What stayed behind is `10_run_provenance.md`: resume path, JD path, model name,
wall clock and per-call timings. **Those cannot go in the report** — they are
exactly the non-deterministic fields the report must not carry.

### Soft-failure notes are filed under the entity they name

The Planner's and Generator's discarded-notes are prose strings, and they are
the only record that part of the plan was declined. `attach_soft_failures`
files each one under the entity whose **runtime id it names**, matched as a
substring. That is safe because ids are unambiguous tokens — `skill_005` cannot
be mistaken for anything else in a sentence — and the prose itself is never
parsed. A note naming no id attaches to nothing and still reaches the reader
through `report.md`'s soft-failures section.

This is what makes a reconciled action actionable. The live backend run reports
`skill_005 Concepts — planned REWRITE, effective REWRITTEN` with no visible
change, which looks like a no-op until the two notes filed beneath it explain
it:

```text
- skill_005: skill 'Secure Coding' names an activity, not a technology
- skill category skill_005 ('Concepts'): removal of 'API Design', ... was
  cancelled — only 3 skill(s) were available to replace them
```

That is §10b's "nothing is deleted unless something replaces it" and the
lopsided-trade split, visible in the report for the first time: the plan asked
to rename `skill_005` to *Software Engineering Practices*, and what actually
happened is that `skill_005` was left intact and the incoming skills became a
new `GENERATED` category, `skill_006`.

### Confirmed live, 2026-09-03

`backend_aggressive`, the richest trail of the six runs. Full chain, real
provider, 75.2 s wall clock, five LLM calls, **1 page, passed**.

The reported attempt history reproduces §10h's measurement exactly:

| attempt | action | entity | pages | spill |
|---|---|---|---|---|
| 1 (initial compile) | — | — | 2 | 13 |
| 2 | `REMOVE_BULLET` | `proj_001` | 2 | 7 |
| 3 | `REMOVE_BULLET` | `proj_001` | 2 | 7 |
| 4 | `REMOVE_BULLET` | `proj_003` | 2 | 7 |
| 5 | `REMOVE_BULLET` | `proj_003` | 2 | 2 |
| 6 | `REMOVE_SKILL_CATEGORY` | `skill_003` | 1 | 0 |

`13 → 7 → 7 → 7 → 2 → 0`, including the three consecutive removals that free
nothing. **A report that showed only the final verdict would make those three
steps look like a defect**; the per-attempt history is what shows the
subheading blocks moving as a unit.

Three reconciliations in that run are the ones a plan-only report would get
wrong:

- `proj_002 SOCrates` — planned `REMOVE`, **REMOVED**. Honoured, because the
  `GENERATE` funded it.
- `skill_003 Databases` — planned `KEEP`, **TRIMMED_FOR_PAGE_FIT**. Removed by
  the Revision Engine, not by the plan. §10h explains why it was the row that
  went: lowest priority, last position.
- `proj_003 Service Mesh Simulator` — **GENERATED**, reported as "created by
  the Generator" rather than as a planned `GENERATE`, because the `GENERATE`
  entry carries no id and the pairing does not exist.

**All six pairings, 2026-09-03.** Re-run end to end through `scripts/live_run.py`
after the Reporter shipped. Every one lands on one page and passes, and the
reported spill progressions **reproduce §10h's table step for step**:

| run | pages | attempts | spill progression | removals | LLM | generated | soft failures |
|---|---|---|---|---|---|---|---|
| backend_strict | 1 ✅ | 1 | `0` | 0 | 0 | 0 | 9 |
| backend_aggressive | 1 ✅ | 6 | `13 → 7 → 7 → 7 → 2 → 0` | 5 | 0 | 4 | 3 |
| cybersecurity_strict | 1 ✅ | 3 | `5 → 5 → 0` | 2 | 0 | 0 | 6 |
| cybersecurity_aggressive | 1 ✅ | 6 | `16 → 14 → 12 → 9 → 5 → 0` | 5 | 0 | 2 | 3 |
| fullstack_strict | 1 ✅ | 1 | `0` | 0 | 0 | 0 | 10 |
| fullstack_aggressive | 1 ✅ | 3 | `7 → 7 → 0` | 2 | 0 | 1 | 3 |

Wall clock 62.8–78.5 s, five LLM calls each, **zero** revision LLM calls across
all six — §10h's "the deterministic path needs no model" holds again.

**Four reconciliations a plan-only report would have stated falsely.** These are
the cases that justify `reconcile.py` existing at all:

- `cybersecurity_strict` — `skill_002 AI and Automation` planned `REMOVE`,
  effective **`REMOVAL_CANCELLED`**. STRICT emits no `GENERATE` anywhere, so
  nothing could fund the removal and the Generator cancelled it. A report
  reading the plan at face value would claim the category was removed when it
  is still on the delivered resume.
- `cybersecurity_aggressive` — two `REMOVE`s, one `GENERATE`: `skill_001` was
  removed and `skill_002` cancelled. Exactly §10b's "each successful GENERATE
  funds exactly one REMOVE", visible in a report for the first time.
- `backend_aggressive` — `skill_003 Databases` planned `KEEP`, effective
  **`TRIMMED_FOR_PAGE_FIT`**. Removed by the Revision Engine, not by the plan,
  for the reason §10h records: lowest priority, last position.
- `fullstack_aggressive` — `proj_003 Vector RAG Pipeline` carries
  `source: GENERATED` **and** effective `TRIMMED_FOR_PAGE_FIT`. The Generator
  invented a project and the Revision Engine then deleted it to reach one page.

**That last one is worth acting on, and nothing before the Reporter could see
it.** A generation call was spent on a project that never reached the PDF. The
plan, the trail and the final resume each hold one third of the story; only the
reconciliation puts them together. Whether it is worth fixing is a *generation*
question — the same shape as §10h's "generation can arrive already below a
floor" — and the honest position is that one observation is not a pattern.

Determinism held across three consecutive runs: every LLM reply came back
byte-identical (6675 / 10254 / 307 / 2330 / 2302 chars — the same figures
§10h recorded), and the three report files were identical each time.

### Testing

`tests/report/` — 58 tests, none skipped, no provider and no TeX distribution
needed. That is unusual here: `tests/pipeline` and `tests/quality` both skip
without pdflatex.

Resume, plan, job-analysis and gate-verdict builders are **imported from the
packages that already own them** — `make_resume`/`passing_result`/
`failing_result` from `tests/revision/conftest.py`, `make_plan` from
`tests/generator/conftest.py`, `make_job_analysis` from
`tests/planner/conftest.py`. Cross-package conftest imports are new in this
repo (`tests` is a package, so they resolve); a second copy of `make_resume`
would have been one more thing to keep in step with the models. `skill_sizes=(4, 4)`
is the default in `make_source_resume` because that is what makes the revision
fixture's ids line up with the ids `make_plan` plans for.

`test_engine_history.py` drives the **real** `RevisionEngine` with
`StubCompiler` + `CountingGate` and asserts `gate_results` agrees step-for-step
with the trail — the upstream change is verified through the engine, not just
asserted on a hand-built model.

The no-LLM invariant has no provider to fake, so it is checked where it can
actually be broken: `test_the_package_makes_no_llm_call` scans every import
line in `src/report/` for `provider`, `prompts`, `sampling` and `subprocess`.
Same shape as `tests/revision/test_floors.py`'s "single home" test.

## 11. Known open items

- **FIXED: nothing produced a report.** `src/report/` (§10i) now emits
  `report.md`, `changes.md` and `report.json`, and `scripts/live_run.py` writes
  them as `14_report.md` / `15_changes.md` / `16_report.json`. The ~60 lines of
  report logic that used to sit inline in that script are gone; what stayed is
  `10_run_provenance.md`, holding the wall clock, model name and per-call
  timings that a deterministic report must not carry.

- **NEW (task 018): still no CLI, and now three more artifacts nothing on the
  command line can produce.** `ResumePipeline` plus `Reporter` is the whole
  chain, and the only entry points remain Python and `scripts/live_run.py`.
  This is the same gap §11 has recorded since task 013; the Reporter does not
  widen it, but it does mean the report is only reachable from code. That
  command is still what should trigger `src/cli/_common.py`.

- **NEW (task 018): `EffectiveAction.DROPPED_UNPLANNED` has never been
  observed.** It fires when an entity is absent from the generated resume
  although no plan entry asked for its removal. There is no known path to it —
  the planner guarantees total coverage and the generator only grows the resume
  — so it exists as a tripwire. If it ever appears in a real report, a stage is
  dropping entities silently and that is the bug to chase, not the report.

- **NEW (task 018): the report describes the run, and cannot describe a run
  that never finished.** `OnePageInfeasibleError` propagates out of the
  pipeline, so there is no `PipelineResult` and therefore no report for the one
  case a reader would most want explained. The evidence in that case is the
  exception's own `pdf_path` and `trail_path` plus `revision_trail.json`.
  Closing this would mean the pipeline catching that error and returning a
  failed result, which is a change to task 017's contract, not to the Reporter.

- **NEW (task 018): `report.json` embeds `JobAnalysis` whole but projects the
  plan, and the asymmetry is deliberate.** `JobAnalysis` is flat, has no
  free-text field and no int-valued enum, so embedding it avoids a second
  representation to keep in step. `ResumePlan` cannot be embedded as-is:
  `SectionPriority` is an `IntEnum` and serialises as `3` rather than
  `"MEDIUM"` (§10), and the plan addresses entities by runtime id only, so it
  cannot say which project `proj_002` is. `PlanEntry` therefore carries the
  priority *name* and the entity's label. Do not "simplify" this by embedding
  the plan.

- **NEW: a crashed `live_run.py` leaves the previous run's artifacts looking
  current.** The output directory is keyed on resume stem + mode and is written
  incrementally, so a run that dies early — a mistyped JD path, a provider
  timeout — leaves the *prior* run's `10_run_summary.md` in place with no marker
  that it is stale. Hit while re-running the cybersecurity pairing, whose JD is
  `application-software-developer.md`, not a `cybersecurity.md` (there is no
  such fixture). Harmless when watching the console; a trap for an unattended
  batch. A stamp written first and cleared last would close it.

- **FIXED: AGGRESSIVE mode could not plan the backend pairing (0/4).**
  Found by the first real end-to-end run (2026-08-29) against
  `content/backend_resume.md` + `tests/fixtures/job_descriptions/backend.md` on
  `qwen3.6:latest`, and fixed the same day with an aggressive-specific entry
  manifest. The planner decodes greedily, so the failure was deterministic, not
  flaky.

  **It falsified a recorded claim.** `src/planner/prompts.py` stated
  "Aggressive never exhibited the bleed, so it gets no manifest. Adding one
  there is a regression." That over-read its own data: the A/B behind it used
  only the cybersecurity pairing, and what the numbers actually showed was
  narrower — the *strict* manifest is wrong for aggressive, because its exact
  counts leave nowhere to put a GENERATE entry.

  Two distinct failures, both measured on the backend pairing, 4 trials each:

  | condition | result | failure |
  |---|---|---|
  | no manifest (as shipped) | 0/4 | `project_plans[2].new_category_name` — the *skills* shape bleeding into a project entry |
  | strict manifest forced on | 0/4 | `project_plans[1]` — `GENERATE requires project_id to be null` |

  The fix is `_AGGRESSIVE_ENTRY_MANIFEST_TEMPLATE`: pin the ids *and* say where
  a new entry goes — "one entry for each of these ids, in this order; after
  those, append one extra entry for each NEW one, with `project_id: null`".
  Positional, not a bare count hedge; the earlier "plus one entry per GENERATE"
  wording returned unbalanced JSON 4/4. It also names which field belongs to
  which array, which is what stops the bleed.

  Re-measured across three pairings, before and after, 4 trials each:

  | pairing | mode | before | after |
  |---|---|---|---|
  | backend | STRICT | 4/4 | 4/4 |
  | backend | AGGRESSIVE | **0/4** | **4/4** |
  | cyber+appdev | STRICT | 4/4 | 4/4 |
  | cyber+appdev | AGGRESSIVE | 4/4 | 4/4 |
  | fullstack | STRICT | 4/4 | 4/4 |
  | fullstack | AGGRESSIVE | 4/4 | 4/4 |

  Guards: the STRICT prompt is **byte-identical** before and after (diffed
  against `git HEAD`), so strict cannot have regressed; the aggressive diff is a
  pure insertion. And GENERATE still works — backend plans 5 skills into 7
  entries (2 GENERATE) and 2 projects into 3, with `experience_plans` still
  pinned at exactly 2. A manifest that silently suppressed GENERATE would have
  scored 4/4 while turning aggressive into strict.

  **The lesson, which is the part worth keeping: a mode boundary drawn from one
  resume/JD pairing is a hypothesis, not a result.** Measure across pairings
  before concluding a mode is unaffected. This is §9 lesson 8 one level up — it
  says measure every mode a prompt change touches; this adds *and every pairing
  you would generalise over*.

- **`src/cli/_common.py` is not extracted.** `analyze.py` and `plan.py` already
  duplicate ~60 lines of provider bootstrap + error ladder. A third CLI command
  should trigger the extraction.
- **RESOLVED: no bullet-level targeting in the plan, and none is needed.** Plan
  models address whole entities; there is no `highlight_indices: List[int]`.
  §10f argued the Revision Engine mostly would not need it, and §10h confirms
  it: the engine needs an *order* over removable content, which
  `_order_highlights` already guarantees per entity, plus a recompile to tell it
  whether the removal helped. Six of six live runs converge without it.

- **DECIDED: which experience to trim first.** Intern bullets, then full-time,
  keyed on `employment_type`. An internship is a stated invariant. See §10f.

- **Nothing persists the quality report, and `revision_trail.json` is what
  replaced it.** `ARCHITECTURE.md` describes `attempt_N_report.json` in the
  attempt directory. The gate still deliberately writes nothing — the caller
  owns the attempt directory — and the Revision Engine, which is that caller,
  records each step's page count and spill in the trail instead. One file that
  gets read beats one per attempt that does not.
- **NEW (task 017): generation can emit a resume already below a retention
  floor.** `cybersecurity_aggressive` arrives with a 4-bullet full-time role
  against a floor of 5, `fullstack_strict` with a 2-bullet internship against a
  floor of 3. The floors govern *trimming*; nothing in the Generator knows about
  them, and the Revision Engine can only decline to make a violation worse.
  Both runs still reach one page and pass. Closing this belongs to generation —
  a minimum-bullets rule in the experience prompt, the way bullet length and
  summary length were fixed there. Pinned by
  `tests/revision/test_revision_integration.py::TestGenerationCanArriveBelowAFloor`.

- **NEW (task 017): the LLM compression path has no live coverage.** All six
  runs converge deterministically, so `src/revision/compression.py` and
  `src/revision/prompts.py` are exercised only by synthetic tests. The prompt
  has never met a real model. §9 lesson 6 — offline tests are not evidence — is
  unresolved for exactly this one path, and the first resume that needs it will
  be its first live trial. A cheap mitigation if it ever matters: force the path
  by running `RevisionEngine` with an artificially tight gate against a real
  provider.

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

- **`output/compile/` is a third artifact root**, joining `output/tex/` and
  `output/resumes/latex/`. All are under the gitignored `output/`. The
  compiler's `DEFAULT_ARTIFACT_DIRECTORY` is only a default — the caller passes
  whatever attempt directory it wants, and the Revision Engine will.

- **FIXED: `docs/ARCHITECTURE.md` is now amended to v1.1** and carries an
  **Amendment Log** recording every correction and its reason. It is still
  marked *Frozen*; the log is what makes an edit to a frozen document
  auditable. Corrected in this pass: artifacts moved from flat
  `artifacts/attempt_1.pdf` to nested `output/compile/<attempt>/`; Python 3.12+
  → 3.9; PyYAML → TOML + keyring; Rich and PyMuPDF marked not adopted;
  `generated/`, `artifacts/`, `logs/` and top-level `prompts/` removed as never
  created; `src/models/` and `src/utils/` removed in favour of what exists;
  `src/compiler/`, `src/validation/`, `src/config/`, `src/helpers/` added; the
  Compiler section expanded to its real contract; `ROADMAP.md` marked not
  written and `IMPLEMENTATION_GUIDE.md` marked a stub.

  Two `docs/` gotchas listed in §10 are therefore resolved. **Still open:**
  `docs/COMPONENT_SPECIFICATIONS.md` has not been re-checked against the code,
  and `docs/IMPLEMENTATION_GUIDE.md` remains a stub.

- **FIXED: the compiler cannot tell a good PDF from a bad one, by design.** It
  answers only "did the engine produce a readable PDF". Every one of the §10d
  failure modes — overlapping bullets, two pages, overfull boxes, dropped
  glyphs — compiles with exit 0 and passes every check the compiler makes. The
  Quality Gate (§10f) now catches all four: the log gives it overfull boxes and
  missing glyphs, the PDF gives it overlap and page count.

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
  Compilation itself turns out to be cheap — **~0.5 s per resume**, so four
  attempts cost about 2 s of that 110 s. The budget pressure is all in the LLM
  calls.
- **There is now an end-to-end chain, but still no CLI.** `src/pipeline/`
  connects analyze → plan → generate → serialize → render → compile → judge →
  revise,
  and `tests/pipeline/` runs it offline on every change. What is still missing
  is a *command*: no `resume-tailor` subcommand drives it, so the entry point
  is `ResumePipeline` in Python or `tests/pipeline/verify_pipeline.py`. That
  command is what should trigger the `src/cli/_common.py` extraction.

- **`resume-tailor generate` does not exist.** The CLI was out of scope for
  task 012; `tests/generator/verify_generation.py` is the only way to drive the
  generator live. That command should also trigger the `src/cli/_common.py`
  extraction. The serializer is what it will write its output with.
- **FIXED: nothing wrote `generated.md`.** `ResumePipeline` now does, as a side
  branch. Task 013 built the serializer but no caller. `LatexRenderer.render_to_file` (task 014) and `PDFCompiler.compile`
  (task 015) are the only writers so far, and only the verify scripts call them
  — there is still no CLI path from a job description to a file on disk.
  `resume-tailor doctor` gained a LaTeX *check* in task 015 but no command
  produces a PDF.
- **FIXED: everything overflowed one page, in both modes.** The Revision Engine
  (§10h) now trims every one of the nine to one page in 1–3 seconds with zero
  LLM calls. The measurement below is what it trims *from*, and is still the
  right starting point for judging whether a change made fitting harder.
  Re-measured in task 016 through the Quality Gate's own extractor: page 1
  holds ~70 text lines, and **seven of the nine compiled resumes spill only 3–9
  lines onto page 2** (≈2–4 bullets). The two exceptions are
  `backend_aggressive` at 26 lines and `cybersecurity_aggressive` at 15. All
  nine still report zero overfull boxes, zero missing glyphs and zero text
  overlap.

  Strict mode overflows too, so this is not an aggressive-mode problem — the
  *source* resumes already need hand-tuning to fit, and the generator only
  grows them.

  (Earlier versions of this note recorded page counts taken while bullets were
  overlapping — see §10d. Those are all invalid. The task 015 correction, "all
  nine run to two pages", still holds; task 016 adds *how far* over.)

  So trimming is on the critical path for essentially every resume, but it is a
  small job for most of them. §10f records why it likely needs no LLM.

- **FIXED: the strict-mode shape bleed on cybersecurity_resume.** It was §9
  lesson 2 one array further on — the model duplicated the *projects* into
  `experience_plans` wearing the skills shape (`experience_id: "proj_001"`
  carrying `new_category_name`/`skills_to_add`, action `REMOVE`), giving 4
  entries where the resume has 2. Trigger: 6 skill categories (others have 5)
  and a poorly-matched JD making the leading entries `REMOVE`, so the
  "REMOVE + skills shape" pattern ran past the array boundary.

  The prose rule "Exactly one entry per experience" was already in the prompt
  and did not hold. The fix is the strict-only `_entry_manifest` — exact ids per
  array, computed from the resume, placed last. All six pairings now pass 4/4
  (24/24 trials); see §9 lesson 8 for why it is strict-only.
- **`""` and `None` are indistinguishable through Markdown.** An optional
  scalar holding `""` is omitted and re-parses as `None`. Emitting
  `Location: ` with a trailing space would preserve it, at the cost of trailing
  whitespace and a value the parser strips to `""` anyway. Accepted: an empty
  optional field and an absent one mean the same thing on a resume.
- **Leading/trailing whitespace inside a field value does not survive.** The
  parser strips it. The serializer emits values verbatim and does not raise,
  because the loss is cosmetic — unlike the three silent-truncation cases,
  which do raise.
