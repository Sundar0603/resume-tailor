# Task 013 – Markdown Serializer

## Objective

Implement the Markdown Serializer.

The serializer converts a structured `Resume` object into the canonical Markdown representation defined by `RESUME_SCHEMA.md`.

The serializer must be deterministic and must not use an LLM.

It must not modify the `Resume` object.

---

# Background

The Resume Generator produces a structured `Resume` object.

The next stage must be able to persist and inspect that object as Markdown.

The pipeline is:

```text
Resume Generator
        │
        ▼
    Resume Object
        │
        ▼
Markdown Serializer
        │
        ▼
generated.md
```

Markdown remains the human-readable representation of resume content.

The canonical Markdown schema is defined in:

```text
docs/RESUME_SCHEMA.md
```

The serializer must follow that schema exactly.

---

# Scope

Implement:

* `MarkdownSerializer`
* deterministic Resume → Markdown serialization
* serialization tests
* round-trip tests with the existing parser

Do NOT implement:

* LLM calls
* resume generation
* JD analysis
* LaTeX rendering
* PDF generation
* quality validation
* page optimization
* shortening
* revision logic

---

# Project Structure

Use the existing renderer/serialization area of the project.

Recommended structure:

```text
src/
    renderer/
        __init__.py
        markdown_serializer.py
```

If a renderer package already exists, place the serializer there rather than creating a duplicate package.

Do not reorganize unrelated modules.

---

# Public API

Expose:

```python
serializer = MarkdownSerializer()

markdown = serializer.serialize(resume)
```

Input:

```python
Resume
```

Output:

```python
str
```

The serializer must return the complete Markdown document, including YAML Front Matter.

---

# Serialization Rules

The output must follow the canonical section order:

```text
Metadata
Contact
Summary
Skills
Work Experience
Projects
Education
```

Do not reorder these sections.

---

# Metadata

Serialize the YAML Front Matter.

Example:

```yaml
---
resume: cybersecurity
template: cybersecurity
version: 1.0
---
```

Use the values from:

```python
resume.metadata
```

Do not invent metadata.

---

# Contact

Serialize:

```markdown
# Contact

Name: ...

Phone: ...

Email: ...

LinkedIn: ...

GitHub: ...
```

Use the canonical schema field names.

---

# Summary

Serialize as a single paragraph.

```markdown
# Summary

...
```

Do not convert the summary into bullets.

---

# Skills

Serialize every skill category.

Example:

```markdown
# Skills

## Security

- SOC Tooling
- Threat Intelligence

## Backend

- Spring Boot
- Redis
```

Rules:

* Preserve category order.
* Preserve skill order.
* Preserve all skills.
* Do not deduplicate.
* Do not alphabetize unless the Resume object is already ordered that way.
* Do not infer or modify categories.

---

# Work Experience

Serialize every experience in order.

Example:

```markdown
# Work Experience

## Experience

Company: Zoho Corporation

Role: Software Developer

Employment Type: Full Time

Duration: May 2024 - Present

Location: Chennai

Technologies:

- Java
- Spring Boot

Domains:

- Threat Intelligence
- API Security

Highlights:

- Built ...
- Designed ...
- Developed ...
```

Rules:

* Preserve experience order.
* Preserve bullet order exactly.
* Preserve technology order.
* Preserve domain order.
* Never sort bullets.
* Never shorten bullets.
* Never rewrite content.

The serializer must serialize exactly what is present in the `Resume` object.

---

# Projects

Serialize every project in order.

Example:

```markdown
# Projects

## Project

Name: Triage Studio

Type: Personal

Repository: https://...

Technologies:

- Python
- OpenAI APIs

Domains:

- AI Agents
- Security

Highlights:

- Built ...
- Developed ...
```

Rules:

* Preserve project order.
* Preserve bullet order.
* Preserve technology order.
* Preserve domain order.
* Do not sort.
* Do not shorten.
* Do not rewrite.

---

# Education

Serialize every education entry in order.

Example:

```markdown
# Education

## Degree

Institution: ...

Degree: ...

Major: ...

Duration: ...

CGPA: ...

Location: ...
```

---

# Optional Fields

Optional fields may be omitted when they are absent.

Do not serialize:

```text
None
null
"None"
```

For example, if `repository` is absent:

```markdown
Name: Triage Studio

Type: Personal

Technologies:
```

There should be no:

```markdown
Repository: None
```

---

# Runtime Metadata

The Markdown schema is the canonical source of resume content.

Runtime-only metadata such as:

* generated entity lineage
* temporary validation state
* revision state
* quality-gate results
* internal analysis data

must not be introduced into the canonical Markdown format unless explicitly defined by `RESUME_SCHEMA.md`.

Do not modify `RESUME_SCHEMA.md` as part of this task.

In particular, do not add runtime IDs or `source` fields to the canonical Markdown simply because they exist on the runtime `Resume` model.

The serializer must distinguish between:

```text
Resume model data
```

and:

```text
Canonical Markdown data
```

Only fields defined by the schema should be serialized.

---

# Determinism

Serializing the same `Resume` object multiple times must produce byte-for-byte identical output.

Example:

```python
first = serializer.serialize(resume)
second = serializer.serialize(resume)

assert first == second
```

The serializer must not:

* use randomness
* use timestamps
* use UUIDs
* depend on dictionary iteration order
* perform network requests

---

# No Mutation

Serialization must not modify the Resume.

Example:

```python
before = resume.model_dump(deep=True)

serializer.serialize(resume)

after = resume.model_dump(deep=True)

assert before == after
```

---

# Round-Trip Compatibility

The serializer must work with the existing `ResumeParser`.

The following must succeed:

```text
Markdown
   ↓
ResumeParser
   ↓
Resume
   ↓
MarkdownSerializer
   ↓
Markdown
   ↓
ResumeParser
   ↓
Resume
```

The final Resume should be semantically equivalent to the original Resume.

Example:

```python
original = parser.parse("content/backend.md")

markdown = serializer.serialize(original)

reparsed = parser.parse_string(markdown)

assert reparsed == original
```

If the parser currently does not support parsing from a string, add the smallest necessary API needed to perform this test, without changing existing parser behavior.

---

# Content Preservation

The serializer must preserve:

* text
* bullet order
* entity order
* skill order
* technologies
* domains
* highlights
* URLs
* punctuation
* capitalization

The serializer must not "clean up" or normalize resume content.

It is a serializer, not an editor.

---

# New Generated Entities

The Serializer must correctly serialize generated Projects and Skill Categories.

For example, a generated project should look exactly like any other project in the canonical Markdown representation.

Do not expose runtime-only source metadata such as:

```text
source=GENERATED
```

unless that field is later added to the canonical schema.

The serialized output must remain compliant with `RESUME_SCHEMA.md`.

---

# Testing

Implement tests covering:

## Basic Serialization

* metadata
* contact
* summary
* skills
* experience
* projects
* education

---

## Ordering

Verify:

* section order
* experience order
* project order
* skill-category order
* bullet order

---

## Optional Fields

Verify optional fields are omitted when absent.

Verify `"None"` is never serialized.

---

## Content Preservation

Verify exact preservation of:

* bullet text
* punctuation
* capitalization
* URLs
* technology names
* domain names

---

## Determinism

Serializing the same object twice must produce identical output.

---

## No Mutation

Verify the Resume object is unchanged after serialization.

---

## Round Trip

Test:

```text
Parse
→ Serialize
→ Parse
```

and verify semantic equivalence.

Use all available canonical resumes as fixtures if practical.

---

# Error Handling

The serializer should raise a clear serializer-specific exception if it receives an object that cannot be serialized.

Suggested exception:

```python
SerializationError
```

Do not silently drop required fields.

Do not attempt to repair malformed Resume objects.

Resume validity is handled by the Validator.

---

# Out of Scope

Do NOT implement:

* LLM logic
* Resume Generator changes
* JD Analyzer changes
* LaTeX rendering
* PDF compilation
* page counting
* overflow detection
* orphan-word detection
* shortening
* revision loops
* ATS optimization

---

# Definition of Done

The task is complete when:

* `MarkdownSerializer` is implemented.
* A `Resume` can be serialized into canonical Markdown.
* YAML Front Matter is generated correctly.
* Section order is deterministic.
* Entity and bullet order is preserved.
* Optional fields are handled correctly.
* Runtime-only metadata is not leaked into canonical Markdown.
* Serialization does not mutate the Resume.
* Serialization is deterministic.
* Parse → Serialize → Parse round-trip tests pass.
* Unit tests pass.
