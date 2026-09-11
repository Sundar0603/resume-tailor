This document is the authoritative source for all architectural decisions in Resume Tailor CLI. If implementation diverges from this document, the implementation is considered incorrect unless the architecture has been explicitly updated first.

Resume Tailor CLI v1.0

**Version:** 1.6

**Status:** Frozen

**Last Updated:** 2026-09-04

## Amendment Log

This document is Frozen: implementation may not diverge from it, but the
document itself may be corrected when it is found to describe something the
project never built. Each entry below records such a correction.

**1.6 — 2026-09-04**

- *The tailoring command is `resume-tailor tailor`, not bare `resume-tailor`* —
  the CLI section shows `resume-tailor --resume backend` and
  `resume-tailor --mode aggressive`, a root command carrying the run's options.
  What shipped is a subcommand, `resume-tailor tailor [--resume PATH]
  [--jd PATH] [--mode ...]`, beside `doctor`, `analyze` and `plan`. Reason: the
  root app was already a `typer.Typer` with `no_args_is_help=True` and three
  registered subcommands by task 011; making the fourth a root command would
  have meant a different shape for the one command that does the most, and
  `no_args_is_help` would have had to go. Required by
  `tasks/019-cli-implementation.md`.
- *`--resume` takes a path, not a shorthand name* — `--resume backend` implies
  a name resolved against a known set. Resumes are discovered dynamically from
  the content directory (`--content-dir`, default `content/`), because the
  project supports an arbitrary number of them and nothing may hardcode their
  names. Omitting `--resume` lists what is there and prompts; a single resume is
  selected without a prompt.
- *Pasting a job description is not "Later"* — the CLI section defers
  `pbpaste | resume-tailor` to a later phase. `tailor` reads a pasted job
  description from stdin to EOF by default, which is the workflow
  `resume-tailor analyze` has used since task 010; `--jd PATH` is the
  alternative, matching `plan`.
- *A run's artifacts live in a timestamped directory* — `output/runs/<stem>_<mode>_<YYYYMMDD-HHMMSS>/`.
  Reason: runs must not overwrite one another, and a name carrying only resume
  and mode leaves a crashed run's stale report beside the next run's PDF with
  no marker (PROJECT_KNOWLEDGE §11).
- *The pipeline gained a progress callback and a post-revision validation
  stage* — `ResumePipeline.run` takes an optional `on_stage` callback,
  announcement-only, so a CLI can report progress across a 60–80 s run without
  re-implementing the chain. It also re-validates the resume the Revision
  Engine returns, against the original source, raising
  `FinalResumeValidationError`. Reason: the Revision Engine deletes content and
  checks only its own retention floors, never the Validator; the floors sit
  strictly above the Validator's minimums, so this is a tripwire rather than an
  expected failure. Required by `tasks/019-cli-implementation.md` §9.

**1.5 — 2026-09-03**

- *Reporter artifacts* — a run now produces **three** report files, not two:
  `report.md`, `changes.md` and `report.json`. Reason: this document specified
  only the two Markdown documents, and a machine-readable record was needed so
  the report could be diffed and asserted on without parsing prose. Required by
  `tasks/018-reporter.md`.
- *`changes.md` is a structured change record, not a textual diff* — the
  example in the Reports section shows a before/after line diff of one bullet.
  The Reporter shows the source and final bullet lists side by side and diffs
  neither. Reason: the Generator rewrites a whole entity at once, so N source
  bullets map onto M new ones with no correspondence between them
  (PROJECT_KNOWLEDGE §10b). A line diff would have to invent a pairing that
  does not exist. Structured lineage — planner actions, the revision trail,
  runtime entity ids and `EntitySource` — replaces it.
- *"Metrics Added" and "Achievements Added" are not reported* — the `report.md`
  example lists both. Technologies, domains and skills added or removed are
  reported, as exact set diffs over structured fields. The other two are not,
  because deciding what counts as a metric or an achievement is a judgement,
  and the Reporter is explicitly forbidden from making judgements about resume
  content — a decision like that belongs to the stage that owns the content.
  The Generator already counts quantified bullets for its own purposes
  (`_report_unquantified`).
- *Reporter directory and interface names* — the reserved directory `report/`
  is now built and holds `class Reporter`, not `ReportGenerator` as the Core
  Interfaces list names it. Reason: every orchestrator in this project is named
  after its component (`QualityGate`, `RevisionEngine`, `PDFCompiler`,
  `LatexRenderer`), and `ReportGenerator` would additionally read as a
  *generator*, which is a different stage in this pipeline.
- *Quality Gate directory* — the reserved `quality_gate/` shipped as
  `src/quality/` in task 016. Recorded here because the directory listing in
  this document was never corrected at the time.

**1.4 — 2026-08-31**

- *Revision budget* — `max_revisions: 3` is now a cap on **LLM revision passes
  only**, not on render→compile→judge iterations. The Revision Engine's
  deterministic deletion loop is uncapped. Reason: the budget exists to bound
  *inference*, which is what the 180-second run budget actually pays for. A
  compile costs ~0.5s, and task 016 measured spill going `7 → 7 → 0` — removals
  that individually free nothing, because the subheading blocks move as a unit.
  Convergence needs 2–5 removals on the six live runs, so a hard cap of three
  cycles would fail runs that otherwise pass. The deterministic loop is provably
  terminating: every step strictly reduces the resume.
- *Revision behaviour on failure* — the engine raises `OnePageInfeasibleError`
  when one page is unreachable without breaching a retention floor. Reason: an
  earlier note in PROJECT_KNOWLEDGE §10f required it to always deliver a
  one-page resume; the user reversed that on 2026-08-31. The floors are hard,
  and a loud failure beats a silently two-page resume or a silently gutted one.
- *Revision order* — `revision_order` (Summary 1, Projects 2, Skills 3,
  Experience 4) is the order sections would be *rewritten* in. It is **not** the
  deletion order, which is Projects → Skills → Experience. Reason: a
  deterministic trimmer cannot compress prose, only delete it wholesale, so the
  Summary is never a trim target; its length is fixed at generation time
  instead. Recorded because the two orderings disagree at the first entry and
  the difference is easy to misread as a bug.

**1.3 — 2026-08-29**

- *Quality Gate* — findings now carry a severity, ERROR or WARNING, and
  `passed` is "no ERROR issues" rather than "no issues at all". This mirrors the
  Validator's errors-vs-warnings split. Orphan words are the only WARNING.
  Reason: three of the nine compiled resumes contain orphans while being clean
  in every other respect, so treating a stranded word as disqualifying would
  fail a resume a reviewer would happily read. Diverges from task 016's brief,
  which listed orphan words as a failure; the divergence is deliberate and was
  driven by the measurement.

**1.2 — 2026-08-28**

- *Quality Gate / Progressive Validation* corrected. Stage 2 previously ran
  "only if Stage 1 fails". Both stages now always run. Reason: geometry
  analysis costs milliseconds and compilation ~0.5s, so the "expensive"
  premise was false; and short-circuiting hid text overlap until the Revision
  Engine had already spent one of its three attempts on the page count.
- *Quality Gate / Stage 1* corrected. "No orphan words" was listed as a Stage 1
  check. Orphan detection needs rendered PDF geometry, which the compiler log
  does not carry, so it is a Stage 2 check. Missing glyphs — which the log does
  carry — take its place in Stage 1.
- *Technology Decisions* — PDF Analysis changed from "not yet adopted" to
  `pdfminer.six`, adopted in task 016. MIT, and it adds no new packages:
  `cryptography` and `charset-normalizer` were already installed. Pinned
  `<20251227` because releases from that date declare `requires-python >=3.10`
  and this project is 3.9. PyMuPDF was rejected as AGPL-3.0.
- *Quality Gate* — recorded that page count alone is never sufficient, per the
  §10d regression where overlapping text *improved* the page count.

**1.1 — 2026-08-26**

- *Technology Decisions* corrected to the versions and libraries actually in
  use. Python is 3.9, not 3.12+. Configuration is TOML plus the OS keyring, not
  PyYAML. Rich and PyMuPDF are listed as not yet adopted rather than as current
  choices.
- *Folder Structure* corrected. `generated/`, `artifacts/`, `logs/` and a
  top-level `prompts/` were never created; `output/` is the single artifact
  root and prompts live in `src/prompts/`. The `src/` listing now names the
  packages that exist and marks the ones still to come.
- *Artifacts* changed from flat `artifacts/attempt_1.pdf` to nested
  `output/compile/attempt_1/`. Reason: `output/` is already gitignored,
  `artifacts/` was not, and one artifact root is better than two.
- *Compiler* expanded from three lines to its actual contract, following the
  implementation of the PDF Compiler in task 015.
- *Related Documents* — `ROADMAP.md` marked as not yet written, and
  `IMPLEMENTATION_GUIDE.md` marked as a stub, rather than referenced as though
  both exist.

**1.0 — 2026-07-20**

- Original frozen architecture. The Resume Planner stage was added to the
  pipeline during task 012, which this document already reflects.

Vision

Given a master resume and a Job Description, generate a submission-ready, ATS-optimized, single-page resume using the user's existing LaTeX template in under 3 minutes (typically 1–2 minutes), while requiring zero manual editing.

## Scope

This document defines the architecture for Version 1.0.

It is intentionally focused on the MVP required to support the author's job search workflow.

Future enhancements are documented separately under the Backlog section.

Product Philosophy

This project is not an AI demo.

It is an autonomous resume optimization system.

The user should only:

Choose the resume.
Paste the Job Description.

Everything else should happen automatically.

The tool should not ask questions or require decisions during execution.

Success Criteria

A resume is considered successfully generated only if all of the following are true:

ATS optimized
Matches the selected mode
Compiles successfully
Fits exactly one page
Has no structural/layout issues
Preserves the user's LaTeX design
Produces a complete audit report

If any of these fail, the resume is not finished.

## Architectural Rule

AI agents are implementation tools.

They must never modify the architecture.

Any architectural changes must first be made in this document before implementation begins.

Core Design Principles

1. Quality First

The objective is not "offline".

The objective is

Produce the highest-quality resume within 3 minutes.

The architecture should support:

Local models
OpenAI
Anthropic
Gemini
Future providers

The best provider for the task can be configured.

2. Zero Intervention

Execution should look like

resume-tailor

or

pbpaste | resume-tailor

The tool never pauses asking

Continue?
Confirm?
Select?

Everything is configuration driven.

3. Markdown is the Source of Truth

Master resumes become

backend.md

fullstack.md

cybersecurity.md

The AI edits Markdown.

Never LaTeX.

4. LaTeX is Only a Renderer

The AI never edits

resume.tex

Instead

Markdown

↓

Renderer

↓

resume.tex

↓

pdflatex

↓

resume.pdf

This guarantees your formatting is always preserved.

5. Every Module Has One Responsibility
   Module Responsibility
   Parser Read data
   Analyzer Understand JD
   Planner Decide what changes and why
   Generator Generate / revise content
   Renderer Produce LaTeX
   Compiler Produce PDF
   Quality Gate Decide if resume is acceptable
   Reporter Explain changes

No module performs two unrelated jobs.

## Core Interfaces

The project exposes the following architectural interfaces.

LLMProvider

Renderer

QualityGate

ReportGenerator

MarkdownParser

Technology Decisions

| Component | Technology |
|---|---|
| Python | 3.9+ (`pyproject.toml` requires `>=3.9`; the venv is 3.9) |
| Package Manager | pip via the project venv (`uv` is not required and is often absent from PATH) |
| CLI | Typer |
| Terminal UI | plain `typer.echo` — Rich is **not adopted** |
| Config | TOML at `~/.resume-tailor/config.toml`, API keys in the OS keyring |
| Data Models | Pydantic v2 |
| PDF Analysis | **not yet adopted** — planned for the Quality Gate |
| PDF Compilation | pdflatex, invoked by `src/compiler/` |
| Testing | pytest |
| Rendering | LaTeX, from frozen templates |
| LLM Provider | Pluggable (Ollama/OpenAI/Anthropic/Gemini/OpenRouter) |

Notes on the corrections in 1.1:

- **Python 3.9, not 3.12+.** Use `typing.List` / `typing.Optional`; the
  `X | Y` union syntax will not parse.
- **TOML, not PyYAML.** PyYAML is not installed. `config/config.yaml` exists
  only because this document once mandated the path — nothing in `src/` reads
  it. Real configuration is `~/.resume-tailor/config.toml` via
  `src/config/manager.py`, with credentials in the OS keyring via
  `src/config/credentials.py`.
- **Rich and PyMuPDF are not installed.** They remain reasonable future
  choices; listing them as current decisions misdescribed the project.

Folder Structure (This folder structure is considered part of the architecture. Implementation tasks should not modify it unless the architecture document is explicitly updated)
```text
resume-tailor/

    README.md
    pyproject.toml

    docs/
        ARCHITECTURE.md
        COMPONENT_SPECIFICATIONS.md
        CODING_STANDARDS.md
        IMPLEMENTATION_GUIDE.md     # stub
        PROJECT_KNOWLEDGE.md        # running reference, updated each task

    config/
        config.yaml                 # inert; real config is ~/.resume-tailor/config.toml

    content/
        backend_resume.md
        fullstack_resume.md
        cybersecurity_resume.md

    templates/
        backend.tex
        fullstack.tex
        cybersecurity.tex
        masterTemplates/            # the original filled-in resumes, kept for reference

    output/                         # gitignored; the single artifact root
        resumes/latex/              # rendered .tex, one per resume
        tex/                        # ad-hoc tailored .tex, {resume}_{mode}.tex
        compile/                    # compilation attempts, one directory each

    tasks/
    tests/

    src/
        cli/
        parser/
        validation/
        analyzer/
        planner/
        generator/
        renderer/                   # Markdown serializer + LaTeX renderer
        compiler/                   # pdflatex invocation
        providers/
        config/
        prompts/
        helpers/
        entity_ids.py
        vocabulary.py

        quality/                    # Quality Gate (named quality_gate/ above until 1.5)
        report/                     # Reporter
```

Corrections made in 1.1:

- **`generated/`, `artifacts/` and `logs/` were never created.** `output/` is
  the single artifact root, and it is the only one in `.gitignore`. Anything
  that wants to write artifacts writes under `output/`.
- **`prompts/` is not top-level.** Prompt construction lives in `src/prompts/`
  and in each component's own `prompts.py`; there are no prompt Markdown files.
- **There is no `src/models/` or `src/utils/`.** Models live beside the code
  that owns them (`src/parser/models.py`, `src/planner/models.py`, and so on),
  and shared helpers are `src/helpers/`, `src/entity_ids.py` and
  `src/vocabulary.py`.
- **`config/config.yaml` is inert.** Nothing in `src/` reads it. It exists only
  because this document mandated the path.
- **Resume files are `{name}_resume.md`**, not `{name}.md`.

Resume Model

Instead of treating the resume as one document, we treat it as structured sections.

Resume

├── Contact
├── Summary
├── Skills
├── Experience
├── Projects
└── Education

Each section is independent.

Section Policies

Every section has two independent properties.

1. Mutable

Can the AI modify it?

Example

Education

mutable = false
Experience

mutable = true 2. Revision Order

Only used when the resume must be shortened.

Example

Summary

revision_order = 1
Projects

revision_order = 2
Skills

revision_order = 3
Experience

revision_order = 4

Education

mutable = false

so revision order doesn't even exist.

Notice

This order is NOT used during generation.

Only during shortening.

High-Level Pipeline
Markdown Resume
│
▼
Resume Parser
│
▼
Resume Object
│
▼
JD Analyzer
│
▼
Resume Planner
│
▼
Resume Generator
│
▼
LaTeX Renderer
│
▼
pdflatex
│
▼
Quality Gate
│
Passed?
/ \
 Yes No
│ │
▼ ▼
Done Revision Generator
│
└───────────────┐
▼
LaTeX Renderer
JD Analyzer

Responsibility

Understand the Job Description.

✓ Extract keywords

✓ Extract role

✓ Extract company

Output

Company

Role

Required Skills

Preferred Skills

Responsibilities

Keywords

This module never generates text.

It only analyzes.

Out of Scope

✗ Resume generation

✗ ATS scoring

✗ PDF generation

Resume Generator

Input

Resume
JD Analysis
Resume Plan
Mode

Output

Optimized Resume

It knows nothing about LaTeX.

Amended in task 012: a Resume Planner stage (task 011) sits between the JD
Analyzer and the Generator. The Planner decides what changes and why, emitting
a ResumePlan of KEEP / REWRITE / REMOVE / GENERATE actions per entity; the
Generator follows that plan and writes the words. Experience role is mutable in
aggressive mode only. See tasks/012-resume-generator.md and
docs/PROJECT_KNOWLEDGE.md.

Modes
🟢 Strict

Allowed

Rewrite wording
Improve grammar
Emphasize existing skills
Reorder bullets

Forbidden

New technologies
New metrics
New projects
New achievements
🔴 Aggressive

Allowed

Rewrite everything
Add JD keywords
Add technologies
Add quantified metrics
Add achievements
Rewrite summary
Rewrite bullets

No confirmations.

Everything happens automatically.

Renderer

Input

Resume Object

Output

resume.tex

Uses

backend.tex

unchanged.

Compiler

Runs

pdflatex

Produces

resume.pdf

Expanded in 1.1, following the implementation in task 015.

The Compiler's only question is **"did the engine produce a readable PDF?"**
It makes no quality judgement: page count, spacing, orphan words and overfull
boxes all belong to the Quality Gate. It never modifies or repairs the LaTeX it
is given.

```python
PDFCompiler(engine="pdflatex", timeout_seconds=120).compile(
    latex_source, output_directory="output/compile/attempt_1", job_name="resume"
) -> CompilationResult
```

- **Each compilation runs in its own temporary directory**, then copies its
  artifacts into the caller-owned output directory. This is what makes repeated
  and concurrent compilations safe, and keeps auxiliary files out of the
  project tree.
- **The caller owns attempt numbering.** The Compiler owns only the base file
  name within a directory.
- **Success requires both a zero exit status and a readable PDF.** Either alone
  is insufficient: under `-interaction=nonstopmode` the engine can write a
  partial PDF and still exit non-zero.
- **It raises rather than returning a status flag.** `CompilationFailedError`
  carries the exit code and the path to the preserved log, which the Revision
  Engine needs.
- **Artifacts are preserved before any exception is raised**, so a failed
  attempt is always debuggable. The `.tex` and `.log` survive every failure,
  including a timeout.
- **Compilation is deterministic.** `SOURCE_DATE_EPOCH` and `FORCE_SOURCE_DATE`
  are pinned in the engine's environment; without them pdflatex stamps the wall
  clock into the PDF and identical source produces different bytes.
- **The engine is configurable and never hardcoded to an absolute path.** It is
  resolved through `PATH`, and an explicit executable path is also accepted.
Quality Gate

The Quality Gate is the heart of the system.

Its responsibility is simply

Decide whether the generated resume is submission-ready.

Progressive Validation

Both stages always run. Changed in 1.2 — see the Amendment Log.

Stage 1 (Always Runs)

Fast, deterministic checks from the compiler log and the page count.

✅ LaTeX compiles
✅ Exactly one page
✅ No overfull hboxes
✅ No missing glyphs
✅ No critical compile errors

Orphan words are NOT a Stage 1 check. They need rendered geometry, which the
compiler log does not carry.

Stage 2 (Also Always Runs)

PDF geometry analysis, via `pdfminer.six`.

✅ No text overlap
✅ No section rule drawn through text
⚠️  Orphan words — reported, but do not block

Plus the overflow metrics the Revision Engine needs: how many lines spilled
past page one, how tall that spill is, and which sections it came from.

Why both stages always run. Stage 2 was originally specified to run only when
Stage 1 failed. That is wrong in both directions. Geometry analysis costs
milliseconds and compilation about half a second, so there is nothing to save
by skipping it; and stopping early means the Revision Engine learns about
overlapping text only after spending one of its three attempts on the page
count. The gate reports every problem it can see, in one pass.

Page count is never the sole signal. A document whose bullets print on top of
each other compiles with exit 0, reports no warnings, and comes out *shorter* —
the metric improves because the text is collapsing rather than fitting. A
one-page PDF with colliding text fails the gate.

Produces structured feedback.

Stage 3

Revision.

The Revision Engine receives

Current Resume

-

Quality Report

and revises only the necessary sections.

Revision Loop
Generate

↓

Compile

↓

Quality Gate

↓

Pass?

↓

No

↓

Targeted Revision

↓

Compile

↓

Quality Gate

Configuration

max_revisions: 3

Meaning

Initial generation
Revision 1
Revision 2
Revision 3

Maximum

4 LLM generations

This caps **LLM revision passes**. The Revision Engine's deterministic
deletion loop is uncapped and makes no LLM calls at all. Changed in 1.4 — see
the Amendment Log.

Never more.

Revision Strategy

The entire resume is never regenerated.

Only the affected sections.

Example

Projects overflow

↓

Revise only Projects

If still failing

Summary too long

↓

Revise only Summary

The rest of the resume remains untouched.

Reports

Every run produces

report.md

Example

Mode

Aggressive

Summary

Rewritten

Bullets Modified

7

Technologies Added

5

Metrics Added

3

Achievements Added

2
Diff

Every run also produces

changes.md

Example

- Developed REST APIs.

* Developed RESTful APIs using Spring Boot,
  improving API response time by 45%.
  Artifacts

Every attempt is preserved.

```text
output/
    compile/
        attempt_1/
            resume.tex
            resume.pdf
            resume.log
        attempt_2/
            resume.tex
            resume.log          # a failed attempt keeps its source and log
        final/
            resume.pdf
```

Useful for debugging and prompt tuning.

Changed in 1.1. This section previously specified a flat top-level
`artifacts/attempt_1.pdf`. Artifacts now nest one directory per attempt under
`output/`, because `output/` is already gitignored and a single artifact root
is better than two. The per-attempt quality report (`attempt_1_report.json` in
the original) belongs to the Quality Gate and will join its attempt directory
when that stage is built.

CLI

resume-tailor tailor
resume-tailor tailor --resume content/backend_resume.md --mode aggressive
resume-tailor tailor --jd posting.md --mode strict
resume-tailor doctor
resume-tailor analyze
resume-tailor plan

Amended in 1.6 — see the Amendment Log. `tailor` reads a pasted job description
from stdin when `--jd` is not given, so `pbpaste | resume-tailor tailor` works
today rather than "later".
Phase 1 (MVP)

This is the version you'll actually use during your job hunt.

✅ Project setup (uv, Typer, Rich)
✅ Configuration system
✅ Logging
✅ doctor command
✅ Markdown resume parser
✅ JD analyzer
✅ Resume generator
✅ Strict mode
✅ Aggressive mode
✅ LaTeX renderer
✅ PDF generation
✅ Quality Gate
✅ Automatic revision loop
✅ Report generation
✅ Diff generation
Backlog

Deliberately postponed until after your job hunt:

Learning Mode
LinkedIn / Greenhouse / Lever URL import
Web UI
Cover letter generation
Resume analytics dashboard
Application history
Multi-language support
Final Engineering Philosophy

The project should follow one guiding principle:

Every expensive operation must justify its cost.

That means:

Parse once.
Analyze once.
Generate once.
Validate quickly.
Revise only if necessary.
Revise only the affected sections.
Stop as soon as the resume meets the quality gate.

This keeps the tool within the 1–3 minute target while ensuring the user never receives a resume that needs manual fixes.

## Performance Targets

Typical runtime

45–90 seconds

Maximum runtime

180 seconds

Maximum LLM generations

4

Maximum revisions

3

## Error Handling Philosophy

The application should fail fast.

If a required stage fails, subsequent stages must not execute.

Every error should produce a meaningful message and should never leave partially generated output without explanation.

## Non Goals

Version 1 intentionally does NOT support:

- Web UI

- LinkedIn import

- Cover Letter Generation

- Resume Analytics

- Learning Mode

- Multi-language support

## Related Documents

The architecture is supported by the following documents:

- `COMPONENT_SPECIFICATIONS.md` — Responsibilities, contracts, inputs, outputs, and boundaries for each major component.
- `IMPLEMENTATION_GUIDE.md` — Rules and guidelines for implementing the architecture. **Currently a stub of bare headings.**
- `CODING_STANDARDS.md` — Coding conventions and quality requirements.
- `PROJECT_KNOWLEDGE.md` — Running reference for the codebase as built, updated at the end of each task. Where this document states intent, that one states what exists.
- `ROADMAP.md` — Planned features beyond Version 1. **Not yet written.**
- `tasks/` — Incremental implementation tasks for developers and AI agents.

The `ROADMAP.md` and `IMPLEMENTATION_GUIDE.md` annotations were added in 1.1:
both were referenced here as though complete, and neither was.
