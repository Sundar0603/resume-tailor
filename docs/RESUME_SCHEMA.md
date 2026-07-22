# Resume Schema

**Version:** 1.0  
**Status:** Stable  
**Last Updated:** 2026-07-22

---

# Purpose

This document defines the canonical structure for every master resume used by Resume Tailor.

The goal of this schema is to represent resume content as structured data rather than presentation. Every master resume must conform to this schema regardless of the target role (Backend, Full Stack, Cybersecurity, etc.).

The parser assumes all resumes follow this specification.

---

# Design Principles

The resume schema is designed around the following principles.

- Markdown is the single source of truth.
- Structure is more important than formatting.
- Every resume follows exactly the same layout.
- The parser should never infer meaning from formatting.
- Resume content should be human-editable.
- The schema should be easily convertible to JSON.
- Presentation belongs to LaTeX templates, not the resume itself.

---

# Metadata

Every resume begins with YAML Front Matter.

## Required Fields

| Field | Description |
|--------|-------------|
| resume | Resume type (`backend`, `fullstack`, `cybersecurity`) |
| template | LaTeX template used during rendering |
| version | Resume schema version |

Example

```yaml
---
resume: cybersecurity
template: cybersecurity
version: 1.0
---
```

---

# Contact

Stores personal information.

## Required Fields

| Field | Required |
|--------|----------|
| Name | Yes |
| Phone | Yes |
| Email | Yes |
| LinkedIn | Yes |
| GitHub | Yes |

Example

```markdown
# Contact

Name: Sundar S

Phone: +91 7397398343

Email: sundarselvam3@gmail.com

LinkedIn: https://linkedin.com/in/...

GitHub: https://github.com/...
```

---

# Summary

A short professional summary.

## Rules

- Single paragraph.
- Plain text only.
- No bullet points.
- No Markdown formatting.

Example

```markdown
# Summary

Cybersecurity Engineer specializing in cybersecurity platforms, threat intelligence, security automation, SOC platforms, and AI-powered investigation workflows.
```

---

# Skills

Skills are grouped by category.

## Rules

- Every category is a second-level heading.
- Every skill is stored as a separate list item.
- Never store comma-separated skills.

Example

```markdown
# Skills

## Security

- SOC Tooling
- Threat Intelligence
- Detection Engineering
- Zero Trust

## AI and Automation

- OpenAI APIs
- MCP
- LLM Tool Orchestration

## Programming Languages

- Java
- Python
- JavaScript

## Backend

- Spring Boot
- REST APIs
- Redis

## Frontend

- Vue
- HTML
- CSS

## Tools

- Git
- Docker
- Linux
- MySQL
```

---

# Work Experience

Contains one or more experience records.

Each experience record follows the same structure.

## Required Fields

| Field | Required |
|--------|----------|
| Company | Yes |
| Role | Yes |
| Employment Type | Yes |
| Duration | Yes |
| Location | No |
| Technologies | No |
| Domains | No |
| Highlights | Yes |

Example

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
- Redis

Domains:

- Threat Intelligence
- Firewall Security
- Malware Analysis

Highlights:

- Built threat intelligence ingestion pipelines integrating external intelligence feeds.

- Designed and implemented Zero Trust access control workflows.

- Developed API risk scoring functionality for firewall systems.
```

Additional experiences follow the same format.

---

# Projects

Contains zero or more project records.

Each project follows the same schema.

## Required Fields

| Field | Required |
|--------|----------|
| Name | Yes |
| Type | Yes |
| Repository | No |
| Technologies | No |
| Domains | No |
| Highlights | Yes |

Example

```markdown
# Projects

## Project

Name: SOCrates

Type: Personal

Repository: https://github.com/...

Technologies:

- Python
- Vue
- OpenAI APIs
- MCP

Domains:

- SOC Automation
- Threat Intelligence

Highlights:

- Built an AI-powered SOC assistant.

- Automated IOC enrichment.

- Reduced manual investigation effort by 60%.
```

Additional projects follow the same structure.

---

# Education

Contains one or more education records.

## Required Fields

| Field | Required |
|--------|----------|
| Institution | Yes |
| Degree | Yes |
| Major | Yes |
| Duration | Yes |
| CGPA | No |
| Location | No |

Example

```markdown
# Education

## Degree

Institution: Velammal Engineering College

Degree: Bachelor of Engineering

Major: Computer Science and Engineering

Duration: 2020 - 2024

CGPA: 9.18

Location: Chennai
```

---

# Optional Sections

These sections are optional and may be added in future resumes.

- Certifications
- Publications
- Patents
- Awards
- Open Source Contributions
- Volunteer Experience
- Leadership
- Languages

Each optional section should follow the same structured philosophy as the required sections.

---

# Validation Rules

A resume is considered valid if it satisfies all of the following rules.

## Metadata

- YAML Front Matter must exist.
- `resume` must be present.
- `template` must be present.
- `version` must be present.

## Contact

- Contact section must exist.
- Name is required.
- Email is required.
- Phone is required.

## Summary

- Summary section must exist.
- Summary must contain plain text.

## Skills

- Skills section must exist.
- Every category contains a list.
- No comma-separated values.

## Work Experience

- Work Experience section must exist.
- At least one Experience record must exist.
- Every Experience record must contain:
  - Company
  - Role
  - Employment Type
  - Duration
  - Highlights

## Projects

- Project section may be empty.
- Every Project record must contain:
  - Name
  - Type
  - Highlights

## Education

- Education section must exist.
- At least one Degree record must exist.

---

# Runtime Fields

The following values are generated dynamically during resume tailoring and **must never be stored** in the master resume.

- ATS Score
- Resume Score
- Matched Skills
- Missing Skills
- Extracted Keywords
- Tailoring Notes
- Revision History
- AI Suggestions
- Quality Gate Results
- Target Job Description
- Company Analysis

These values exist only inside the in-memory `Resume` object.

---

# Canonical Directory Structure

```
content/
├── backend.md
├── fullstack.md
└── cybersecurity.md
```

Every file inside the `content/` directory must conform to this schema.

---

# Future Compatibility

This schema is intentionally presentation-independent.

Future renderers may generate:

- LaTeX
- HTML
- DOCX
- PDF
- JSON

without requiring changes to the master resumes.

---

# Versioning

Changes to this schema must increment the schema version.

Minor additions (optional fields):

- 1.0 → 1.1

Breaking changes:

- 1.x → 2.0

The parser must reject resumes using unsupported schema versions.