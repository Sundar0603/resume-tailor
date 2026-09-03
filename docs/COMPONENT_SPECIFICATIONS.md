# Component Specifications

**Version:** 1.0

**Status:** Frozen

**Last Updated:** 2026-07-20

---

# Purpose

This document defines the responsibilities, boundaries, inputs, outputs, and constraints of every major component in Resume Tailor CLI.

Every component follows the **Single Responsibility Principle (SRP)**.

A component may **only** perform the responsibilities defined in this document.

If a component's responsibilities change, this document must be updated before implementation begins.

---

# Architectural Rules

Every component must:

- Have exactly one primary responsibility.
- Communicate only through well-defined inputs and outputs.
- Avoid direct knowledge of unrelated components.
- Be independently testable.
- Be replaceable without affecting unrelated components.

Components must **not** assume responsibilities assigned to other components.

---

# Resume Parser

## Responsibilities

- Load the selected Markdown resume.
- Parse the Markdown into a structured `Resume` object.
- Validate the basic document structure.
- Preserve the original ordering of resume sections.
- Provide structured resume data to downstream components.

## Input

- Selected Markdown resume.

## Output

- Structured `Resume` object.

## Out of Scope

- Job Description analysis.
- Resume optimization.
- ATS scoring.
- LaTeX generation.
- PDF generation.
- LLM interactions.

---

# JD Analyzer

## Responsibilities

- Analyze the Job Description.
- Extract the company name.
- Extract the job title.
- Identify required skills.
- Identify preferred skills.
- Extract responsibilities.
- Extract important keywords.
- Produce a structured `JDAnalysis` object.

## Input

- Job Description.

## Output

Structured `JDAnalysis` containing:

- Company
- Role
- Required Skills
- Preferred Skills
- Responsibilities
- Keywords

## Out of Scope

- Resume generation.
- Resume rewriting.
- ATS scoring.
- PDF generation.
- Layout decisions.
- LaTeX generation.

---

# Resume Generator

## Responsibilities

- Generate an optimized resume using:
  - Resume
  - JD Analysis
  - Resume Plan
  - Selected Mode
- Follow the `ResumePlan` rather than independently deciding what changes.
- Apply Strict or Aggressive mode rules.
- Produce an optimized `Resume` object.
- Revise only requested sections during the revision loop.

## Input

- Resume
- JDAnalysis
- ResumePlan
- Generation Mode

## Output

- Optimized `Resume` object.

> **Amended in task 012.** This specification originally placed the Generator
> directly after the JD Analyzer. A **Resume Planner** stage (task 011) now sits
> between them: the Planner decides *what* changes and *why*, emitting a
> `ResumePlan` of KEEP / REWRITE / REMOVE / GENERATE actions per entity, and the
> Generator writes the words. The Generator no longer chooses which sections to
> change.
>
> Two further amendments from task 012:
>
> - Experience `role` is mutable in **aggressive mode only**, so a role can be
>   retitled to match the target job. See `tasks/005-resume-validator.md`.
> - The skills section is applied in pure Python. The Planner already emits
>   literal category names and skill strings, so no LLM call is involved.

### Strict Mode

Allowed:

- Rewrite wording
- Improve grammar
- Emphasize existing skills
- Reorder bullets

Forbidden:

- New technologies
- New metrics
- New projects
- New achievements

### Aggressive Mode

Allowed:

- Rewrite content
- Add JD keywords
- Add technologies
- Add quantified metrics
- Add achievements
- Rewrite summaries
- Rewrite bullets

Execution is fully automatic.

No confirmations.

## Out of Scope

- Parsing Markdown.
- Editing LaTeX.
- PDF generation.
- Layout validation.
- Quality Gate decisions.
- Report generation.

---

# Renderer

## Responsibilities

- Convert the structured Resume object into LaTeX.
- Populate the existing LaTeX template.
- Preserve the user's formatting.
- Produce `resume.tex`.

## Input

- Structured Resume object.

## Output

- `resume.tex`

## Out of Scope

- Resume generation.
- ATS optimization.
- PDF validation.
- LLM interactions.
- Report generation.

---

# Compiler

## Responsibilities

- Execute the configured LaTeX engine.
- Produce `resume.pdf`.
- Capture compiler logs.
- Report compilation success or failure.

## Input

- `resume.tex`

## Output

- `resume.pdf`
- Compilation logs

## Out of Scope

- Resume generation.
- Resume modification.
- Layout analysis.
- PDF inspection.
- Report generation.

---

# Quality Gate

## Responsibilities

Determine whether the generated resume is submission-ready.

### Stage 1 — Fast Validation

Deterministic checks from the compiler log and the page count:

- LaTeX compilation succeeds.
- Resume contains exactly one page.
- No overfull hboxes.
- No missing glyphs.
- No critical compilation errors.

Orphan words were previously listed here. They require rendered PDF geometry,
which the compiler log does not carry, so they belong to Stage 2.

### Stage 2 — Geometry Analysis

Always runs, not only when Stage 1 fails. See the ARCHITECTURE 1.2 amendment:
the analysis costs milliseconds, and deferring it would hide overlapping text
until the Revision Engine had already spent an attempt on the page count.

- Text overlap between rendered lines.
- Section rules drawn through text.
- Orphan words — reported as a WARNING, which does not block.
- Overflow magnitude and the sections it came from.

Produce structured quality feedback.

Page count is never the sole success signal: a document whose bullets collide
compiles cleanly and comes out *shorter*.

### Stage 3 — Revision Request

Request targeted revisions.

Only affected sections should be revised.

## Input

- Compiled PDF.
- Compiler logs.
- CompilationResult, or CompilationFailedError when the engine failed.

The Resume object was previously listed here. The gate does not take it: it
judges artifacts, and reporting a section plus the offending line text is
enough for the Revision Engine, which already holds the Resume.

## Output

- Quality Report, with each finding marked ERROR or WARNING.
- Pass / Fail decision, where pass means "no ERROR issues".

## Out of Scope

- Resume generation.
- Resume modification.
- LaTeX rendering.
- PDF compilation.
- ATS optimization.

---

# Revision Engine

## Responsibilities

- Receive the source Resume, the current Resume and the Quality Gate result.
- Delete content deterministically until the resume fits one page.
- Re-render, recompile and re-judge after every change.
- Stop the moment the Quality Gate passes.
- Compress selected bullets through a single consolidated LLM call, but only
  when deterministic deletion is exhausted and the page still overflows.
- Extract protected facts before that call and verify them after it.
- Own attempt numbering, the artifact layout and the revision trail.
- Raise when one page is unreachable without breaching a retention floor.

## Input

- Source Resume (never modified; never read for content).
- Current Resume.
- QualityGateResult.
- Output directory and job name.

## Output

- `RevisionResult`, carrying the **changed** Resume, the final Quality Gate
  verdict, the attempt counts and the revision trail.

## Out of Scope

- Regenerating the entire resume.
- Parsing Markdown.
- Rendering LaTeX.
- PDF validation.
- Report generation.
- Deciding *what* content matters. That ordering is the Generator's, applied
  once through `_order_highlights`, and the engine only consumes it.

> **Amended in task 017.** Three corrections, each measured rather than argued.
>
> **`revision_order` is not deletion order.** This specification told the engine
> to "respect each section's `revision_order`", which puts **Summary first**.
> A deterministic trimmer cannot compress prose — it can only delete it
> wholesale, which is the worst trade available — so the Summary is never a trim
> target at all, and its length is fixed at *generation* time instead. The
> deletion order is **Projects → Skills → Experience (Internship → Full-Time)**.
> `REVISION_ORDER` remains in `src/quality/models.py` and is unused by the
> engine.
>
> **"Revise only the affected sections" is not actionable.** The gate reports
> `overflowing_sections`, but page overflow is a property of the whole document:
> content on page two is not evidence that the section it landed in is the one
> to trim. The engine trims by the authoritative order above and lets the
> recompile decide whether it worked.
>
> **"Minimize unnecessary modifications" is served by stopping, not by
> predicting.** Task 016 measured spill going `7 → 7 → 0` — bullet removals that
> individually free nothing, because the subheading blocks move as a unit. The
> engine therefore recompiles after every single step (~0.5 s) and halts at the
> first pass, rather than estimating a batch and over-trimming.
>
> The Summary, Education, Contact and the immutable experience fields are never
> touched, and the retention floors in `src/revision/floors.py` are hard: an
> unreachable one-page target raises `OnePageInfeasibleError` rather than being
> met by breaching one.

---

# Reporter

## Responsibilities

Generate:

- `report.md`
- `changes.md`

Summarize:

- Modified sections.
- Added technologies.
- Added metrics.
- Added achievements.
- AI decisions.
- Revision history.

## Input

- Resume.
- Generation metadata.
- Quality Report.

## Output

- Markdown reports.

## Out of Scope

- Resume generation.
- Resume revision.
- PDF analysis.
- ATS optimization.
- LLM interactions.

---

# LLM Provider

## Responsibilities

Provide a unified abstraction over supported LLM providers.

Supported providers include:

- Ollama
- OpenAI
- Anthropic
- Gemini

Responsibilities include:

- Sending prompts.
- Receiving responses.
- Managing provider-specific APIs.
- Providing a common interface for the rest of the application.

The remainder of the application must never depend on provider-specific implementations.

## Input

- Prompt.
- Generation parameters.

## Output

- Model response.

## Out of Scope

- Prompt construction.
- Resume generation logic.
- Quality validation.
- Report generation.
- Business logic.

---

# CLI

## Responsibilities

- Parse user commands.
- Load configuration.
- Select the requested resume.
- Select execution mode.
- Orchestrate the end-to-end pipeline.
- Display progress.
- Display execution results.

Supported commands include:

- `resume-tailor`
- `resume-tailor --resume backend`
- `resume-tailor --mode aggressive`
- `resume-tailor doctor`

Future support:

- `pbpaste | resume-tailor`

## Input

- CLI arguments.
- Configuration.
- Job Description.

## Output

- Terminal output.
- Generated resume.
- Reports.

## Out of Scope

- Resume generation.
- Resume parsing.
- PDF validation.
- LaTeX rendering.
- Business logic.

---

# Component Dependency Rules

The following dependency graph defines the permitted communication between components.

```text
CLI
 │
 ▼
Parser
 │
 ▼
JD Analyzer
 │
 ▼
Resume Generator
 │
 ▼
Renderer
 │
 ▼
Compiler
 │
 ▼
Quality Gate
 │
 ├─────────────── Pass ───────────────► Reporter
 │
 └────── Fail ─────► Revision Engine
                        │
                        ▼
                   Renderer
```

Rules:

- Components may only depend on downstream components through defined interfaces.
- Components must never bypass the pipeline.
- Components must never directly modify another component's internal state.
- Business logic belongs only within the component responsible for that concern.

---

# Future Components

The following components are intentionally excluded from Version 1:

- Learning Mode
- Cover Letter Generator
- LinkedIn Import
- Greenhouse Import
- Lever Import
- Resume Analytics
- Application Tracker
- Web UI
- Multi-language Support

These components require updates to both `ARCHITECTURE.md` and this document before implementation.
