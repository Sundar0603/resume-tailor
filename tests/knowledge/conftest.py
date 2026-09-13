"""
Fixtures for the Knowledge Base suite.

Factory functions returning text, following the house convention: fixtures are
Python factories rather than files, so a test can vary one field without a new
file appearing on disk for every case.
"""

import copy

import pytest

KNOWLEDGE_BASE_PATH = "knowledge/knowledge_base.md"

_MINIMAL = """---
knowledge_base: test
template: default
version: 1.0
---

# Contact

Name: Sundar S

Phone: +91 7397398343

Email: sundarselvam3@gmail.com

LinkedIn: https://www.linkedin.com/in/sundar-s-870042235/

GitHub: https://github.com/Sundar0603

---

# Summaries

## Summary

Id: sum_001

Label: backend emphasis

Backend engineer with two years at Zoho. Comfortable on both sides: building
AI systems and hardening the surfaces they run against.

---

## Summary

Id: sum_002

Cybersecurity engineer who builds AI systems for security work.

---

# Skills

## Security

Id: skill_001

- SOC Tooling
- Threat Intelligence

---

## Backend

Id: skill_002

- Spring Boot
- Redis

---

# Work Experience

## Experience

Id: exp_001

Company: Zoho Corporation

Role: Software Developer

Employment Type: Full Time

Location: Chennai

Duration: May 2024 - Present

Technologies:

- Java
- Spring Boot

Domains:

- SOC Platforms

Highlights:

- Built the MCP layer for an internal security platform, exposing REST APIs as model-invocable tools.

- Designed Redis-based caching strategies for frequently accessed firewall rules.

---

## Experience

Id: exp_002

Company: Zoho Corporation

Role: Software Developer Intern

Employment Type: Internship

Location: Chennai

Duration: Dec 2023 - Apr 2024

Technologies:

- Java

Domains:

- SOC

Highlights:

- Managed application deployments across multiple data centers.

---

# Projects

## Project

Id: proj_001

Name: Resume Tailor

Type: Personal

Repository: https://github.com/Sundar0603/resume-tailor

Technologies:

- Python

Domains:

- AI Agents

Highlights:

- Built a resume tailoring pipeline driven by a local LLM.

---

## Project

Id: proj_002

Name: SOCrates

Type: Personal

Technologies:

- Python
- OpenAI APIs

Domains:

- SOC Automation

Highlights:

- Built automated investigation pipelines reducing response time by 40%.

---

# Education

## Degree

Id: edu_001

Institution: Velammal Engineering College

Degree: Bachelor of Engineering

Major: Computer Science and Engineering

CGPA: 9.18

Location: Chennai

Duration: 2020 - 2024
"""


def knowledge_base_text() -> str:
    """Return a complete, valid Knowledge Base document."""
    return _MINIMAL


def without_line(text: str, needle: str) -> str:
    """Return the document with the first line containing ``needle`` removed."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if needle in line:
            del lines[index]
            break
    return "\n".join(lines)


@pytest.fixture
def kb_text():
    """A valid Knowledge Base document, as text."""
    return copy.copy(knowledge_base_text())
