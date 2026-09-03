# Task 017 — Revision / Shortening Engine

## Objective

Implement the Revision / Shortening Engine.

The Revision Engine is responsible for reducing a generated resume that fails the Quality Gate until it satisfies the required quality constraints.

The engine should prefer deterministic deletion first.

If deterministic deletion cannot satisfy the one-page constraint because of a remaining shortfall, the engine may perform a **single consolidated LLM compression pass** to shorten selected two-line bullets to one line.

The Revision Engine must never use the LLM to decide what content should be removed.

---

# Pipeline Position

```text
Generated Resume
       ↓
Quality Gate
       │
       ├── PASS → Done
       │
       └── FAIL
              ↓
      Revision / Shortening Engine
              ↓
      Deterministic Deletion
              ↓
      Render → Compile → Quality Gate
              ↓
       Still failing?
          /       \
        No         Yes
        ↓           ↓
      Done      Calculate Shortfall
                    ↓
             Select Bullets
                    ↓
             ONE LLM Call
                    ↓
             Verify Protected Facts
                    ↓
             Apply Compression
                    ↓
             Render → Compile
                    ↓
              Quality Gate
```

---

# Core Principle

The Revision Engine owns the complete shortening policy.

This includes:

- deletion ordering
- bullet removal
- project removal
- skill removal
- experience bullet removal
- retention floors
- shortfall calculation
- selection of bullets for LLM compression
- protected-fact extraction
- LLM compression request construction
- protected-fact verification
- applying compressed bullets
- re-rendering
- recompiling
- re-running the Quality Gate
- stopping once the resume passes

No other component should perform deterministic content deletion.

---

# Inputs

The Revision Engine receives:

```python
source_resume: Resume
current_resume: Resume
quality_result: QualityGateResult
```

The `source_resume` is the resume that was provided at the beginning of the tailoring process.

The `current_resume` is the latest generated/revised resume.

The `quality_result` describes why the current resume failed.

The Revision Engine must not load resumes or quality results from disk itself unless explicitly provided by the application pipeline.

---

# Output

The Revision Engine must return the **changed Resume**.

If the current resume already passes the Quality Gate, return it unchanged.

If the current resume fails:

1. Attempt deterministic deletion.
2. Re-render.
3. Recompile.
4. Re-run the Quality Gate.
5. If a shortfall remains and eligible two-line bullets exist, perform an LLM compression pass.
6. Verify protected facts in every compressed bullet.
7. Apply only valid compressions.
8. Re-render.
9. Recompile.
10. Re-run the Quality Gate.
11. Continue according to this specification if further shortening is required.

If no valid result can be produced under the defined rules, raise an explicit `RevisionError`.

The engine must never return the original failing resume as a successful result.

---

# LLM Usage

The Revision Engine is primarily deterministic.

The LLM is permitted **only for bullet compression when deterministic deletion cannot satisfy the one-page requirement because of a shortfall**.

The LLM must NOT:

- decide what to delete
- decide which bullets are important
- decide priority
- choose which bullets to modify
- add new content
- remove facts
- fabricate metrics
- fabricate technologies
- rewrite unrelated bullets
- rewrite the summary
- rewrite education
- rewrite contact information

The application determines exactly which bullets are sent to the LLM.

---

# Deterministic Deletion First

The engine must always exhaust the legal deterministic deletion strategy before invoking the LLM compression path.

```text
Quality Gate FAIL
      ↓
Deterministic deletion
      ↓
Render
      ↓
Compile
      ↓
Quality Gate
      ↓
PASS?
```

If PASS:

```text
STOP
```

Only if the resume still fails should the engine evaluate whether a shortfall exists and whether LLM compression is applicable.

---

# Removal Order

The global removal order is:

```text
Projects
    ↓
Skills
    ↓
Experience
```

This order is authoritative.

---

# Summary

The Summary is never a deterministic trim target.

The Revision Engine must never remove words or sentences from the Summary.

Summary length is handled during generation.

The Summary is also excluded from the LLM compression pass.

---

# Bullet Length

Individual bullet rewriting is not part of deterministic deletion.

Bullet length optimization is handled during generation.

The Revision Engine may remove entire bullets, but it must never rewrite or shorten remaining bullet text during the deterministic deletion phase.

When a shortfall remains, the LLM compression phase may shorten only the explicitly selected bullets.

---

# Projects

Projects are fully mutable.

The Revision Engine may remove:

- project bullets
- entire projects

Projects must be shortened bullet-by-bullet before the entire project is removed.

---

## Project Bullet Removal

Within each project, bullets are already ordered from:

```text
Highest importance
        ↓
        ...
        ↓
Lowest importance
```

Always remove the lowest-priority remaining bullet first.

Example:

```text
Project A

Bullet 1  ← highest priority
Bullet 2
Bullet 3
Bullet 4  ← remove first
```

---

## Project Removal Floor

Projects should be reduced bullet-by-bullet while preserving the project until it reaches the project floor.

The project floor is:

```text
2 bullets
```

If a project has:

```text
4 bullets
```

and needs trimming:

```text
4
↓
3
↓
2
```

If another deterministic project reduction is required when the project has:

```text
2 bullets
```

remove the entire project.

Do not leave a project with fewer than 2 bullets.

---

# Minimum Projects

The final resume must contain at least:

```text
2 projects
```

The Revision Engine must never reduce the resume below two projects.

Canonical and generated projects may both be removed when permitted by the ordering rules.

---

# Skills

Skills are the second global removal target.

The final resume must contain at least:

```text
5 individual skills
```

This means five actual skills, not five categories.

---

## Skill Removal

When skills must be removed:

- remove the lowest-priority skills first
- preserve at least 5 total skills
- remove empty/unneeded skill categories when appropriate
- never leave invalid empty categories

Do not alphabetize or reorder categories during trimming.

---

# Work Experience

Work Experience is the final deterministic deletion target.

The resume must always contain exactly:

```text
2 work experiences
```

Experiences themselves must never be removed.

Experiences must never be reordered.

Only experience highlights may be removed or compressed.

---

# Experience Bullet Removal Order

Deterministic removal order:

```text
Internship bullets
        ↓
Full-time bullets
```

Within an experience:

```text
Highest priority
        ↓
        ...
        ↓
Lowest priority
```

Remove the lowest-priority bullet first.

---

# Experience Retention Floors

## Internship

Minimum:

```text
3 bullets
```

## Full-Time Experience

Minimum:

```text
5 bullets
```

Never remove below these floors.

An internship is assumed to exist.

No fallback logic for a missing internship is required.

---

# Retention Floors Summary

| Unit                         |   Minimum |
| ---------------------------- | --------: |
| Projects                     |         2 |
| Individual skills            |         5 |
| Internship bullets           |         3 |
| Full-time experience bullets |         5 |
| Work experiences             | exactly 2 |

Additionally:

- Summary is never trimmed.
- Contact is immutable.
- Education is immutable.
- Work experience company/title/employment/duration/location are immutable.

These are hard constraints.

---

# Shortfall

If deterministic deletion cannot produce a one-page resume without violating the retention floors, calculate the remaining shortfall.

Conceptually:

```text
spill
=
amount of rendered overflow

freeable
=
amount of additional rendered space that deterministic
deletion could safely create without violating floors

shortfall
=
spill - freeable
```

A positive shortfall means deterministic deletion alone cannot satisfy the one-page requirement under the current retention rules.

Example:

```text
spill     = 13 lines
freeable  =  9 lines

shortfall =  4 lines
```

The engine must not violate retention floors to eliminate the shortfall.

---

# LLM Compression Path

When:

```text
shortfall > 0
```

the engine should attempt to recover the required space by compressing suitable two-line bullets.

The purpose of compression is:

```text
Two-line bullet
      ↓
One-line bullet
```

The target is:

```text
<= 15 words
```

---

# Compression Eligibility

Only bullets that currently render as approximately two lines and are eligible for one-line compression should be considered.

Do not send every bullet to the LLM.

Do not send one-line bullets to the LLM merely to make them shorter.

The selection is deterministic.

---

# Compression Priority Order

Bullets must be considered in this order:

```text
Projects
    ↓
Skills
    ↓
Experience
        ↓
    Internship
        ↓
    Full-Time
```

Within each entity, use the existing bottom-to-top importance ordering.

The last/lowest-priority eligible bullet is considered before higher-priority bullets.

---

# Compression Selection

Calculate how many line reductions are required.

For example:

```text
shortfall = 4 lines
```

Select enough eligible two-line bullets to potentially provide approximately 4 line reductions.

Each selected bullet should represent a candidate:

```text
2 lines → 1 line
```

The application code determines the selected bullets.

The LLM does not select them.

---

# Protected Facts

Before sending selected bullets to the LLM, the application must identify the **protected facts** contained in every selected bullet.

Protected facts are pieces of information that must survive compression unchanged.

At minimum, protected facts include:

- numbers
- percentages
- counts
- durations
- measurements
- version numbers
- metrics
- technologies
- frameworks
- programming languages
- databases
- cloud services
- APIs
- protocols
- standards
- feature names
- product names
- project names
- named systems
- concrete domain-specific terms
- measurable outcomes

When uncertain whether something is a protected fact, prefer preserving it.

---

# Protected-Fact Extraction

Protected facts must be extracted programmatically before the LLM call.

Do not rely solely on the prompt to identify them.

The extraction mechanism should capture, where applicable:

## Numeric Facts

Examples:

```text
40%
500+
3x
99.9%
30 ms
2025
v2.1
```

These must be preserved exactly unless the original and compressed representations are semantically identical.

---

## Technologies

Examples:

```text
Python
Java
Redis
Spring Boot
PostgreSQL
Docker
Kubernetes
```

These must remain present in the compressed bullet if they were present in the original.

---

## Named Facts

Examples:

```text
OAuth 2.0
REST API
Model Context Protocol
Triage Studio
Threat Intelligence Platform
```

These must not be generalized into vague terms.

---

# Single LLM Call

All selected bullets must be compressed in **one LLM call**.

Do not make one LLM call per bullet.

Incorrect:

```text
Bullet 1 → LLM
Bullet 2 → LLM
Bullet 3 → LLM
Bullet 4 → LLM
```

Correct:

```text
Selected bullets
      ↓
Extract protected facts
      ↓
ONE LLM request
      ↓
Compressed bullets
```

This is important for latency and consistency.

---

# LLM Compression Contract

The LLM receives:

- selected bullet IDs
- original bullet text
- relevant surrounding context when necessary
- protected facts for each bullet
- maximum target length of 15 words
- instruction to preserve every protected fact

The LLM must return a structured response mapping each supplied bullet ID to its compressed text.

Example:

```json
{
  "compressions": [
    {
      "bullet_id": "proj_002:bullet_3",
      "text": "Built Redis caching, reducing API latency by 40%."
    },
    {
      "bullet_id": "exp_001:bullet_5",
      "text": "Debugged production issues and improved Spring Boot API reliability."
    }
  ]
}
```

Do not ask the LLM to return a complete resume.

---

# Compression Requirements

Every compressed bullet must:

- contain no more than 15 words
- preserve factual claims
- preserve all protected facts
- preserve the original meaning as much as practical
- remain grammatically valid
- remain a professional resume bullet

---

# Hard Fact Preservation Rule

The LLM must preserve protected facts every time.

A protected fact must not be:

- removed
- changed
- weakened
- generalized
- replaced
- paraphrased into something less specific

merely to satisfy the word limit.

---

# Metrics Must Never Be Fabricated or Changed

The LLM must never:

- invent a new metric
- increase an existing metric
- decrease an existing metric
- change a count
- change a percentage
- change a duration
- change a measurement

Example:

```text
Original:
Reduced response time by 40%.

Allowed:
Reduced response time by 40%.

Not allowed:
Reduced response time by 50%.
```

---

# Technology Preservation

If the original bullet contains:

```text
Redis
```

the compressed bullet must still contain:

```text
Redis
```

If it contains:

```text
Spring Boot
```

the compressed bullet must still contain:

```text
Spring Boot
```

Do not replace specific technology names with generic language.

---

# Named Feature / Product Preservation

If the original bullet contains a concrete named feature or product:

```text
OAuth 2.0
Triage Studio
Model Context Protocol
```

the compressed version must retain that concrete name.

Do not convert it into:

```text
authentication
platform
protocol
```

---

# Application-Level Protected-Fact Verification

The application must verify the LLM output before applying it.

For every selected bullet:

```text
Original Bullet
      ↓
Protected Fact Extraction
      ↓
LLM Compression
      ↓
Protected Fact Verification
      ↓
Accept / Reject
```

The verification must check that every protected fact from the original bullet is present and unchanged in the compressed result.

At minimum, verify:

- numeric values
- metrics
- technologies
- named features/products
- other extracted protected facts

The LLM response must never be trusted solely because it followed the prompt.

---

# Compression Rejection

If a compressed bullet fails protected-fact verification:

```text
reject the compression
```

Do not apply it to the Resume.

Do not silently accept it.

The engine may:

- retain the original bullet
- attempt another valid revision strategy
- raise `RevisionError` if no valid path remains

The fallback must never violate retention floors or mutate protected facts.

---

# Word Count Verification

After receiving each compressed bullet:

```text
word_count <= 15
```

must be verified by application code.

Do not trust the LLM's claim about word count.

If the compressed bullet exceeds 15 words:

```text
reject compression
```

---

# Compression Scope

Only the selected bullets may change.

The LLM must not modify:

- unselected bullets
- project names
- skills
- experience metadata
- contact
- education
- summary

unless those items are explicitly included in a future separately defined revision operation.

---

# Applying Compression

The application, not the LLM, applies the returned text to the Resume object.

For each returned bullet:

1. Verify the bullet ID exists.
2. Verify it was one of the selected bullets.
3. Verify protected facts are preserved.
4. Verify word count is <= 15.
5. Replace only that bullet's text.
6. Preserve its entity ID.
7. Preserve its entity source.
8. Preserve its position.

Do not allow the LLM response to create or remove entities.

---

# Post-Compression Validation

After applying the LLM compression response:

```text
Resume
   ↓
Resume Validator
```

The generated Resume must still satisfy all structural and immutable constraints.

If the response is invalid or cannot be safely applied:

```text
RevisionError
```

Do not silently accept malformed output.

---

# Re-render After Compression

After applying compressed bullets:

```text
Modified Resume
      ↓
LaTeX Renderer
      ↓
PDF Compiler
      ↓
Quality Gate
```

Never edit the `.tex` file directly.

---

# After Compression

If the Quality Gate passes:

```text
STOP
```

If the Quality Gate still fails:

1. Recalculate the actual spill/shortfall.
2. Continue with any remaining legal deterministic deletion.
3. If another compression pass is required and eligible bullets remain, select the next set of eligible bullets.
4. Extract protected facts again.
5. Make another **single consolidated LLM call**.
6. Verify all protected facts again.
7. Re-render.
8. Recompile.
9. Re-run the Quality Gate.

Each compression step must use one consolidated LLM call.

---

# Entity Lineage

Existing entities must retain their IDs.

For example:

```text
proj_001
```

remains:

```text
proj_001
```

after bullet deletion or compression.

Generated entities must retain:

```python
source = EntitySource.GENERATED
```

until the entity is removed.

When an entity is removed, its ID and source disappear with it.

---

# No Direct LaTeX Editing

The Revision Engine must never modify:

```text
resume.tex
```

directly.

Always:

```text
Resume object
    ↓
Renderer
    ↓
LaTeX
```

This preserves structure and lineage.

---

# Artifact Management

The Revision Engine owns attempt numbering.

Recommended structure:

```text
output/
└── runs/
    └── <run-name>/

        attempt_1/
            resume.tex
            resume.pdf
            report.json

        attempt_2/
            resume.tex
            resume.pdf
            report.json

        final/
            resume.tex
            resume.pdf

        revision_trail.json
```

The implementation may use the project's existing artifact conventions.

Do not persist every internal compiler iteration if the existing architecture does not require it.

---

# Revision Trail

Maintain a structured trail of actions.

For deterministic deletion:

```json
{
  "attempt": 2,
  "action": "REMOVE_BULLET",
  "entity_id": "proj_002",
  "reason": "PAGE_OVERFLOW"
}
```

For project removal:

```json
{
  "attempt": 4,
  "action": "REMOVE_PROJECT",
  "entity_id": "proj_003",
  "reason": "PROJECT_REACHED_BULLET_FLOOR"
}
```

For LLM compression:

```json
{
  "attempt": 5,
  "action": "COMPRESS_BULLETS",
  "bullet_ids": ["proj_002:bullet_3", "exp_001:bullet_5"],
  "shortfall_before": 2
}
```

The exact schema may follow existing project conventions.

---

# Orphan Words

Orphan-word findings are warnings.

They do not block acceptance.

Do not continue trimming solely because orphan-word warnings exist if all blocking Quality Gate checks have passed.

---

# Determinism

The deterministic portion of the Revision Engine must be deterministic.

Given the same:

- source resume
- current resume
- quality result
- configuration

the same deterministic removal decisions must be made.

The LLM compression step is the only intentionally non-deterministic part of the revision process.

Protected-fact extraction and verification must be deterministic.

---

# No Source Mutation

The source resume must never be modified.

Operate on a copy of the generated/current Resume.

---

# Testing

## Deterministic Deletion

Test:

- project bullet removal
- project floor behavior
- entire project removal
- minimum two projects
- skill removal
- minimum five individual skills
- internship-first experience trimming
- full-time experience trimming
- experience floors
- exact two experiences
- summary preservation
- education preservation
- contact preservation

---

## Shortfall Calculation

Test:

```text
spill = 0
spill > 0
spill == freeable
spill > freeable
```

Verify:

```text
shortfall = spill - freeable
```

where applicable.

---

## Compression Selection

Test that:

- only eligible two-line bullets are selected
- one-line bullets are not selected
- selection follows Projects → Skills → Experience
- Experience follows Internship → Full-Time
- lower-priority bullets are selected before higher-priority bullets
- enough bullets are selected to address the calculated shortfall

---

## Single LLM Call

Mock the provider.

Verify that multiple selected bullets result in:

```text
exactly one provider.generate() call
```

rather than one call per bullet.

---

## Protected-Fact Extraction

Test extraction of:

### Numbers

```text
40%
500+
3x
99.9%
30 ms
v2.1
```

### Technologies

```text
Python
Redis
Spring Boot
PostgreSQL
Docker
```

### Named Facts

```text
OAuth 2.0
Triage Studio
Model Context Protocol
```

Verify these are extracted from the original bullet.

---

## Protected-Fact Verification

Test that:

- all protected facts survive unchanged
- missing metrics are rejected
- changed metrics are rejected
- missing technologies are rejected
- missing named features are rejected
- generalized technologies are rejected
- fabricated metrics are rejected

Examples:

```text
40% → 40%
```

valid.

```text
40% → 50%
```

invalid.

```text
Redis → Redis
```

valid.

```text
Redis → caching
```

invalid.

---

## Compression Output

Test:

- valid compressed response
- missing bullet ID
- unknown bullet ID
- duplicate bullet ID
- > 15-word response
- missing protected fact
- altered protected fact
- fabricated metric
- malformed JSON

Invalid responses must fail safely.

---

## Post-Compression

Verify that:

- only selected bullets change
- IDs are preserved
- source values are preserved
- bullet order is preserved
- immutable fields remain unchanged
- Resume Validator still passes

---

## Convergence

Test:

```text
deterministic deletion
→ compression
→ Quality Gate pass
```

Verify that the engine stops immediately once the Quality Gate passes.

---

## Infeasibility

Test a case where:

```text
all legal deterministic deletion is exhausted
```

and:

```text
no eligible compression candidates remain
```

The engine must raise:

```text
RevisionError
```

rather than violating retention floors.

---

# Out of Scope

Do NOT implement:

- JD analysis
- Resume planning
- resume generation
- summary rewriting
- education modification
- contact modification
- LaTeX editing
- layout squeezing
- margin changes
- font-size changes
- negative spacing hacks
- manual `.tex` editing
- Quality Gate implementation
- PDF compiler implementation
- ATS scoring

The Revision Engine may call the Renderer, PDF Compiler, Quality Gate, and LLM Provider, but must not implement their responsibilities.

---

# Definition of Done

The task is complete when:

- `RevisionEngine` is implemented.
- Deterministic deletion is always attempted first.
- Projects are trimmed before Skills.
- Skills are trimmed before Experience.
- Experience follows Internship → Full-Time.
- Project bullets are removed from the bottom first.
- Projects are removed entirely when they reach the 2-bullet floor and another reduction is required.
- At least 2 projects remain.
- At least 5 individual skills remain.
- Internship remains at or above 3 bullets.
- Full-time experience remains at or above 5 bullets.
- Exactly 2 work experiences remain.
- Summary is never trimmed.
- Education is never modified.
- Contact is never modified.
- Immutable experience fields are preserved.
- The engine works on Resume objects rather than `.tex` files.
- The engine uses the Quality Gate after modifications.
- Shortfall is calculated when deterministic deletion is insufficient.
- Eligible two-line bullets are selected deterministically.
- Selection follows Projects → Skills → Experience → Internship → Full-Time.
- Selected bullets are compressed through a single consolidated LLM call per compression step.
- Compressed bullets are limited to 15 words.
- Protected facts are extracted programmatically before compression.
- Numbers and metrics are always preserved exactly.
- Technologies are always preserved.
- Feature/product names and other protected concrete facts are always preserved.
- Protected facts are verified programmatically after compression.
- The LLM cannot decide which bullets to compress.
- The LLM cannot modify unselected content.
- Invalid LLM output is rejected.
- Entity IDs and source lineage are preserved.
- Revision attempts are tracked.
- Revision trail is persisted.
- The engine stops immediately after the Quality Gate passes.
- Retention floors are never silently violated.
- An explicit `RevisionError` is raised when the one-page target is infeasible under the defined rules.
- Unit and integration tests pass.
