# Task 015 – PDF Compiler

## Objective

Implement the PDF Compiler.

The PDF Compiler is responsible for taking a complete LaTeX document and compiling it into a PDF.

Its only responsibility is:

```text
LaTeX Source
    ↓
PDF Compiler
    ↓
PDF
```

The compiler must be deterministic and independent of all resume-generation logic.

---

# Background

The current Resume Tailor pipeline is:

```text
Source Resume
      +
JobAnalysis
      +
ResumePlan
      +
Mode
      ↓
Resume Generator
      ↓
Resume Object
      ↓
Markdown Serializer
      ↓
LaTeX Renderer
      ↓
resume.tex
```

The next stage is PDF compilation.

The compiler must take the output of the LaTeX Renderer and produce a PDF that can later be inspected by the Quality Gate.

---

# Scope

Implement:

- PDF compiler
- LaTeX engine invocation
- isolated compilation directory
- compiler output capture
- compiler error handling
- PDF existence verification
- compilation logs
- configurable LaTeX engine

Do NOT implement:

- one-page validation
- page counting as a quality decision
- overfull hbox analysis
- orphan-word detection
- visual inspection
- content shortening
- revision logic
- LLM calls
- resume generation

---

# Project Structure

Use the existing compiler area if one already exists.

Recommended:

```text
src/
    compiler/
        __init__.py
        pdf_compiler.py
        models.py
        exceptions.py
```

---

# Public API

Expose a simple API such as:

```python
compiler = PDFCompiler()

result = compiler.compile(
    latex_source=latex_source,
    output_path=output_path,
)
```

The result should provide enough information for downstream components to locate:

- generated PDF
- compiler log
- compilation status

A suitable model might contain:

```python
class CompilationResult(BaseModel):
    success: bool
    pdf_path: Path | None
    log_path: Path | None
```

The exact model design may follow the project's existing Pydantic conventions.

---

# LaTeX Engine

Version 1 supports:

```text
pdflatex
```

The engine must be configurable.

Do not hardcode an absolute path such as:

```text
/usr/local/bin/pdflatex
```

Use the executable available through the system PATH unless the project configuration explicitly specifies another executable path.

---

# Compilation Input

The compiler should accept a complete LaTeX document.

For example:

```latex
\documentclass{article}
...
\begin{document}
...
\end{document}
```

The compiler must not attempt to modify or repair the LaTeX source.

---

# Isolated Compilation

Each compilation should occur in its own temporary or dedicated working directory.

Example:

```text
generated/
    compile_<unique-id>/
        resume.tex
        resume.pdf
        resume.log
        ...
```

The exact directory naming strategy is left to the implementation.

The important requirement is:

- compilation attempts must not interfere with one another
- concurrent compilations must be possible
- auxiliary files must not pollute the project root

---

# Repeated Compilation

The compiler will eventually be called multiple times during the revision loop.

Example:

```text
attempt 1 → compile
attempt 2 → compile
attempt 3 → compile
attempt 4 → compile
```

Each compilation must be isolated.

No state from a previous compilation should affect the next compilation.

---

# Compiler Command

The implementation should invoke the configured LaTeX engine with appropriate non-interactive options.

The compiler must never wait for interactive input.

For example, the implementation may use appropriate flags equivalent to:

```text
-interaction=nonstopmode
```

The exact command-line arguments should be chosen based on the configured LaTeX engine.

---

# Output Capture

Capture:

- stdout
- stderr
- process exit code

Store the useful compiler output in a log file.

The log should remain available when compilation fails.

---

# Success Conditions

Compilation is successful only if all of the following are true:

1. The LaTeX process exits successfully.
2. A PDF file is produced.
3. The PDF file exists at the expected path.
4. The PDF is readable as a file.

Do not consider compilation successful merely because the process exited with status `0`.

---

# Failure Conditions

Compilation must fail when:

- `pdflatex` is not installed.
- LaTeX executable cannot be found.
- LaTeX process exits with a failure status.
- PDF is not produced.
- Output file cannot be accessed.

---

# Error Handling

Create compiler-specific exceptions if they do not already exist.

Suggested:

```text
CompilerError
LatexEngineNotFoundError
CompilationFailedError
PDFNotGeneratedError
```

The compiler should provide useful diagnostics.

Example:

```text
LaTeX compilation failed.

Exit code: 1

See:
artifacts/attempt_1.log
```

Do not expose raw Python tracebacks for expected compilation failures.

---

# Logs

A compiler log must be retained for every compilation attempt.

Example:

```text
artifacts/
    attempt_1/
        resume.tex
        resume.pdf
        resume.log
```

If compilation fails:

```text
artifacts/
    attempt_1/
        resume.tex
        resume.log
```

The `.tex` and `.log` files should remain available for debugging.

---

# Artifact Preservation

The compiler should support an output directory supplied by the caller.

For example:

```python
compiler.compile(
    latex_source=latex_source,
    output_directory=Path("artifacts/attempt_1"),
)
```

The compiler should not decide the application's overall artifact naming convention.

The caller owns the attempt number and final artifact naming.

---

# Determinism

Given:

- identical LaTeX source
- identical compiler version
- identical configuration

the compiler should produce equivalent output.

The compiler must not modify the LaTeX source.

---

# No Mutation

The compiler must not modify:

- Resume
- JobAnalysis
- ResumePlan
- configuration
- templates

It receives LaTeX source and produces compilation artifacts.

---

# Unit Tests

The tests must not require a real LaTeX installation unless explicitly marked as integration tests.

## Unit Tests

Mock the subprocess invocation.

Cover:

- successful compilation
- compiler executable not found
- non-zero exit code
- missing PDF
- stdout/stderr capture
- log creation
- output path handling

---

# Integration Test

Add a separate integration test that runs only when `pdflatex` is available.

The test should:

1. Compile a minimal valid LaTeX document.
2. Verify the process succeeds.
3. Verify a PDF is generated.
4. Verify the PDF file exists.

The test should be safely skippable when `pdflatex` is unavailable.

---

# Example Minimal Test Document

Use a minimal document such as:

```latex
\documentclass{article}

\begin{document}

Resume Tailor PDF Compiler Test

\end{document}
```

Do not use a real resume for the compiler unit tests.

---

# Do NOT Perform Quality Analysis

The compiler must not decide:

```text
Is this one page?
Is spacing good?
Are there orphan words?
Are there overfull hboxes?
Is the resume visually good?
```

Those decisions belong to the Quality Gate.

The compiler only answers:

> "Did LaTeX successfully produce a PDF?"

---

# Out of Scope

Do NOT implement:

- PDF parsing
- page counting as a quality decision
- PyMuPDF analysis
- one-page validation
- orphan-word analysis
- overfull hbox analysis
- visual analysis
- shortening
- revision engine
- ATS scoring
- LLM integration

---

# Definition of Done

The task is complete when:

- `PDFCompiler` is implemented.
- `pdflatex` can be invoked through the compiler.
- Compilation occurs in an isolated working directory.
- stdout/stderr are captured.
- compiler logs are preserved.
- compilation failures produce clear exceptions.
- successful compilation returns a usable PDF path.
- missing PDF output is detected.
- output directories are caller-controlled.
- repeated compilations do not interfere with one another.
- unit tests pass.
- the optional integration test passes when `pdflatex` is available.
