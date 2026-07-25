# Task 003 - Enrich Domain Models

The parser and Pydantic migration are complete.

This task focuses on enriching the domain models by adding commonly used helper methods and runtime-generated entity identifiers.

The parser should continue to function exactly as before.

---

# Part 1 - Runtime Entity IDs

Every repeatable entity should expose a stable runtime identifier.

Add an `id` field to the following models:

- Experience
- Project
- Education
- SkillCategory

## ID Generation

These IDs **must NOT** be stored in the Markdown resumes.

They are **runtime-generated** by the parser while constructing the domain models.

The Markdown schema remains unchanged.

Example IDs:

```
Experience
-----------
exp_001
exp_002

Project
--------
proj_001
proj_002

Education
---------
edu_001

Skill Category
--------------
skill_001
skill_002
```

These IDs should be deterministic.

Parsing the same resume multiple times should always generate identical IDs.

The IDs exist only in memory and are intended to uniquely identify entities during later stages such as:

- Resume generation
- Revision engine
- Quality gate
- Reporting

---

# Part 2 - Resume Helper Methods

Implement the following helper methods on the `Resume` model.

---

## get_skills(category)

Returns all skills belonging to a category.

Example:

```python
resume.get_skills("Backend")
```

Returns:

```python
[
    "Spring Boot",
    "REST APIs",
    "Redis"
]
```

If the category does not exist, return an empty list.

---

## all_skills()

Returns a flattened list of every skill across all categories.

Example:

```python
resume.all_skills()
```

Returns:

```python
[
    "Python",
    "Java",
    "Spring Boot",
    "Redis",
    ...
]
```

---

## total_skills()

Returns the total number of individual skills.

---

## total_experiences()

Returns the total number of experiences.

Equivalent to:

```python
len(resume.experiences)
```

---

## total_projects()

Returns the total number of projects.

---

## total_education()

Returns the total number of education entries.

---

## total_highlights()

Returns the total number of highlight bullets across:

- Experiences
- Projects

---

## word_count()

Returns the approximate total number of words contained in:

- Summary
- Experience highlights
- Project highlights

This method will later be used by the Quality Gate.

---

# Part 3 - Entity Helper Methods

## Experience.word_count()

Returns the total number of words across all highlight bullets.

---

## Project.word_count()

Returns the total number of words across all highlight bullets.

---

## SkillCategory.skill_count()

Returns the number of skills in the category.

---

# Implementation Guidelines

These methods are convenience methods only.

They should:

- Not perform validation.
- Not modify state.
- Not perform parsing.
- Not perform rendering.
- Not call any external services.
- Not use AI.

They should simply expose useful information already contained within the models.

---

# Do NOT

Do not:

- Modify the Markdown schema.
- Store IDs inside the Markdown resumes.
- Add validation logic.
- Add ATS scoring.
- Add rendering logic.
- Add LLM logic.
- Change parser behavior (other than assigning runtime IDs during parsing).

---

# Verification

The following should work:

```python
resume.get_skills("Backend")

resume.all_skills()

resume.total_skills()

resume.total_projects()

resume.total_experiences()

resume.total_education()

resume.total_highlights()

resume.word_count()
```

Each entity should expose a runtime-generated ID.

Example:

```python
resume.experiences[0].id
# exp_001

resume.projects[1].id
# proj_002

resume.education[0].id
# edu_001

resume.skills[0].id
# skill_001
```

Parsing the same resume multiple times should always produce the same IDs.

All existing parser tests should continue to pass.

---

# Definition of Done

The task is complete when:

- Runtime-generated IDs are available for all repeatable entities.
- No IDs are stored in the Markdown resumes.
- All helper methods are implemented.
- The parser continues to pass all existing tests.
- Existing parser behavior remains unchanged.
