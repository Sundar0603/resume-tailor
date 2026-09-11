---
resume: cybersecurity-ai
template: cybersecurity
version: 1.0
---

# Contact

Name: Sundar S

Phone: +91 7397398343

Email: sundarselvam3@gmail.com

LinkedIn: https://www.linkedin.com/in/sundar-s-870042235/

GitHub: https://github.com/Sundar0603

---

# Summary

Cybersecurity engineer who builds AI systems for security work. Two years shipping SOC platforms, threat intelligence pipelines, detection engineering workflows and firewall risk scoring in production, and an equal amount of time putting LLMs and agents to work on the same problems: MCP tool exposure for security APIs, agentic vulnerability triage, and automated IOC enrichment. Comfortable on both sides of the boundary, building the AI systems and hardening the surfaces they run against.

---

# Skills

## Security

- SOC Tooling
- Threat Intelligence
- Detection Engineering
- Incident Response
- Zero Trust
- API Security
- Malware Analysis
- Threat Enrichment
- Security Automation
- Firewall Systems
- SIEM Workflows
- Secure Design Review

## AI and Agentic Systems

- MCP
- LLM Tool Orchestration
- AI Agents
- Agentic Workflow Engines
- OpenAI APIs
- Anthropic APIs
- Tool Schema Design
- OpenAPI 3.1 Contracts
- Human-in-the-Loop Controls
- Prompt Engineering
- Local LLM Serving
- Ollama
- AI-powered Investigation Workflows

## Programming Languages

- Python
- Java
- JavaScript
- TypeScript
- JSX

## Backend

- Spring Boot
- REST APIs
- OAuth 2.0
- JWT
- Redis
- MySQL

## Frontend

- Vue
- HTML
- CSS
- Vite

## Tools

- Git
- Docker
- Linux
- Bash

---

# Work Experience

## Experience

Company: Zoho Corporation

Role: Software Developer

Employment Type: Full Time

Location: Chennai

Duration: May 2024 - Present

Technologies:

- Java
- JavaScript
- Spring Boot
- Redis
- MCP

Domains:

- AI Agents
- API Security
- Threat Intelligence
- Firewall Security
- Zero Trust
- Malware Analysis

Highlights:

- Building the MCP layer for an internal security platform, converting REST APIs already declared in the application's XML API catalog into model-invocable tools, so an AI agent discovers and calls the endpoints it needs at runtime instead of shipping a hand-written integration per API. The agent is bundled inside the existing application, and application code changed by zero lines.

- Designed a deny-by-default exposure model: of roughly 360 declared URLs, only the endpoints explicitly marked as tools exist to the model and every other route stays invisible, with generated OpenAPI 3.1 contracts making arguments schema-bound so anything the contract does not declare is rejected before the application ever sees it.

- Built the agent as a credential pass-through rather than a privileged service. The user's OAuth access token never enters the model context, is copied verbatim onto the rebuilt request, and is verified in exactly one place, the platform's existing SecurityFilter with IAM, so every AI-initiated call is scope-checked, throttled, attributed to the human user, and cannot widen its own scope.

- Proved the design end to end on a live server by filing a real security finding entirely through the agent, with every hop, tool discovery, tool call, rebuilt HTTP request and authorization check validated by the same filter as any other request.

- Developed API risk scoring for firewall systems, evaluating APIs across authentication strength, service dependencies, attack impact and other security indicators, producing the risk-based prioritization that improved API security posture by 20%.

- Built threat intelligence ingestion pipelines integrating external intelligence feeds and internal threat sources, normalizing and enriching indicators into a centralized TIP repository used to identify and block malicious traffic.

- Designed and implemented Zero Trust access control workflows, and built malware analysis workflows for ingestion, enrichment and visualization of threat artifacts, sharpening analyst visibility into malicious activity.

---

## Experience

Company: Zoho Corporation

Role: Software Developer Intern

Employment Type: Internship

Location: Chennai

Duration: Dec 2023 - Apr 2024

Technologies:

- Java
- JavaScript
- Spring Boot

Domains:

- SOC
- Incident Response
- Detection Engineering

Highlights:

- Contributed to incident management workflows for SOC operations and incident response, supporting analyst-driven incident creation and automated escalation of SLA-breached cases into security incidents, reducing investigation time by 30%.

- Developed rule management interfaces for detection engineering workflows, enabling analysts to author and maintain log-based detection rules that turn raw security events into investigation cases.

- Implemented key components of a six-stage incident response lifecycle, standardizing investigation, remediation and closure workflows for security analysts.

---

# Projects

## Project

Name: Triage Studio

Type: Personal

Repository: https://github.com/Sundar0603/Daily-Studies

Technologies:

- Python
- OpenAI APIs
- MCP
- Chrome DevTools Protocol
- Accessibility Trees

Domains:

- Vulnerability Validation
- Browser Automation
- AI Agents
- Offensive Security

Highlights:

- Built Triage Studio, an AI-powered vulnerability triage platform that reproduces and validates security findings by driving multiple browser and terminal sessions itself, executing authentication flows, triggering the vulnerability and collecting execution evidence for analyst verification.

- Developed an agent-based workflow engine over OpenAI APIs, CDP accessibility trees and human-in-the-loop guidance, coordinating multi-user attack scenarios and adapting the investigation plan in real time as the application responds, rather than replaying a fixed script.

- Implemented cross-session state coordination and evidence collection, validating vulnerabilities that only appear across multiple users, roles, browsers and execution environments while holding investigation context across the whole workflow.

---

## Project

Name: SOCrates

Type: Personal

Technologies:

- Python
- Vue.js
- OpenAI APIs
- MCP
- REST APIs

Domains:

- SOC Automation
- Threat Intelligence
- IOC Enrichment

Highlights:

- Built SOCrates, an AI-powered SOC assistant that automates IOC analysis and enrichment for indicators such as IPs and domains, cutting manual investigation effort by 60%.

- Designed an MCP-based orchestration architecture with LLM-driven tool routing and asynchronous workflows, letting the model pick which enrichment source to query rather than firing every integration at every indicator.

- Developed automated investigation pipelines with JSON-based data flows and ticketing integrations, improving triage efficiency and reducing response time by 40%.

---

## Project

Name: Resume Tailor

Type: Personal

Repository: https://github.com/Sundar0603/resume-tailor

Technologies:

- Python
- LLM Pipelines
- Multi-Provider LLM APIs
- LaTeX
- pdfminer

Domains:

- AI Systems
- LLM Reliability
- Automation

Highlights:

- Built Resume Tailor, an autonomous eight-stage LLM pipeline that turns a canonical resume and a job posting into a submission-ready, ATS-optimized one-page PDF in 60 to 80 seconds, with zero human decisions once the run starts, replacing an afternoon of manual rewriting per application.

- Engineered the whole system against the failure mode that quietly sinks most LLM tooling, output that is fluent and wrong: a structural validator, a vocabulary filter that blocks any technology absent from both the resume and the posting, and a strict mode in which no number can reach the output that was not already in the source.

- Built a deterministic revision engine that measures real page geometry from the compiled PDF, overflow, text overlap and orphan lines, then trims to one page under hard retention floors and fails loudly rather than shipping a silently gutted resume, an LLM system that refuses to hand over work it cannot stand behind.

- Made the pipeline provider-agnostic across five LLM backends, Ollama, OpenAI, Anthropic, Gemini and OpenRouter, with local models served over an SSH-forwarded host, and held the whole thing to 1,500+ automated tests plus live verification scripts that drive real models, because green offline tests had already once hidden a component that failed on every real invocation.

---

# Education

## Degree

Institution: Velammal Engineering College

Degree: Bachelor of Engineering

Major: Computer Science and Engineering

CGPA: 9.18

Location: Chennai

Duration: 2020 - 2024
