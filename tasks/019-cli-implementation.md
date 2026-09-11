# Task 019 — End-to-End Pipeline & CLI Orchestration

## Objective

Implement the **end-to-end tailoring pipeline** and wire it into the CLI.

All major components are already implemented independently. This task should **orchestrate those components**, not redesign or reimplement them.

The final user experience should be:

```text
resume-tailor tailor
    ↓
Select canonical resume
    ↓
Paste / provide Job Description
    ↓
Run automatically
    ↓
Final submission-ready PDF + reports
```

Once the tailoring run begins, there should be **no confirmation or manual intervention steps**.

---

# 1. End-to-End Pipeline

Implement a clear orchestration layer that executes:

```text
Source Resume
    ↓
Parser
    ↓
Job Description
    ↓
JD Analyzer
    ↓
JobAnalysis
    ↓
Resume Planner
    ↓
ResumePlan
    ↓
Resume Generator
    ↓
Generated Resume
    ↓
Validator
    ↓
Markdown Serializer
    ↓
LaTeX Renderer
    ↓
Compiler
    ↓
Quality Gate
    ↓
Revision Engine (when necessary)
    ↓
Markdown Serializer
    ↓
LaTeX Renderer
    ↓
Compiler
    ↓
Quality Gate
    ↓
Reporter
    ↓
Final Output
```

Use the existing implementations and interfaces.

Do not duplicate component logic inside the orchestrator.

---

# 2. CLI Entry Point

Add the appropriate CLI command using the project's existing CLI framework/conventions.

The intended workflow should be approximately:

```text
resume-tailor tailor
```

The CLI should allow the user to:

```text
select a canonical resume
provide the Job Description
select/configure the tailoring mode where required by existing configuration
```

Then the pipeline runs automatically.

Do not add unnecessary interactive checkpoints such as:

```text
"Do you want to continue?"
"Review this plan?"
"Accept generated resume?"
"Run revision?"
```

The entire tailoring process is autonomous.

---

# 3. Canonical Resume Selection

The project intentionally supports an arbitrary number of canonical resumes.

Everything in the configured canonical resume directory is considered a possible source resume.

Do not hardcode:

```text
3 resumes
backend/fullstack/cybersecurity
```

The CLI should discover the available canonical resumes dynamically using the existing project configuration/path conventions.

If no canonical resume exists, fail clearly with an actionable error.

If only one exists, it should be selected automatically rather than forcing unnecessary interaction.

---

# 4. Job Description Input

Support the existing intended workflow of pasting/copying a large Job Description into the CLI.

The CLI should not impose an artificial small-size limit.

Support multi-line input correctly.

Use the existing project conventions for termination of pasted input.

Avoid introducing unnecessary temporary files solely for JD input unless the existing CLI architecture already uses them.

The exact user-facing syntax may be adapted to the CLI framework, but the workflow must remain simple.

---

# 5. Pipeline Context

Create a run-level context/state object where useful.

It should hold the outputs accumulated during one tailoring run, for example:

```python
TailoringRun
    source_resume
    job_description
    job_analysis
    resume_plan
    generated_resume
    quality_gate_results
    revision_trail
    final_resume
    artifacts
    report
```

Use the existing domain models rather than creating alternate representations of the same concepts.

The context must represent **one run only** and should not persist mutable global state between runs.

---

# 6. Validation

The generated resume must be validated against the **source resume used at the beginning of the run**.

Use the existing API concept:

```python
validator.validate(
    source_resume=source_resume,
    generated_resume=generated_resume,
)
```

Do not load a separate "trusted" resume from disk during the run.

Do not make the Validator responsible for discovering canonical resumes.

Do not mutate the source resume.

Validation should happen before rendering/compilation.

If validation fails, stop the run with a clear error rather than attempting to render an invalid Resume.

---

# 7. Initial Render / Compile / Quality Gate

After successful validation:

```text
Resume
  ↓
Markdown Serializer
  ↓
LaTeX Renderer
  ↓
Compiler
  ↓
Quality Gate
```

Store the relevant artifacts for the run using the project's existing artifact conventions.

The Quality Gate is authoritative for deciding whether the rendered result is acceptable.

Do not duplicate Quality Gate logic in the orchestrator.

---

# 8. Revision Flow

If the initial Quality Gate passes:

```text
Quality Gate PASS
    ↓
No revision
    ↓
Generate report
    ↓
Finish
```

If the Quality Gate fails:

```text
Quality Gate FAIL
    ↓
Revision Engine
    ↓
Revised Resume
    ↓
Validate
    ↓
Serialize
    ↓
Render
    ↓
Compile
    ↓
Quality Gate
```

Repeat according to the **current Revision Engine contract**.

Do not introduce a separate revision-count algorithm into the CLI.

Do not assume the old "maximum 4 LLM generations" architecture. That constraint is obsolete.

The Revision Engine owns its current deterministic trimming/compression behavior and attempt semantics.

The orchestrator owns only the pipeline around it.

---

# 9. Revision Validation

Every Resume returned by the Revision Engine must continue to pass the existing structural validation before rendering.

Use the original `source_resume` as the validation reference.

The source resume must remain unchanged across all revision attempts.

---

# 10. Quality Gate History

Every Quality Gate result generated during the run must be retained.

For example:

```text
quality_gate_results = [
    attempt_1_result,
    attempt_2_result,
    attempt_3_result,
]
```

Do not discard failed attempts.

Reporter requires the complete history.

The orchestrator should pass the full history to Reporter.

---

# 11. Revision Trail

Retain the complete Revision Trail returned/generated by the Revision Engine.

Do not reconstruct revision information afterward.

Pass the original structured Revision Trail directly to Reporter.

---

# 12. Final Result

The pipeline should only report success when the final Resume has passed the final Quality Gate.

The final output should make it obvious where the submission-ready PDF is located.

At minimum, provide the path to:

```text
final PDF
report.md
changes.md
report.json
```

Use the project's existing generated/output/artifact directory conventions.

Do not invent a second output system.

---

# 13. Artifact Organization

Each tailoring run should have an isolated artifact location so different runs do not overwrite one another.

Use the repository's existing artifact conventions where available.

A run may contain intermediate artifacts such as:

```text
attempt-001/
attempt-002/
attempt-003/
```

or the project's equivalent naming scheme.

The Revision Engine already owns attempt numbering where applicable. Do not create conflicting attempt semantics in the orchestrator.

The final output must be easy to locate.

---

# 14. Reporter Integration

Reporter should execute only after the final result has been established.

Pass it:

```python
source_resume
job_analysis
resume_plan
generated_resume
quality_gate_results
revision_trail
final_resume
mode
```

Use the existing Reporter API.

The Reporter should not influence pipeline decisions.

The orchestrator simply provides the required structured inputs and writes the resulting report artifacts.

---

# 15. Errors

Implement clean failure handling around each major pipeline boundary.

Errors should identify the failed stage.

Examples:

```text
Failed to parse source resume
Failed to analyze Job Description
Failed to generate tailored resume
Generated resume failed validation
LaTeX rendering failed
PDF compilation failed
Quality Gate failed after revision attempts
Reporter failed
```

Do not hide underlying exceptions unnecessarily.

Preserve useful error context for debugging/logging.

The CLI should return a non-zero exit code on failure.

Do not print stack traces to normal users unless the project's existing CLI/debug convention calls for it.

---

# 16. Logging / Progress

The run may take up to roughly the project's existing execution budget, so the CLI should provide useful progress feedback.

For example:

```text
Loading source resume...       ✓
Analyzing Job Description...   ✓
Planning changes...            ✓
Generating resume...           ✓
Validating resume...           ✓
Rendering LaTeX...             ✓
Compiling PDF...               ✓
Checking layout...             ✓
Revising...                    ...
Compiling revised PDF...       ✓
Generating report...           ✓

Resume ready.
```

Do not expose internal implementation details unnecessarily.

Progress reporting must not interfere with machine-readable outputs or exceptions.

Follow the project's existing CLI output style.

---

# 17. Execution Time

The project's target runtime is approximately:

```text
1–2 minutes preferred
3 minutes hard maximum target
```

Do not redesign working components solely for theoretical optimization during this task.

However:

* Avoid duplicate LLM calls.
* Do not rerun analysis or planning unnecessarily.
* Do not reparse unchanged inputs.
* Do not perform redundant rendering or compilation.
* Do not invoke Reporter before the final result exists.

The orchestrator should call each stage only when necessary.

---

# 18. Provider Configuration

Use the existing Provider / Factory / Configuration infrastructure.

The orchestrator should not contain provider-specific branching such as:

```python
if provider == "openai":
    ...
elif provider == "ollama":
    ...
```

Provider selection belongs to the existing provider infrastructure.

The same pipeline should work with supported providers without pipeline changes.

---

# 19. Mode

Use the existing `Mode` abstraction and pass it to the components that require it.

Do not implement mode-specific generation logic inside the orchestrator.

The orchestrator should not decide what constitutes:

```text
STRICT
AGGRESSIVE
```

It only passes the selected mode through the existing interfaces.

---

# 20. Immutability

The following must never be mutated during a run:

```text
source_resume
canonical Markdown files
LaTeX templates
```

The generated/revised Resume should always be a separate object.

This is especially important because the Validator compares generated content against the original source Resume.

---

# 21. Tests

Add integration tests for the orchestration layer.

At minimum cover:

### Successful run with no revision

```text
Parser
→ Analyzer
→ Planner
→ Generator
→ Validator
→ Render
→ Compile
→ Quality Gate PASS
→ Reporter
```

### Successful run requiring revision

```text
Initial Quality Gate FAIL
→ Revision Engine
→ Validate
→ Render
→ Compile
→ Quality Gate PASS
→ Reporter
```

### Multiple revision attempts

Verify that:

```text
all Quality Gate results are retained
Revision Trail is retained
Reporter receives complete history
```

### Validation failure

Verify that rendering/compilation does not continue after structural validation fails.

### Compilation failure

Verify that the pipeline stops appropriately.

### Final Quality Gate failure

Verify that the CLI reports failure rather than claiming a successful final resume.

### Missing canonical resume

Verify a clear CLI error.

### Single canonical resume

Verify it is selected automatically.

### Multiple canonical resumes

Verify the user can select among discovered resumes.

### Deterministic artifact organization

Verify separate runs do not overwrite previous runs.

---

# 22. End-to-End Smoke Test

After implementation, perform an actual end-to-end smoke test using:

```text
one canonical resume
one realistic Job Description
the configured LLM provider
the real Renderer
the real Compiler
the real Quality Gate
the real Revision Engine
the real Reporter
```

Do not replace the pipeline with mocks for this smoke test.

Verify that a final PDF and all three reports are produced.

Verify the final PDF passes the final Quality Gate.

---

# 23. CLI UX

The final successful command should make the result obvious.

Example:

```text
Resume Tailor

✓ Source resume selected: ...
✓ Job Description analyzed
✓ Resume plan created
✓ Resume generated
✓ Validation passed
✓ PDF compiled
✓ Quality Gate passed
✓ Report generated

Final Resume:
  ...

Reports:
  ...
  ...
  ...

Done.
```

Adapt formatting to the project's existing CLI implementation.

Do not add excessive decorative output.

---

# 24. Architectural Constraints

This task is an **orchestration task**.

Do not:

* rewrite completed components
* move business logic between components
* modify the resume schema unnecessarily
* modify the LaTeX templates
* add LLM logic to the CLI
* add provider-specific logic to the CLI
* make Reporter perform analysis
* make Quality Gate perform revision
* make Revision Engine perform rendering/compilation
* make Generator perform one-page fitting
* make Validator discover source resumes

Keep responsibilities separated.

If an existing interface needs a minor adaptation for orchestration, prefer a small compatibility change over architectural duplication.

---

# Definition of Done

Task 018 is complete when:

* A real `tailor` CLI workflow exists.
* The user can select a canonical resume dynamically.
* The user can provide a large Job Description.
* The complete pipeline runs automatically.
* JD Analyzer, Planner, Generator, Validator, Serializer, Renderer, Compiler, Quality Gate, Revision Engine, and Reporter are wired together.
* Validation uses the original `source_resume`.
* Failed Quality Gate attempts are retained.
* Revision occurs only when required.
* Final success requires a passing final Quality Gate.
* Final PDF and all Reporter artifacts are produced.
* Each run has isolated artifacts.
* CLI errors are clear and return non-zero status.
* Existing provider abstraction is respected.
* Canonical resumes and templates are never modified.
* Integration tests pass.
* A real end-to-end smoke test succeeds.

---

## Agent Report

After implementation, report:

```text
Files changed:
...

Tests added:
...

Tests executed:
...

Integration smoke test:
PASS / FAIL

Final PDF produced:
...

Reports produced:
...

Architectural deviations:
...
```

Do not declare the task complete until the real end-to-end smoke test has been executed.
