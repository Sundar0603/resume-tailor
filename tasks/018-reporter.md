# Task 017 — Implement Reporter

## Objective

Implement the **Reporter** component for Resume Tailor.

The Reporter is responsible for producing a clear, deterministic record of what happened during a tailoring run.

It must not perform generation, validation, comparison through raw Markdown parsing, or LLM calls. It only consumes the structured outputs produced by the earlier pipeline stages and writes reports.

---

## Inputs

The Reporter should receive the structured results from the tailoring pipeline:

```text
source_resume
job_analysis
resume_plan
generated_resume
quality_gate_results
revision_trail
final_resume
mode
```

Use the existing domain models and interfaces already implemented in the project.

Do not introduce duplicate representations of these objects.

---

## Outputs

The Reporter must generate these three artifacts:

```text
report.md
changes.md
report.json
```

They should be written into the run's existing artifact/output structure rather than introducing a new directory convention.

Follow the repository's existing naming and artifact conventions.

---

# 1. `report.json`

This is the machine-readable report and should contain structured information about the complete tailoring run.

Include, at minimum:

```text
mode
source resume identity
job analysis summary
planner result
generated resume summary
quality gate history
revision trail
final resume summary
```

The JSON should preserve useful structured information rather than flattening everything into prose.

Use Pydantic serialization where appropriate.

Do not serialize runtime-only information unnecessarily, especially if existing models distinguish runtime metadata from canonical resume content.

---

# 2. `report.md`

This is the human-readable summary of the complete run.

It should clearly show:

## Run Information

```text
Mode
Source resume
Target role
```

## Job Analysis Summary

Summarize:

```text
required skills
preferred skills
technologies
domains
key responsibilities
important keywords
```

Use the already-produced `JobAnalysis`. Do not call the LLM again.

## Resume Plan Summary

Show what the planner decided to do.

For example:

```text
Experience
- exp_001: REWRITE
- exp_002: KEEP

Projects
- proj_001: REWRITE
- proj_002: REMOVE
- generated project: GENERATE

Skills
- skill_001: REWRITE
- generated category: GENERATE
```

Use stable runtime IDs and planner actions where available.

## Quality Gate

Show the quality-gate progression.

Example:

```text
Attempt 1
- Page count: 2
- Compile: PASS
- Overfull boxes: PASS
- Missing glyphs: PASS
- Layout overlap: FAIL

Attempt 2
- Page count: 1
- Compile: PASS
- Overfull boxes: PASS
- Missing glyphs: PASS
- Layout overlap: PASS
```

Warnings should be distinguishable from blocking failures.

Do not reinterpret Quality Gate results. Report what the Quality Gate actually returned.

## Final Result

Clearly state whether the final resume passed the Quality Gate.

Include final page count and other relevant final quality information.

---

# 3. `changes.md`

This should focus specifically on **what changed in the resume**.

Do not independently diff raw Markdown files.

Use:

```text
ResumePlan
RevisionTrail
runtime entity IDs
source lineage
```

to determine the changes.

Organize changes by section:

```text
Summary
Skills
Experience
Projects
Education
```

Only include sections that actually changed, unless the existing project conventions require all sections to be displayed.

For changes originating from the planner, distinguish actions such as:

```text
KEEP
REWRITE
REMOVE
GENERATE
```

For revision-engine changes, clearly distinguish:

```text
bullet removed
project removed
skill removed
bullet compressed
```

Where useful, include the relevant entity ID.

Example:

```text
Projects

- proj_002
  - Removed lowest-priority bullet during deterministic trimming.

Experience

- exp_001
  - Compressed one bullet to satisfy page-fit constraints.
```

Generated entities should be identifiable as generated using the existing `source` lineage metadata.

---

# Design Requirements

## Deterministic

Reporter output must be deterministic.

The same structured inputs should produce the same report content.

Do not use an LLM.

Do not use timestamps or random identifiers in report content unless the existing run/artifact infrastructure explicitly requires them.

---

## No Independent Resume Logic

Reporter must not decide whether a resume change was correct.

For example, it must not independently determine:

```text
whether a skill is valid
whether a project should exist
whether content violates constraints
whether the resume fits on one page
```

Those decisions belong to the relevant pipeline components.

Reporter only reports their results.

---

## No Raw Markdown Diff

Do not implement:

```text
old markdown → parse → diff → infer changes
```

The project already has structured lineage and planner/revision information.

Use those structures instead.

---

## Preserve Source Lineage

Where relevant, distinguish:

```text
CANONICAL
GENERATED
```

using the existing `EntitySource` mechanism.

Do not let the Reporter invent or infer source values.

---

# Suggested API

Adapt this to the repository's existing architecture rather than forcing an exact signature:

```python
class Reporter:
    def generate(
        self,
        source_resume: Resume,
        job_analysis: JobAnalysis,
        resume_plan: ResumePlan,
        generated_resume: Resume,
        quality_gate_results: list[QualityGateResult],
        revision_trail: RevisionTrail,
        final_resume: Resume,
        mode: Mode,
    ) -> Report:
        ...
```

A structured `Report` model may be introduced if that fits the existing architecture.

Prefer structured data first, then render:

```text
Report
 ├── report.json
 ├── report.md
 └── changes.md
```

Avoid duplicating report-building logic between the three formats.

---

# Testing

Add focused unit tests.

At minimum test:

1. A run with no revisions.
2. A run with deterministic removals.
3. A run with LLM bullet compression.
4. A run containing generated projects or skill categories.
5. A run with multiple Quality Gate attempts.
6. Final successful one-page result.
7. Final failed result.
8. Deterministic output for identical inputs.

Verify that:

```text
report.json
report.md
changes.md
```

contain the expected information and remain deterministic.

---

# Constraints

Do not modify the responsibilities of:

```text
Parser
JD Analyzer
Resume Planner
Resume Generator
Markdown Serializer
LaTeX Renderer
Compiler
Quality Gate
Revision Engine
```

Do not move logic from those components into Reporter.

Do not add an LLM dependency.

Do not modify the LaTeX templates.

Do not modify the canonical resume content.

Keep the implementation aligned with `ARCHITECTURE.md`. If the current repository differs from any detail above, inspect the existing implementation and follow the architecture already established instead of creating parallel abstractions.

---

# Definition of Done

Reporter is complete when:

* `report.json` is generated successfully.
* `report.md` is generated successfully.
* `changes.md` is generated successfully.
* Reports use structured pipeline results rather than raw Markdown diffing.
* Planner actions and revision-engine changes are represented clearly.
* Generated vs canonical entities are represented using existing lineage metadata.
* Quality Gate history is reported accurately.
* No LLM calls are made by Reporter.
* Reporter does not mutate the Resume or any upstream pipeline result.
* Unit tests cover the major cases above.
* Existing project tests still pass.

After implementation, run the relevant test suite and report:

```text
Files changed
Tests added
Tests executed
Test result
Any architectural deviations
```
