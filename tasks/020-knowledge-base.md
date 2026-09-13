# Task 020 — Introduce Knowledge Base as the Canonical Data Source

## Objective

Refactor Resume Tailor so that the four existing role-specific resumes are **no longer the source of truth for canonical resume data**.

Introduce a single **Knowledge Base** containing all human-verified canonical career information.

The existing resumes should remain available, but they become **role-specific views/curated resumes** built from the Knowledge Base rather than authoritative sources.

The core principle is:

> **Knowledge Base = source of truth for canonical content.**
>
> **Generated content must never enter the Knowledge Base.**

This change should make the system capable of selecting and reusing relevant canonical experiences, projects, skills, technologies, and other information regardless of which existing role-specific resume currently contains them.

---

# 1. Why This Change Is Needed

The existing four resumes are intentionally role-specific and therefore incomplete relative to one another.

For example:

```text
Full Stack Resume
    └── does not currently contain some AI projects

AI Project
    └── exists in another resume
```

A Full Stack + AI Job Description should still be able to reuse that AI project.

The system should not be constrained by which role-specific resume happened to contain the project.

Instead:

```text
Knowledge Base
    ├── all canonical experiences
    ├── all canonical projects
    ├── all canonical skills
    ├── all canonical technologies
    ├── all canonical domains
    └── other canonical career information

                  ↓

              Job Description

                  ↓

       Select relevant canonical data

                  ↓

       Reuse / Recombine / Generate

                  ↓

            Tailored Resume
```

---

# 2. Terminology

Use the term:

```text
Knowledge Base
```

Do **not** call it:

```text
Canonical Knowledge Base
Data Lake
```

The Knowledge Base contains canonical information, but the project's user-facing terminology should simply be **Knowledge Base**.

---

# 3. New Source-of-Truth Model

The architecture should become:

```
                    Knowledge Base
                           │
                           ▼
                     JD Analyzer
                           │
                           ▼
                     Data Retrieval
                           │
                           ▼
                     Resume Planner
                           │
                           ▼
                    Resume Generator
```

The four existing resumes remain useful, but they are no longer authoritative.

---

# 4. Knowledge Base Contents

At minimum, the Knowledge Base should support the canonical forms of the existing resume entities:

```text
Experiences
Projects
Skills
Education
```

It should preserve the existing structured information associated with those entities, such as:

```text
Experience
- company
- title
- employment_type
- duration
- location
- technologies
- domains
- highlights

Project
- name
- description
- technologies
- domains
- highlights

Skills
- categories
- individual skills
```

Follow the project's current domain models wherever possible.

Do not create a second incompatible schema merely for the Knowledge Base.

---

# 5. Knowledge Base Is Canonical

Everything inside the Knowledge Base is assumed to be canonical and human-verified.

The Knowledge Base may contain information that is absent from every individual role-specific resume.

That is intentional.

For example:

```text
Knowledge Base
├── Project A
├── Project B
├── Project C
├── Experience A
├── Experience B
├── Skill X
├── Skill Y
└── ...
```

A role-specific resume may contain only a subset:

```text
Full Stack Resume
├── Project A
├── Experience A
└── Skill X
```

That does **not** make Project B or Project C less canonical.

---

# 6. Generated Data Must Never Enter the Knowledge Base

This is a hard architectural boundary.

Generated content may be used only within the current tailoring run.

For example:

```text
Knowledge Base
      │
      ▼
Tailoring Pipeline
      │
      ▼
Generated Resume
```

Allowed:

```text
Knowledge Base → Resume
```

Forbidden:

```text
Generated Resume → Knowledge Base
```

The system must never automatically persist:

```text
GENERATED
```

entities into the Knowledge Base.

This includes generated:

```text
projects
skills
technologies
achievements
metrics
experiences
```

and any other generated claims.

Existing `EntitySource` / lineage mechanisms must remain compatible with this rule.

---

# 7. Generated vs Canonical

The existing distinction between:

```text
EntitySource.CANONICAL
EntitySource.GENERATED
```

should continue to exist.

However, the meaning becomes clearer:

```text
Knowledge Base entities
    → CANONICAL

Tailoring-run generated entities
    → GENERATED
```

The LLM must never decide the source value.

The application must assign the appropriate lineage/source metadata.

---

# 8. Existing Four Resumes

Do not delete the four existing resumes.

They should continue to exist and remain useful as curated role-specific views.

For example:

```text
backend.md
fullstack.md
cybersecurity.md
...
```

However, their role changes:

### Previously

```text
Resume = source of truth
```

### Now

```text
Resume = curated view of Knowledge Base
```

Their content can remain manually maintained.

The migration does **not** require automatically rewriting all four resumes into Knowledge Base references during this task unless that is necessary for implementation.

Avoid unnecessary migration complexity.

---

# 9. Knowledge Base Storage

Introduce a clear persistent representation for the Knowledge Base.

Choose the storage format that best fits the existing project architecture and is easy for the user to manually maintain.

The format should:

- be human-editable
- preserve structured entities
- support multiple experiences/projects/skills
- preserve ordering where meaningful
- be straightforward to parse
- integrate naturally with the existing Pydantic models

Do not introduce a database unless the existing architecture genuinely requires one.

A structured Markdown/YAML/TOML/JSON representation is preferable to introducing infrastructure unnecessarily.

The final storage format is an implementation decision for the agent, but it must preserve the architectural rules above.

---

# 10. Parser Changes

The existing Parser currently understands canonical resume files.

Extend or adapt parsing so the Knowledge Base can be loaded into the existing domain models.

Prefer:

```text
Knowledge Base Parser
        ↓
Resume/domain objects
```

rather than creating an entirely separate object hierarchy.

However, do not force the Knowledge Base into the existing `Resume` abstraction if doing so makes the model semantically incorrect.

If the Knowledge Base naturally requires a container such as:

```python
KnowledgeBase(
    experiences=[...],
    projects=[...],
    skill_categories=[...],
    education=[...],
)
```

introduce it cleanly.

The exact model should follow the existing project conventions.

---

# 11. Knowledge Base IDs

Canonical entities should have stable identifiers suitable for retrieval and lineage.

Do not rely on array position alone.

For example:

```text
exp_001
exp_002

proj_001
proj_002
proj_003

skill_001
skill_002
```

IDs may be stored persistently in the Knowledge Base if that fits the design.

Unlike the existing per-parse runtime IDs, Knowledge Base IDs should be stable across runs.

Do not make IDs dependent on the order in which a parser happens to discover entities.

---

# 12. Data Retrieval

Introduce a dedicated retrieval step between JD understanding and planning.

Conceptually:

```text
JD Analyzer
    ↓
JobAnalysis
    ↓
Knowledge Base Retrieval
    ↓
Relevant canonical evidence
    ↓
Resume Planner
```

The Retriever's responsibility is:

> Find canonical Knowledge Base entities relevant to the current Job Description.

It should not:

- generate content
- rewrite resume content
- make final resume decisions
- render anything
- compile PDFs

It only retrieves relevant canonical information.

---

# 13. Retrieval Strategy

The Retriever should use the structured information already extracted by the JD Analyzer.

Relevant signals may include:

```text
required skills
preferred skills
technologies
domains
responsibilities
keywords
target role
```

Use the existing `JobAnalysis` model.

The Retriever should consider semantic relevance rather than requiring exact string matches.

For example:

```text
JD:
FastAPI + AI + REST APIs + PostgreSQL
```

should be able to retrieve:

```text
Project:
AI document processing platform
Technologies:
Python, FastAPI, LLM, PostgreSQL
```

even when the current Full Stack resume does not contain that project.

---

# 14. Retrieval Output

Introduce a structured retrieval result.

For example:

```python
KnowledgeBaseRetrieval(
    experiences=[...],
    projects=[...],
    skills=[...],
    supporting_evidence=[...],
)
```

The exact model is up to the agent.

The important requirement is that the Planner receives structured canonical candidates rather than searching files itself.

---

# 15. Planner Responsibility

The existing Resume Planner should now consider:

```text
JobAnalysis
+
Retrieved Knowledge Base data
+
Mode
```

rather than relying only on a selected role-specific resume.

The Planner should determine what should happen:

```text
KEEP
REWRITE
REUSE
RECOMBINE
GENERATE
REMOVE
```

Use the project's existing action model where possible.

Do not unnecessarily introduce duplicate action concepts if an existing abstraction can represent the same behavior cleanly.

---

# 16. Three Content Strategies

The Planner/Generator architecture should support three conceptual strategies.

## REUSE

Use an existing canonical entity because it already strongly matches the JD.

Example:

```text
Canonical Project
    ↓
JD match
    ↓
Reuse project
```

---

## RECOMBINE

Construct a tailored presentation from multiple canonical facts/entities.

Example:

```text
Experience A
+
Project B
+
Technology C
        ↓
Relevant tailored bullet/presentation
```

The resulting content can be newly written, but its factual basis remains canonical.

This is preferred over unnecessary invention.

---

## GENERATE

Create new content when canonical information is insufficient.

This remains allowed only according to the existing tailoring mode.

Strict mode should continue following its current no-fabrication guarantees.

Aggressive mode may generate new projects, skills, technologies, achievements, etc., according to the existing architecture.

Generated content remains confined to the current run.

---

# 17. Important Example

Suppose the Knowledge Base contains:

```text
Project A
AI Document Processing Platform
Technologies:
Python, FastAPI, LLM, PostgreSQL

Project B
Security Automation Platform
Technologies:
Python, APIs, Docker
```

The current Full Stack resume may contain only Project B.

A JD requests:

```text
Full Stack + AI
Python
FastAPI
REST APIs
PostgreSQL
LLM
```

The system should be able to do:

```text
JD
 ↓
Retriever
 ↓
Project A selected
 ↓
Planner
 ↓
Reuse / Recombine
 ↓
Generator
 ↓
Full-stack-oriented presentation of Project A
```

The system must not conclude that Project A is unavailable merely because it wasn't present in the Full Stack resume.

---

# 18. Strict Mode

Strict mode should use canonical Knowledge Base information as its factual foundation.

It may:

```text
reuse canonical data
rephrase canonical data
recombine canonical data
tailor emphasis
```

It must not fabricate unsupported claims according to the existing Strict-mode rules.

The Knowledge Base provides the factual universe available to Strict mode.

---

# 19. Aggressive Mode

Aggressive mode should follow the existing architecture's current behavior.

It may:

```text
reuse canonical data
recombine canonical data
generate new projects
generate new skills
generate new technologies
generate other allowed content
```

However:

> Anything generated during an Aggressive run remains GENERATED and must never be persisted into the Knowledge Base automatically.

---

# 20. Validation Changes

The Validator must continue to validate the generated Resume against the original factual source used for the run.

This task requires updating that concept carefully.

The source of canonical data is now the Knowledge Base rather than one selected role-specific resume.

The Validator should therefore validate against the appropriate canonical Knowledge Base representation where existing validation rules require source comparison.

Do not weaken existing validation guarantees.

Do not silently treat generated content as canonical.

Do not modify the Validator merely to make generated content pass.

Preserve the distinction between:

```text
canonical evidence
generated content
```

If the current Validator API needs to evolve from:

```python
validator.validate(
    source_resume=source_resume,
    generated_resume=generated_resume,
)
```

design the smallest clean change that supports the new architecture.

---

# 21. CLI Changes

The CLI should no longer fundamentally depend on:

```text
"Select one of the four resumes as the source"
```

The Knowledge Base becomes the source used by the tailoring pipeline.

The existing role-specific resumes can remain selectable for other purposes if useful, but they must not constrain the canonical data available to tailoring.

The new conceptual workflow is:

```text
resume-tailor tailor
        ↓
Load Knowledge Base
        ↓
Provide JD
        ↓
Analyze
        ↓
Retrieve relevant canonical data
        ↓
Plan
        ↓
Generate
        ↓
Validate
        ↓
Render
        ↓
Compile
        ↓
Quality Gate
        ↓
Revision
        ↓
Report
```

Do not force the user to manually decide which projects or experiences should be used.

The system should make that decision automatically.

---

# 22. Existing Pipeline Changes

The current pipeline:

```text
Source Resume
→ JD Analyzer
→ Resume Planner
→ Resume Generator
```

should evolve conceptually into:

```text
Knowledge Base
      ↓
JD Analyzer
      ↓
Knowledge Base Retrieval
      ↓
Resume Planner
      ↓
Resume Generator
```

The remainder stays:

```text
Resume Generator
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
Revision Engine
      ↓
Reporter
```

Do not redesign already-completed components unless the new architecture requires a concrete interface change.

---

# 23. Source Resume Selection

Do not remove the existing role-specific resumes unnecessarily.

Instead, separate these concepts:

```text
Knowledge Base
= canonical source

Role-specific resume
= curated view / optional starting configuration
```

The pipeline should no longer assume that a selected role-specific resume defines everything that can be used.

The agent should determine the cleanest backward-compatible CLI behavior.

---

# 24. Reporter

Update Reporter so reports can distinguish between:

```text
Knowledge Base canonical data used
Generated data created during this run
Role-specific view data, if applicable
```

Do not make Reporter responsible for retrieval or generation.

Use the structured retrieval result, planner actions and revision trail.

Changes should clearly indicate when a canonical Knowledge Base entity was used.

---

# 25. Revision Engine

The Revision Engine continues operating on the generated `Resume`.

It should not access or mutate the Knowledge Base directly.

No revision result should be written back into the Knowledge Base.

The existing deterministic deletion and compression behavior remains unchanged unless a small integration adaptation is required.

---

# 26. Immutability Rules

The following are immutable during a tailoring run:

```text
Knowledge Base
Role-specific resume views
LaTeX templates
```

Generated and revised Resume objects remain separate runtime objects.

The pipeline must never modify canonical files as a side effect of tailoring.

---

# 27. Migration Requirements

Do not attempt a massive rewrite.

First establish the Knowledge Base structure and prove that the existing canonical data can be represented correctly.

Then migrate the pipeline incrementally.

The migration must preserve existing working functionality wherever possible.

Do not delete the existing role-specific resumes.

Do not lose any canonical information during migration.

A human should be able to inspect the Knowledge Base and understand exactly what information is considered canonical.

---

# 28. Tests

Add tests for:

### Knowledge Base parsing

Verify:

```text
experiences
projects
skills
education
IDs
source lineage
```

are parsed correctly.

### Stable IDs

Verify that Knowledge Base entity IDs remain stable across repeated loads.

### Retrieval

Verify that a JD can retrieve relevant entities even when those entities are absent from a particular role-specific resume.

### Cross-role retrieval

Specifically test the motivating case:

```text
AI project absent from Full Stack resume
        ↓
Full Stack + AI JD
        ↓
AI project retrieved from Knowledge Base
```

### Strict mode

Verify that canonical reuse/recombination works without unsupported fabrication.

### Aggressive mode

Verify that generated entities are possible when required.

### Generated isolation

Verify that:

```text
generated entity
    ≠
Knowledge Base entity
```

and nothing generated is persisted to the Knowledge Base.

### Planner

Verify that Planner receives and correctly uses retrieval results.

### Full pipeline

Verify:

```text
Knowledge Base
→ Analyzer
→ Retrieval
→ Planner
→ Generator
→ Validator
→ Renderer
→ Compiler
→ Quality Gate
→ Revision
→ Reporter
```

### Regression

Run the existing test suite and ensure previously working behavior remains functional.

---

# 29. Real-World Smoke Test

Perform at least one real run using a JD where a highly relevant project or skill exists in the Knowledge Base but is absent from the corresponding role-specific resume.

The expected behavior is:

```text
JD
 ↓
Knowledge Base Retrieval
 ↓
Relevant omitted project discovered
 ↓
Planner selects it
 ↓
Generator appropriately tailors it
 ↓
Final PDF contains the relevant project/content
```

Verify that the selected canonical project is correctly represented and that the Knowledge Base remains unchanged after the run.

---

# 30. Architectural Constraints

This is an architectural evolution, not permission to rewrite the whole project.

Do not:

- delete the existing four resumes
- treat generated output as canonical
- persist generated entities into the Knowledge Base
- let the LLM directly mutate the Knowledge Base
- allow the Planner to read arbitrary files
- let the Generator retrieve arbitrary files
- make the Retriever generate content
- make the Retriever rewrite content
- make the Knowledge Base depend on rendered LaTeX
- introduce a database without a strong reason
- duplicate the existing Resume/domain models unnecessarily
- weaken validation
- change the Revision Engine's existing responsibilities
- change the Quality Gate's responsibilities

The Knowledge Base should be a **read-only input during tailoring**.

---

# Definition of Done

Task 020 is complete when:

- A persistent Knowledge Base exists.
- The Knowledge Base contains the canonical career information.
- The four existing role-specific resumes remain intact.
- The four resumes are no longer the authoritative source for tailoring data.
- Knowledge Base entities have stable IDs.
- Knowledge Base entities are treated as canonical.
- Generated entities remain run-local and are never written into the Knowledge Base.
- A dedicated retrieval step exists.
- Retrieval uses `JobAnalysis`.
- Planner receives retrieved canonical candidates.
- Planner/Generator can reuse canonical content missing from a role-specific resume.
- Reuse, recombination and generation are supported coherently.
- Strict and Aggressive modes continue respecting their existing rules.
- Validator is correctly adapted to the new source-of-truth architecture without weakening guarantees.
- Reporter reflects Knowledge Base usage and generated content appropriately.
- Existing Revision Engine behavior remains intact.
- CLI no longer constrains tailoring to one role-specific resume's contents.
- The cross-role AI-project smoke test succeeds.
- The complete existing test suite passes.
- The Knowledge Base remains unchanged after a tailoring run.

---

## Agent Report

After implementation, report:

```text
Files changed:
...

Knowledge Base format:
...

Knowledge Base entities:
...

Retrieval implementation:
...

Planner/Generator changes:
...

Validator changes:
...

CLI changes:
...

Reporter changes:
...

Tests added:
...

Tests executed:
...

Cross-role smoke test:
PASS / FAIL

Generated data persisted to Knowledge Base:
MUST BE: NO

Architectural deviations:
...
```

Do not declare the task complete until the cross-role retrieval smoke test has been executed and the Knowledge Base has been verified to remain unchanged.
