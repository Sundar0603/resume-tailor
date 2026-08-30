# Task 016 – Quality Gate

## Objective

Implement the Resume Tailor Quality Gate.

The Quality Gate determines whether a compiled resume PDF is genuinely submission-ready.

Its job is to evaluate the generated artifacts and return a structured quality result.

It must **not modify** the resume, LaTeX source, PDF, or Resume object.

The Quality Gate must not treat page count alone as proof of a valid one-page resume.

---

# Pipeline Position

```text
Resume Object
      ↓
Markdown Serializer
      ↓
LaTeX Renderer
      ↓
PDF Compiler
      ↓
Quality Gate
      │
      ├── PASS → Resume accepted
      │
      └── FAIL → Revision / Shortening Engine
```

The Quality Gate is an evaluation component.

It does not perform corrections.

---

# Inputs

The Quality Gate should receive the artifacts produced by the PDF compilation stage.

At minimum:

```text
resume.tex
resume.pdf
compiler.log
```

The Quality Gate may also receive the `CompilationResult` from the PDF Compiler if that is already part of the existing API.

---

# Public API

Expose a simple API such as:

```python
result = quality_gate.evaluate(
    pdf_path=pdf_path,
    latex_path=latex_path,
    compiler_result=compiler_result,
)
```

The exact API may follow the existing project conventions, but the Quality Gate must remain independent of the CLI and LLM provider.

---

# Output

Return a structured `QualityGateResult`.

The result should contain:

```text
passed
issues
metrics
```

Example:

```python
QualityGateResult(
    passed=False,
    issues=[
        QualityIssue(...)
    ],
    metrics=QualityMetrics(...)
)
```

The result must provide enough information for the future Revision / Shortening Engine to decide what corrective action is required.

---

# Validation Philosophy

A resume passes the Quality Gate only when it is genuinely usable.

The following are separate checks:

```text
Compilation
Page Count
Overfull HBoxes
Missing Glyphs
Orphan Words
Text Overlap
```

The Quality Gate must not collapse everything into:

```text
page_count == 1
```

A one-page PDF with overlapping text is invalid.

A one-page PDF with missing glyphs is invalid.

A one-page PDF with other structural problems is invalid.

---

# Stage 1 – Fast Validation

Stage 1 must always run.

These checks should be cheap and deterministic.

## 1. Compilation

Verify that the PDF compilation succeeded.

A compilation failure is an immediate quality failure.

---

## 2. Exactly One Page

The final PDF must contain exactly one page.

Valid:

```text
page_count = 1
```

Invalid:

```text
page_count = 0
page_count > 1
```

The Quality Gate must report the observed page count.

---

## 3. Overfull HBoxes

Inspect the LaTeX compiler output/log for overfull horizontal boxes.

Any relevant overfull `\hbox` should cause a quality failure.

Record:

```text
overfull_hbox_count
```

Do not attempt to fix the problem.

---

## 4. Missing Glyphs

Inspect compiler output/logs for missing glyph warnings/errors.

Missing glyphs must cause a quality failure.

Record the relevant occurrences in the quality report.

---

# Stage 2 – PDF Geometry Validation

Stage 2 is required because page count alone is insufficient.

The system must detect cases where content technically fits on one page but is visually broken.

At minimum, investigate:

- text overlap
- orphan words

The implementation should determine whether these checks can be performed reliably using the current installed toolchain.

Do not automatically add a PDF library solely because the architecture mentions one.

If the existing toolchain is insufficient for reliable geometry analysis, evaluate and document the smallest justified dependency.

---

# Text Overlap Detection

Detect cases where independent text blocks overlap in the rendered PDF.

Example failure:

```text
Experience bullet 1
Experience bullet 2
```

rendering on top of each other.

A document with substantial or structurally significant text overlap must fail the Quality Gate even if:

```text
page_count == 1
```

The overlap check must operate on PDF geometry, not merely the LaTeX source.

The implementation should avoid false positives caused by:

- glyph-level bounding boxes
- intentional character spacing
- adjacent words touching normally
- overlapping decorative elements that are part of the template

The exact threshold should be configurable or clearly documented.

---

# Orphan Word Detection

Detect visually undesirable orphan words created by line wrapping.

Examples:

```text
Implemented a scalable distributed processing
architecture for
```

or:

```text
Developed and deployed
RESTful
```

where a single word is left alone on a line in a way that materially harms the resume layout.

The implementation must define a deterministic criterion for an orphan word.

The check must not inspect every character unnecessarily if a cheaper block/line-level analysis is sufficient.

The goal is to identify genuine problematic line wrapping, not ordinary short lines.

---

# Stage 2 Failure Reporting

When Stage 1 passes but Stage 2 fails, produce structured issues.

Example:

```text
PAGE_LAYOUT_OVERLAP
ORPHAN_WORD
```

Include useful metrics such as:

```text
page
section/region if determinable
line
text involved if available
```

The Quality Gate should not attempt to infer resume semantics beyond what is necessary to report the problem.

---

# Progressive Validation

The Quality Gate should use progressive validation.

```text
Stage 1
  ↓
Passed?
  ├── No → return failure
  │
  └── Yes
        ↓
Stage 2
        ↓
      Passed?
       ├── No → return failure
       └── Yes → PASS
```

Do not perform expensive PDF geometry analysis when Stage 1 already failed for an obvious reason, unless the implementation needs the additional information for diagnostics.

The Quality Gate should stop as soon as the result is conclusively known.

---

# Important Constraint: No Layout Squeezing

The Quality Gate must **never** modify layout to force a pass.

Do not:

- reduce font size
- reduce margins
- reduce line spacing
- reduce section spacing
- inject negative `\vspace`
- alter template geometry
- remove template elements
- rewrite LaTeX
- modify the PDF

The Quality Gate only evaluates.

---

# Important Constraint: No Content Removal

The Quality Gate must not remove content.

Content shortening belongs to the future Revision / Shortening Engine.

The Quality Gate should report the problem clearly enough for that component to act.

---

# Shortening Compatibility

The current resume content is intentionally ordered from highest importance to lowest importance.

Within a project:

```text
Bullet 1  ← highest importance
Bullet 2
Bullet 3
Bullet 4  ← lowest importance
```

Within work experience, the same principle applies.

The Quality Gate must **preserve this ordering** and must not reorder any content.

The future Revision / Shortening Engine will use this ordering to remove the lowest-priority removable content first.

The Quality Gate should therefore expose enough information for that engine to understand the nature of the failure.

---

# Compilation Budget

PDF compilation is considered inexpensive relative to LLM calls.

The Quality Gate may compile or inspect multiple times when necessary, but it must remain deterministic.

Do not prematurely optimize away useful validation simply to avoid a small number of compiler invocations.

The primary performance concern is expensive LLM revision calls, not local PDF compilation.

---

# Metrics

The Quality Gate should expose structured metrics.

At minimum:

```text
page_count
overfull_hbox_count
missing_glyph_count
overlap_count
orphan_word_count
```

Additional useful metrics may be added if they can be obtained reliably.

Do not invent metrics that cannot be measured accurately.

---

# Quality Issues

Define a strongly typed quality issue/code enum.

Suggested codes:

```python
class QualityIssueCode(str, Enum):
    COMPILATION_FAILED = "COMPILATION_FAILED"
    INVALID_PAGE_COUNT = "INVALID_PAGE_COUNT"
    OVERFULL_HBOX = "OVERFULL_HBOX"
    MISSING_GLYPH = "MISSING_GLYPH"
    TEXT_OVERLAP = "TEXT_OVERLAP"
    ORPHAN_WORD = "ORPHAN_WORD"
```

The exact naming may follow project conventions.

Do not use uncontrolled string literals throughout the Quality Gate.

---

# Error vs Failure

A Quality Gate failure means:

> The resume was successfully processed but is not submission-ready.

An internal Quality Gate error means:

> The system could not reliably perform the required evaluation.

These should be distinguishable.

Do not silently treat an analyzer failure as a successful quality result.

---

# Dependency Decision

The existing architecture may not include a PDF analysis library.

Before adding a new dependency:

1. Determine which checks are already available from compiler logs.
2. Determine which checks require rendered PDF geometry.
3. Use the smallest reliable mechanism for geometry analysis.
4. Add a dependency only when it provides necessary correctness.

In particular:

```text
Page count
Overfull hboxes
Missing glyphs
```

should preferably use compiler/log information where reliable.

Only checks such as:

```text
Text overlap
Orphan words
```

may require PDF-level geometry analysis.

Document any new dependency and why it is necessary.

---

# Testing

The Quality Gate requires both unit and integration tests.

## Unit Tests

Mock compiler/log/PDF analysis inputs where practical.

Cover:

### Compilation

- successful compilation
- compilation failure

### Page Count

- zero pages
- exactly one page
- two pages
- more than two pages

### Overfull HBoxes

- zero
- one
- multiple

### Missing Glyphs

- none
- one
- multiple

### Overlap

- no overlap
- legitimate adjacent text
- genuine overlap

### Orphans

- no orphan
- one orphan
- multiple orphans

---

# Regression Test: Broken One-Page PDF

Include a regression test for the known failure mode where:

```text
page_count == 1
```

but the document contains broken/overlapping text.

This test is mandatory.

The Quality Gate must reject such a document.

This prevents page count from becoming the sole success signal again.

---

# Integration Tests

Use real compiled PDFs for a small set of cases.

At minimum:

1. valid one-page resume
2. two-page resume
3. intentionally overlapping/broken one-page resume
4. resume containing a missing glyph if reproducible

The tests should verify the actual PDF output, not only mocked metrics.

---

# Determinism

Running the Quality Gate twice against the same artifacts must produce equivalent results.

Example:

```python
first = gate.evaluate(...)
second = gate.evaluate(...)

assert first == second
```

The Quality Gate must not:

- use randomness
- modify artifacts
- call an LLM
- depend on external services

---

# No Mutation

The Quality Gate must not modify:

- Resume
- LaTeX source
- PDF
- compiler log
- templates

It may create temporary analysis artifacts if required, but those must not alter the source artifacts.

---

# Out of Scope

Do NOT implement:

- Resume Generator
- JD Analyzer
- Resume Planner
- Markdown Serializer
- LaTeX Renderer
- PDF compilation
- LLM-based evaluation
- Resume shortening
- Revision Engine
- ATS scoring
- visual redesign
- layout squeezing

---

# Definition of Done

The task is complete when:

- `QualityGate` is implemented.
- A structured `QualityGateResult` exists.
- Structured quality issue codes exist.
- Compilation status is checked.
- Exactly-one-page validation is implemented.
- Overfull hbox detection is implemented.
- Missing-glyph detection is implemented.
- Text overlap detection is implemented reliably.
- Orphan-word detection is implemented with a documented deterministic rule.
- The known broken-one-page regression case fails.
- Stage 1 and Stage 2 validation are separated.
- Quality Gate never modifies content or layout.
- Quality Gate does not remove content.
- Metrics are exposed for downstream revision logic.
- Unit tests pass.
- Integration tests pass where the required tools are available.
