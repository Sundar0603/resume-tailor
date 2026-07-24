# Task 1 — Implement Resume Parser

## Objective

Implement the Resume Parser responsible for converting a schema-compliant Markdown resume into an in-memory `Resume` object.

The parser must be deterministic and must not use any LLMs.

---

# Background

The project uses Markdown as the canonical source of truth for all master resumes.

Every resume conforms to the schema defined in `docs/RESUME_SCHEMA.md`.

The parser's responsibility is to transform a Markdown document into strongly typed domain objects.

The parser must **only parse**.

Validation is implemented separately.

---

# Scope

This task includes:

- Reading Markdown resume files.
- Parsing YAML front matter.
- Parsing every section defined in the schema.
- Constructing the corresponding domain objects.
- Returning a populated `Resume` object.

This task does **not** include validation.

This task does **not** include AI.

This task does **not** include rendering.

---

# Assumptions

Assume:

- All input resumes follow `RESUME_SCHEMA.md`.
- The three master resumes already exist under:

```
content/
    backend.md
    fullstack.md
    cybersecurity.md
```

---

# Functional Requirements

The parser shall support the following sections.

## Metadata

Parse YAML front matter.

Required fields:

- resume
- template
- version

---

## Contact

Parse:

- Name
- Phone
- Email
- LinkedIn
- GitHub

Return a `Contact` object.

---

## Summary

Return the summary as a string.

---

## Skills

Parse every skill category.

Each category becomes a `SkillCategory`.

Each skill becomes an element of a list.

---

## Work Experience

Parse every `## Experience` block.

Return a list of `Experience` objects.

Each object contains:

- Company
- Role
- Employment Type
- Duration
- Location
- Technologies
- Domains
- Highlights

---

## Projects

Parse every `## Project` block.

Return a list of `Project` objects.

Each object contains:

- Name
- Type
- Repository
- Technologies
- Domains
- Highlights

---

## Education

Parse every `## Degree` block.

Return a list of `Education` objects.

---

# Implementation Guidelines

The parser should be modular.

Suggested architecture:

```
ResumeParser
    ├── MetadataParser
    ├── ContactParser
    ├── SummaryParser
    ├── SkillsParser
    ├── ExperienceParser
    ├── ProjectParser
    └── EducationParser
```

Each parser should only understand one section.

Avoid one large parser implementation.

---

# Parsing Rules

The parser must not infer information.

Example:

Correct:

```
Company: Zoho Corporation
```

Incorrect:

```
## Zoho Corporation
```

The parser should rely only on the schema.

No heuristic parsing.

No guessing.

No AI.

---

# Error Handling

The parser may assume schema-compliant input.

If parsing fails because the document violates the schema, raise a parser exception.

Do not attempt automatic recovery.

---

# Out of Scope

The following are **not** part of this task.

- Resume validation
- LLM integration
- ATS scoring
- JD parsing
- Resume generation
- Markdown rendering
- LaTeX rendering
- PDF generation
- Quality gate

---

# Deliverables

The implementation should produce:

```
src/
    parser/
        resume_parser.py
        metadata_parser.py
        contact_parser.py
        summary_parser.py
        skills_parser.py
        experience_parser.py
        project_parser.py
        education_parser.py
```

---

# Acceptance Criteria

The following code should execute successfully.

```python
parser = ResumeParser()

resume = parser.parse("content/cybersecurity.md")
```

The resulting object should contain:

```python
resume.metadata.resume == "cybersecurity"

resume.contact.name == "Sundar S"

len(resume.skills) > 0

len(resume.experiences) == 2

len(resume.projects) == 2

len(resume.education) == 1
```

The parser must work for:

- backend.md
- fullstack.md
- cybersecurity.md

without modification.

---

# Verification

The task is considered complete when the following checks pass.

### Check 1

All three resumes parse successfully.

---

### Check 2

No exceptions are thrown for valid resumes.

---

### Check 3

Every section is populated correctly.

---

### Check 4

Experience count matches the Markdown.

---

### Check 5

Project count matches the Markdown.

---

### Check 6

Skills are grouped correctly.

---

### Check 7

No parser uses AI or heuristic extraction.

---

# Definition of Done

The task is complete when:

- Every master resume parses successfully.
- Every section is converted into the appropriate domain object.
- No validation logic exists inside the parser.
- No rendering logic exists inside the parser.
- No AI is used.
- The parser is deterministic.
- The implementation is modular and follows the project architecture.
