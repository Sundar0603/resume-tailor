# Task 006 – Job Description Analyzer

## Objective

Implement the Job Description Analyzer.

The analyzer is responsible for converting a raw job description into a structured `JobAnalysis` object that can later be consumed by the Resume Generator.

The analyzer does **not** generate resumes, modify resumes, score resumes, or perform ATS optimization.

It only extracts and structures information from the supplied Job Description.

---

# Background

The Resume Tailor pipeline is designed as a sequence of independent components.

```
Raw Resume
    │
    ▼
Resume Parser
    │
    ▼
Resume
    │
    ▼
Resume Validator
    │
    ▼
Resume Generator
```

The Resume Generator should **not** receive a giant block of raw job description text.

Instead, the Job Description should first be analyzed into a structured object.

The pipeline becomes:

```
Raw Resume
        │
        ▼
Resume Parser
        │
        ▼
Resume

Raw Job Description
        │
        ▼
Job Description Analyzer
        │
        ▼
JobAnalysis

Resume
      +
JobAnalysis
        │
        ▼
Resume Generator
```

This keeps responsibilities separated and makes the Generator significantly simpler.

---

# Scope

Implement:

- JobAnalysis model
- JDAnalyzer
- Prompt template
- Provider abstraction
- Response parsing
- Validation
- Unit tests

Do NOT implement:

- Resume generation
- ATS scoring
- Resume recommendations
- Company research
- Internet lookups
- Rendering
- PDF generation

---

# Project Structure

```
src/
    analyzer/
        __init__.py
        analyzer.py
        models.py
        prompts.py
        provider.py
        exceptions.py
```

---

# Public API

The analyzer exposes a single public API.

```python
analysis = analyzer.analyze(job_description)
```

Input:

```python
job_description: str
```

Output:

```python
JobAnalysis
```

The analyzer must be stateless.

---

# JobAnalysis Model

Implement using Pydantic v2.

```python
class JobAnalysis(BaseModel):

    company: str | None

    role: str

    seniority: str | None

    summary: str

    required_skills: list[str]

    preferred_skills: list[str]

    technologies: list[str]

    domains: list[str]

    responsibilities: list[str]

    qualifications: list[str]

    nice_to_have: list[str]

    keywords: list[str]
```

The model should contain only information required by downstream resume generation.

Do not include scoring, recommendations, or AI reasoning.

---

# Analyzer Responsibilities

The analyzer must:

- accept raw JD text
- construct the analyzer prompt
- invoke the LLM provider
- parse the returned JSON
- validate it with Pydantic
- return JobAnalysis

The analyzer must never return raw JSON.

---

# Provider Abstraction

The analyzer must not depend on any specific LLM provider.

Create a provider abstraction that can later support:

- OpenAI
- Anthropic
- Gemini
- Ollama

The analyzer should communicate only through this abstraction.

Example:

```python
provider.generate(prompt) -> str
```

Provider implementation itself is out of scope.

Only define the interface.

---

# Prompt

Create a dedicated prompt template.

The prompt must instruct the model to:

- analyze the supplied Job Description
- extract only requested fields
- infer reasonable technologies and domains when explicitly implied
- avoid inventing company information
- return valid JSON
- strictly follow the required schema

Prompt should be stored separately from implementation.

---

# JSON Parsing

The analyzer should expect JSON output.

Flow:

```
Prompt
    │
    ▼
LLM

JSON String
    │
    ▼
Parse JSON

dict
    │
    ▼
Pydantic Validation

JobAnalysis
```

Malformed JSON should raise an exception.

Schema validation failures should raise an exception.

---

# Validation

The analyzer must validate:

- role exists
- summary exists
- required_skills is present
- keywords is present

Optional fields may be empty.

---

# Exceptions

Create analyzer-specific exceptions.

Suggested examples:

```
AnalyzerError

InvalidAnalyzerResponse

InvalidAnalyzerJSON

JobAnalysisValidationError
```

---

# Unit Tests

Implement tests covering:

## Valid Cases

- complete JD
- short JD
- JD without company
- JD with minimal requirements

---

## Invalid Cases

- malformed JSON
- missing role
- missing summary
- invalid schema
- provider failure

---

## Parsing

Verify JSON correctly becomes JobAnalysis.

---

## Validation

Verify invalid responses raise appropriate exceptions.

---

# Design Principles

The analyzer should be:

- deterministic
- stateless
- side-effect free
- independently testable

It should not know anything about resumes.

Its only responsibility is:

```
Raw Job Description

↓

JobAnalysis
```

---

# Out of Scope

Do NOT implement:

- Resume Generator
- Resume ranking
- ATS optimization
- Company research
- Internet searches
- Skill matching
- Resume scoring
- PDF rendering
- CLI integration

---

# Definition of Done

Task is complete when:

- analyzer package exists
- JobAnalysis model implemented
- analyzer implemented
- provider abstraction implemented
- prompt implemented
- JSON parsing implemented
- validation implemented
- comprehensive unit tests pass
- component is fully independent from resume generation