# Task 010 – Job Description Analyzer CLI

## Objective

Integrate the Job Description Analyzer into the CLI and verify that it can analyze a real job description using the configured AI provider.

This task is intentionally limited in scope.

The goal is **not** to generate a tailored resume.

The goal is to verify that:

- CLI
- Job Description Analyzer
- AI Provider
- LLM
- JSON Parsing
- Pydantic Validation

work together correctly.

---

# Background

The following components have already been implemented:

- CLI
- Configuration Manager
- Credential Manager
- Provider Factory
- AI Providers
- Job Description Analyzer

The analyzer should now be exercised end-to-end using a real LLM.

---

# Scope

Implement:

- CLI command
- Job description input
- Analyzer execution
- JSON parsing
- Validation
- Pretty printing

Do NOT implement:

- Resume parsing
- Resume generation
- Resume tailoring
- Rendering
- PDF generation
- Quality gate
- Reports

---

# Command

Implement:

```
resume-tailor analyze
```

---

# Execution Flow

```
resume-tailor analyze

↓

Read Job Description

↓

JobDescriptionAnalyzer

↓

ProviderFactory

↓

LLM

↓

JSON

↓

Pydantic Validation

↓

JobAnalysis

↓

Pretty Print
```

---

# Job Description Input

When executed, the CLI should prompt the user to paste a job description.

Example:

```
Paste the job description below.

Press Ctrl+D (Ctrl+Z on Windows) when finished.

--------------------------------------------------
```

The CLI should read until EOF.

No file support is required for this task.

---

# Analyzer Execution

Construct the analyzer using the existing infrastructure.

The CLI should not communicate directly with the provider.

The CLI should only interact with:

```
JobDescriptionAnalyzer
```

The analyzer remains responsible for:

- prompt construction
- LLM invocation
- JSON parsing
- validation

---

# Successful Output

Pretty-print the resulting JobAnalysis.

Example:

```
Job Analysis

Company
--------
Acme Inc.

Role
----
Senior Backend Engineer

Seniority
----------
Senior

Summary
-------
...

Required Skills
---------------
• Python
• FastAPI
• PostgreSQL

Preferred Skills
----------------
• Redis
• Docker

Technologies
------------
• Python
• PostgreSQL
• AWS

Domains
-------
• Backend Development

Responsibilities
----------------
...

Qualifications
--------------
...

Nice To Have
------------
...

Keywords
--------
...
```

The formatting does not need to exactly match the example.

It should simply be human-readable.

---

# Error Handling

Handle gracefully:

Empty input

Provider errors

Invalid JSON returned by the model

Validation failures

Unexpected analyzer exceptions

Show clear user-friendly messages.

Do not display Python stack traces.

---

# Design Constraints

The CLI must not:

- construct prompts
- parse JSON
- validate JobAnalysis
- communicate directly with providers

The CLI should only:

- read user input
- invoke JobDescriptionAnalyzer
- display the result

All analyzer logic remains inside the analyzer component.

---

# Manual Verification

Verify the following scenarios manually.

## Scenario 1

Paste a valid job description.

Expected:

Analyzer returns a valid JobAnalysis.

---

## Scenario 2

Paste an empty input.

Expected:

Friendly validation message.

---

## Scenario 3

Disconnect the provider (for example, stop Ollama).

Expected:

Clear provider error.

---

## Scenario 4

Force the model to return invalid JSON (temporary prompt modification is acceptable).

Expected:

JSON parsing / validation failure is handled gracefully.

---

## Scenario 5

Run against multiple real job descriptions.

Examples:

- Backend Engineer
- Full Stack Developer
- Cybersecurity Engineer

Verify that the analyzer extracts meaningful structured information.

---

# Out of Scope

Do NOT implement:

Resume Parser

Resume Generator

Resume Validation

Renderer

Compiler

Quality Gate

Reports

Streaming

Conversation Memory

Retry Policies

---

# Definition of Done

Task is complete when:

✓ `resume-tailor analyze` is implemented.

✓ Users can paste a job description.

✓ The analyzer is invoked successfully.

✓ The configured provider is used automatically.

✓ The returned JSON is parsed successfully.

✓ The resulting JobAnalysis is validated.

✓ The JobAnalysis is displayed in a human-readable format.

✓ Expected failures are handled gracefully.

✓ Manual verification scenarios pass.
