# Task 005 - Resume Validator

## Objective

Implement the Resume Validator.

The validator is responsible for validating generated resumes before they proceed to rendering, compilation, and quality analysis.

The validator does **not** load resumes from disk or know about the project structure. It simply validates a generated resume against the source resume that was used to start the generation process.

---

# Background

Every resume located in the `content/` directory is considered a canonical resume.

The project assumes there is at least one canonical resume.

The Resume Generator begins with one canonical resume selected by the user.

That resume becomes the **source resume** for the generation process.

The validator compares the generated resume against this source resume to ensure that the Resume Generator has not violated any structural or immutable constraints.

The validator does not know or care where the source resume originated. It simply compares two `Resume` objects.

---

# Scope

Implement a validator for the `Resume` domain model.

The validator must:

- Validate structural integrity.
- Validate required fields.
- Validate entity consistency.
- Validate immutable constraints.
- Validate runtime-generated IDs.
- Validate entity sources.

The validator must never modify either resume.

---

# Project Structure

Implement the validator under a dedicated package.

```text
src/
└── validation/
    ├── __init__.py
    ├── validator.py
    ├── models.py
    ├── codes.py
    └── exceptions.py
```

### validator.py

Contains the main `ResumeValidator`.

### models.py

Contains:

- `ValidationResult`
- `ValidationIssue`

### codes.py

Contains the `ValidationCode` enum.

Validation logic must never use raw string literals.

### exceptions.py

Reserved for future use.

It may remain empty if no custom exceptions are currently required.

---

# Validator API

The validator compares the generated resume against the resume that was provided to the Resume Generator.

Example:

```python
validator.validate(
    source_resume=source_resume,
    generated_resume=generated_resume,
)
```

The validator must not:

- Read files from disk.
- Load resumes from the `content/` directory.
- Depend on application configuration.
- Mutate either resume.

The validator simply compares the supplied `Resume` objects.

---

# Validation Philosophy

The validator is a pure component.

```text
Source Resume
      │

Generated Resume
      │
      ▼
Resume Validator
      │
      ▼
ValidationResult
```

The validator must:

- be deterministic
- have no side effects
- not perform rendering
- not perform AI operations
- not mutate either `Resume` object

---

# Validation Models

Implement the following models.

## ValidationResult

Represents the outcome of validation.

Example:

```python
ValidationResult(
    is_valid=False,
    errors=[],
    warnings=[],
    info=[]
)
```

---

## ValidationIssue

Represents a single validation issue.

Example:

```python
ValidationIssue(
    code=ValidationCode.DUPLICATE_ENTITY_ID,
    entity_id="exp_001",
    field="id",
    message="Duplicate entity ID."
)
```

Each issue should contain:

- validation code
- human-readable message
- optional entity ID
- optional field name

The models should follow the project's existing Pydantic conventions.

---

# Validation Rules

## Resume

The generated resume must contain:

- Contact
- Summary
- Skills
- Experience
- Projects
- Education

---

## Work Experience

The generated resume must contain exactly **two** work experiences.

Each experience must contain:

- id
- source
- company
- title
- duration
- technologies
- domains
- highlights

Validation rules:

- Exactly two experiences.
- IDs are unique.
- Source exists.
- Technologies list exists.
- Domains list exists.
- Highlights are not empty.

The following fields are immutable and must exactly match the corresponding work experience in the source resume:

- company
- title
- duration

The Resume Generator must never:

- add work experiences
- remove work experiences
- reorder work experiences

---

## Projects

The generated resume must contain at least **two** projects.

There is no upper limit.

Each project must contain:

- id
- source
- name
- highlights

Optional:

- technologies
- links

Validation rules:

- At least two projects.
- IDs are unique.
- Source exists.
- Highlights are not empty.

Projects are fully mutable.

The Resume Generator may:

- modify existing projects
- rename projects
- rewrite projects
- modify technologies
- modify highlights
- generate entirely new projects

Every generated project must receive a unique runtime-generated ID.

---

## Skills

At least one skill category must exist.

Each category must contain:

- id
- source
- name
- skills

Validation rules:

- At least one skill category.
- IDs are unique.
- Source exists.
- Category name exists.
- Skills list exists.
- Duplicate IDs are not allowed.
- Duplicate skills within the same category are not allowed.

Skills are fully mutable.

The Resume Generator may:

- add skill categories
- remove skill categories
- rename categories
- modify skills within a category
- remove skills
- add new skills
- reorganize skills across categories

Every generated skill category must receive a unique runtime-generated ID.

---

## Education

At least one education entry must exist.

Each entry must contain:

- id
- source
- institution
- degree

Education is immutable.

The generated resume must exactly match the education section in the source resume.

---

## Contact

Required:

- name
- email
- phone
- location

Contact information is immutable.

The generated resume must exactly match the source resume.

---

## Summary

Summary must exist.

Summary must not be empty.

---

# Runtime IDs

Every entity must have a runtime-generated ID.

Supported entity types:

- Experience
- Project
- Education
- SkillCategory

IDs must be unique within their entity type.

---

# Entity Sources

Every entity must expose its origin.

Use the existing enum.

Example:

```python
EntitySource.CANONICAL
EntitySource.GENERATED
```

Validation rules:

- Every entity has a source.
- Source value is valid.

Generated entities are currently supported for:

- Projects
- Skill Categories

---

# Validation Codes

Implement a strongly typed `ValidationCode` enum.

Do not use raw string literals such as:

```python
"DUPLICATE_ID"
"MISSING_SUMMARY"
"INVALID_SOURCE"
```

Instead:

```python
class ValidationCode(str, Enum):
    DUPLICATE_ENTITY_ID = "DUPLICATE_ENTITY_ID"
    INVALID_SOURCE = "INVALID_SOURCE"
    MISSING_SUMMARY = "MISSING_SUMMARY"
    MISSING_CONTACT = "MISSING_CONTACT"
    INVALID_EXPERIENCE_COUNT = "INVALID_EXPERIENCE_COUNT"
    INVALID_PROJECT_COUNT = "INVALID_PROJECT_COUNT"
    MODIFIED_IMMUTABLE_FIELD = "MODIFIED_IMMUTABLE_FIELD"
```

The list may evolve over time.

The enum should provide a stable interface for downstream consumers such as:

- CLI
- Reporter
- Quality Gate
- Revision Engine

---

# Warnings

Generate warnings for:

- Summary shorter than 20 words.
- Summary longer than 120 words.
- Experience with more than 8 highlights.
- Project with more than 6 highlights.
- Empty skill category.

Warnings do not invalidate the resume.

---

# Extensibility

Design the validator so that validation rules are modular and easy to extend.

Avoid placing all validation logic inside a single large method.

Prefer smaller validation methods such as:

- `validate_contact(...)`
- `validate_summary(...)`
- `validate_skills(...)`
- `validate_experience(...)`
- `validate_projects(...)`
- `validate_education(...)`
- `validate_runtime_ids(...)`
- `validate_entity_sources(...)`

The developer should be able to add or modify validation rules without modifying existing code.

The validator should remain maintainable as additional validation rules are introduced.

---

# Do NOT

Do not implement:

- ATS validation
- Job description matching
- Grammar checking
- Rendering validation
- PDF validation
- One-page validation
- AI evaluation

These belong to later stages of the pipeline.

---

# Verification

## Valid Resume

A valid generated resume should produce:

```python
ValidationResult(
    is_valid=True
)
```

---

## Invalid Resume

Examples:

- Three work experiences.
- One work experience.
- Duplicate IDs.
- Missing summary.
- Missing highlights.
- Empty technologies list.
- Invalid source.
- Missing contact information.
- Modified company.
- Modified job title.
- Modified employment duration.
- Modified education.
- Modified contact information.

These should produce:

```python
ValidationResult(
    is_valid=False
)
```

with appropriate validation issues.

---

## Generated Projects

The following must be considered valid:

```text
Canonical Project
Canonical Project
Generated Project
Generated Project
Generated Project
```

provided all projects satisfy the required structure.

---

## Generated Skills

The following must be considered valid:

```text
Programming Languages (Canonical)
Frameworks (Canonical)

↓

Programming Languages (Generated)
Cloud & DevOps (Generated)
AI & LLMs (Generated)
```

provided all skill categories satisfy the required structure.

---

# Definition of Done

The task is complete when:

- `ResumeValidator` is implemented.
- `ValidationResult` is implemented.
- `ValidationIssue` is implemented.
- `ValidationCode` enum is implemented.
- Structural validation rules are enforced.
- Runtime-generated IDs are validated.
- Entity sources are validated.
- Immutable sections are compared against the supplied source resume.
- Generated projects are supported.
- Generated skill categories are supported.
- The validator remains a pure, stateless component.
- Validation logic is modular and easy to extend.
- Unit tests cover both valid and invalid generated resumes.
