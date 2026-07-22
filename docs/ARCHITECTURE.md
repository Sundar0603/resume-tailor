This document is the authoritative source for all architectural decisions in Resume Tailor CLI. If implementation diverges from this document, the implementation is considered incorrect unless the architecture has been explicitly updated first.

Resume Tailor CLI v1.0

**Version:** 1.0

**Status:** Frozen

**Last Updated:** 2026-07-20

Vision

Given a master resume and a Job Description, generate a submission-ready, ATS-optimized, single-page resume using the user's existing LaTeX template in under 3 minutes (typically 1–2 minutes), while requiring zero manual editing.

## Scope

This document defines the architecture for Version 1.0.

It is intentionally focused on the MVP required to support the author's job search workflow.

Future enhancements are documented separately under the Backlog section.

Product Philosophy

This project is not an AI demo.

It is an autonomous resume optimization system.

The user should only:

Choose the resume.
Paste the Job Description.

Everything else should happen automatically.

The tool should not ask questions or require decisions during execution.

Success Criteria

A resume is considered successfully generated only if all of the following are true:

ATS optimized
Matches the selected mode
Compiles successfully
Fits exactly one page
Has no structural/layout issues
Preserves the user's LaTeX design
Produces a complete audit report

If any of these fail, the resume is not finished.

## Architectural Rule

AI agents are implementation tools.

They must never modify the architecture.

Any architectural changes must first be made in this document before implementation begins.

Core Design Principles

1. Quality First

The objective is not "offline".

The objective is

Produce the highest-quality resume within 3 minutes.

The architecture should support:

Local models
OpenAI
Anthropic
Gemini
Future providers

The best provider for the task can be configured.

2. Zero Intervention

Execution should look like

resume-tailor

or

pbpaste | resume-tailor

The tool never pauses asking

Continue?
Confirm?
Select?

Everything is configuration driven.

3. Markdown is the Source of Truth

Master resumes become

backend.md

fullstack.md

cybersecurity.md

The AI edits Markdown.

Never LaTeX.

4. LaTeX is Only a Renderer

The AI never edits

resume.tex

Instead

Markdown

↓

Renderer

↓

resume.tex

↓

pdflatex

↓

resume.pdf

This guarantees your formatting is always preserved.

5. Every Module Has One Responsibility
   Module Responsibility
   Parser Read data
   Analyzer Understand JD
   Generator Generate / revise content
   Renderer Produce LaTeX
   Compiler Produce PDF
   Quality Gate Decide if resume is acceptable
   Reporter Explain changes

No module performs two unrelated jobs.

## Core Interfaces

The project exposes the following architectural interfaces.

LLMProvider

Renderer

QualityGate

ReportGenerator

MarkdownParser

Technology Decisions
Component Technology
Python 3.12+
Package Manager uv
CLI Typer
Terminal UI Rich
Config PyYAML
Data Models Pydantic
PDF Analysis PyMuPDF
Testing pytest
Rendering LaTeX
LLM Provider Pluggable (Ollama/OpenAI/Anthropic/Gemini/etc.)
Folder Structure (This folder structure is considered part of the architecture. Implementation tasks should not modify it unless the architecture document is explicitly updated)
resume-tailor/

README.md
ARCHITECTURE.md
ROADMAP.md

pyproject.toml

config/
config.yaml

content/
backend.md
fullstack.md
cybersecurity.md

templates/
backend.tex
fullstack.tex
cybersecurity.tex

prompts/
jd_analysis.md
strict.md
aggressive.md
revision.md

generated/

output/

artifacts/

logs/

tests/

src/

    cli/

    parser/

    analyzer/

    generator/

    renderer/

    quality_gate/

    report/

    providers/

    models/

    utils/

Resume Model

Instead of treating the resume as one document, we treat it as structured sections.

Resume

├── Contact
├── Summary
├── Skills
├── Experience
├── Projects
└── Education

Each section is independent.

Section Policies

Every section has two independent properties.

1. Mutable

Can the AI modify it?

Example

Education

mutable = false
Experience

mutable = true 2. Revision Order

Only used when the resume must be shortened.

Example

Summary

revision_order = 1
Projects

revision_order = 2
Skills

revision_order = 3
Experience

revision_order = 4

Education

mutable = false

so revision order doesn't even exist.

Notice

This order is NOT used during generation.

Only during shortening.

High-Level Pipeline
Markdown Resume
│
▼
Resume Parser
│
▼
Resume Object
│
▼
JD Analyzer
│
▼
Resume Generator
│
▼
LaTeX Renderer
│
▼
pdflatex
│
▼
Quality Gate
│
Passed?
/ \
 Yes No
│ │
▼ ▼
Done Revision Generator
│
└───────────────┐
▼
LaTeX Renderer
JD Analyzer

Responsibility

Understand the Job Description.

✓ Extract keywords

✓ Extract role

✓ Extract company

Output

Company

Role

Required Skills

Preferred Skills

Responsibilities

Keywords

This module never generates text.

It only analyzes.

Out of Scope

✗ Resume generation

✗ ATS scoring

✗ PDF generation

Resume Generator

Input

Resume
JD Analysis
Mode

Output

Optimized Resume

It knows nothing about LaTeX.

Modes
🟢 Strict

Allowed

Rewrite wording
Improve grammar
Emphasize existing skills
Reorder bullets

Forbidden

New technologies
New metrics
New projects
New achievements
🔴 Aggressive

Allowed

Rewrite everything
Add JD keywords
Add technologies
Add quantified metrics
Add achievements
Rewrite summary
Rewrite bullets

No confirmations.

Everything happens automatically.

Renderer

Input

Resume Object

Output

resume.tex

Uses

backend.tex

unchanged.

Compiler

Runs

pdflatex

Produces

resume.pdf
Quality Gate

The Quality Gate is the heart of the system.

Its responsibility is simply

Decide whether the generated resume is submission-ready.

Progressive Validation
Stage 1 (Always Runs)

Fast checks.

✅ LaTeX compiles
✅ Exactly one page
✅ No overfull hboxes
✅ No orphan words
✅ No critical compile errors

If all pass

Resume accepted.

No further analysis.

Stage 2 (Only if Stage 1 Fails)

Targeted analysis.

Instead of inspecting the entire PDF,

it investigates only the problematic areas.

Example

Page 2

↓

Projects Section

↓

Overflow

or

Experience

↓

Last Line

↓

One orphan word

Produces structured feedback.

Stage 3

Revision.

The Revision Engine receives

Current Resume

-

Quality Report

and revises only the necessary sections.

Revision Loop
Generate

↓

Compile

↓

Quality Gate

↓

Pass?

↓

No

↓

Targeted Revision

↓

Compile

↓

Quality Gate

Configuration

max_revisions: 3

Meaning

Initial generation
Revision 1
Revision 2
Revision 3

Maximum

4 LLM generations

Never more.

Revision Strategy

The entire resume is never regenerated.

Only the affected sections.

Example

Projects overflow

↓

Revise only Projects

If still failing

Summary too long

↓

Revise only Summary

The rest of the resume remains untouched.

Reports

Every run produces

report.md

Example

Mode

Aggressive

Summary

Rewritten

Bullets Modified

7

Technologies Added

5

Metrics Added

3

Achievements Added

2
Diff

Every run also produces

changes.md

Example

- Developed REST APIs.

* Developed RESTful APIs using Spring Boot,
  improving API response time by 45%.
  Artifacts

Every attempt is preserved.

artifacts/

attempt_1.pdf

attempt_1.tex

attempt_1_report.json

attempt_2.pdf

...

final.pdf

Useful for debugging and prompt tuning.

CLI
resume-tailor
resume-tailor --resume backend
resume-tailor --mode aggressive
resume-tailor doctor

Later

pbpaste | resume-tailor
Phase 1 (MVP)

This is the version you'll actually use during your job hunt.

✅ Project setup (uv, Typer, Rich)
✅ Configuration system
✅ Logging
✅ doctor command
✅ Markdown resume parser
✅ JD analyzer
✅ Resume generator
✅ Strict mode
✅ Aggressive mode
✅ LaTeX renderer
✅ PDF generation
✅ Quality Gate
✅ Automatic revision loop
✅ Report generation
✅ Diff generation
Backlog

Deliberately postponed until after your job hunt:

Learning Mode
LinkedIn / Greenhouse / Lever URL import
Web UI
Cover letter generation
Resume analytics dashboard
Application history
Multi-language support
Final Engineering Philosophy

The project should follow one guiding principle:

Every expensive operation must justify its cost.

That means:

Parse once.
Analyze once.
Generate once.
Validate quickly.
Revise only if necessary.
Revise only the affected sections.
Stop as soon as the resume meets the quality gate.

This keeps the tool within the 1–3 minute target while ensuring the user never receives a resume that needs manual fixes.

## Performance Targets

Typical runtime

45–90 seconds

Maximum runtime

180 seconds

Maximum LLM generations

4

Maximum revisions

3

## Error Handling Philosophy

The application should fail fast.

If a required stage fails, subsequent stages must not execute.

Every error should produce a meaningful message and should never leave partially generated output without explanation.

## Non Goals

Version 1 intentionally does NOT support:

- Web UI

- LinkedIn import

- Cover Letter Generation

- Resume Analytics

- Learning Mode

- Multi-language support

## Related Documents

The architecture is supported by the following documents:

- `COMPONENT_SPECIFICATIONS.md` — Responsibilities, contracts, inputs, outputs, and boundaries for each major component.
- `IMPLEMENTATION_GUIDE.md` — Rules and guidelines for implementing the architecture.
- `CODING_STANDARDS.md` — Coding conventions and quality requirements.
- `ROADMAP.md` — Planned features beyond Version 1.
- `tasks/` — Incremental implementation tasks for developers and AI agents.
