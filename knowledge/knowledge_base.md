---
knowledge_base: sundar
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

Label: cybersecurity and AI emphasis

Cybersecurity engineer who builds AI systems for security work. Two years shipping SOC platforms, threat intelligence pipelines, detection engineering workflows and firewall risk scoring in production, and an equal amount of time putting LLMs and agents to work on the same problems: MCP tool exposure for security APIs, agentic vulnerability triage, and automated IOC enrichment. Comfortable on both sides of the boundary, building the AI systems and hardening the surfaces they run against.

---

## Summary

Id: sum_002

Label: cybersecurity emphasis

Cybersecurity Engineer specializing in cybersecurity platforms, threat intelligence, security automation, building SOC platforms, and AI-powered investigation workflows. Experienced in building scalable backend systems, distributed services, and security-focused applications used for threat detection, analysis, and response.

---

## Summary

Id: sum_003

Label: backend emphasis

Backend Software Engineer with 2 years of experience at Zoho building enterprise-scale Security Operations Center (SOC) platforms using Java, Spring Boot, Vue.js, Redis and MySQL. Experienced in designing distributed workflows, AI-assisted workflow automation and investigation platforms using LLM APIs and delivering scalable backend services supporting security investigations and automated incident management.

---

## Summary

Id: sum_004

Label: full stack emphasis

Full Stack Software Developer with 2 years of experience at Zoho building enterprise-scale Security Operations Center (SOC) platforms using Java, Spring Boot, Vue.js, Redis and MySQL. Experienced in designing distributed workflows, AI-assisted workflow automation and investigation platforms using LLM APIs and delivering scalable backend services supporting security investigations and automated incident management.

---

# Skills

## Security

Id: skill_001

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

---

## AI and Agentic Systems

Id: skill_002

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

---

## Programming Languages

Id: skill_003

- Python
- Java
- JavaScript
- TypeScript
- JSX

---

## Backend

Id: skill_004

- Spring Boot
- REST APIs
- OAuth 2.0
- JWT
- Redis
- MySQL
- System Design
- Concurrency
- Database Design
- Query Optimization

---

## Frontend

Id: skill_005

- Vue.js
- Pinia
- Vue Router
- Vite
- HTML
- CSS

---

## Tools

Id: skill_006

- Git
- Docker
- Linux
- Bash
- MySQL

---

## AI and Automation

Id: skill_007

- OpenAI APIs
- MCP
- LLM Tool Orchestration
- AI-powered Investigation Workflows

---

## Databases

Id: skill_008

- MySQL

---

## Concepts

Id: skill_009

- Distributed Systems
- API Design
- Authentication and Authorization
- Caching
- Asynchronous Processing

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
- JavaScript
- Spring Boot
- Redis
- MCP
- MySQL
- Vue.js
- Pinia

Domains:

- AI Agents
- API Security
- Threat Intelligence
- Firewall Security
- Zero Trust
- Malware Analysis
- SOC Platforms
- Rule Management
- Workflow Automation
- Caching
- API Design
- Incident Management

Highlights:

- Building the MCP layer for an internal security platform, converting REST APIs already declared in the application's XML API catalog into model-invocable tools, so an AI agent discovers and calls the endpoints it needs at runtime instead of shipping a hand-written integration per API. The agent is bundled inside the existing application, and application code changed by zero lines.

- Designed a deny-by-default exposure model: of roughly 360 declared URLs, only the endpoints explicitly marked as tools exist to the model and every other route stays invisible, with generated OpenAPI 3.1 contracts making arguments schema-bound so anything the contract does not declare is rejected before the application ever sees it.

- Built the agent as a credential pass-through rather than a privileged service. The user's OAuth access token never enters the model context, is copied verbatim onto the rebuilt request, and is verified in exactly one place, the platform's existing SecurityFilter with IAM, so every AI-initiated call is scope-checked, throttled, attributed to the human user, and cannot widen its own scope.

- Proved the design end to end on a live server by filing a real security finding entirely through the agent, with every hop, tool discovery, tool call, rebuilt HTTP request and authorization check validated by the same filter as any other request.

- Developed API risk scoring for firewall systems, evaluating APIs across authentication strength, service dependencies, attack impact and other security indicators, producing the risk-based prioritization that improved API security posture by 20%.

- Built threat intelligence ingestion pipelines integrating external intelligence feeds and internal threat sources, normalizing and enriching indicators into a centralized TIP repository used to identify and block malicious traffic.

- Designed and implemented Zero Trust access control workflows, and built malware analysis workflows for ingestion, enrichment and visualization of threat artifacts, sharpening analyst visibility into malicious activity.

- Built threat intelligence ingestion pipelines integrating external intelligence feeds and internal threat sources, normalizing and enriching indicators into a centralized TIP repository to identify and block malicious traffic.

- Designed and implemented Zero Trust access control workflows securing and strengthening platform security.

- Developed API risk scoring functionality for firewall systems, evaluating APIs across authentication strength, service dependencies, attack impact, and other security indicators, resulting in a 20% improvement in API security posture through risk-based visibility and prioritization.

- Developed malware analysis workflows for ingestion, processing, enrichment, and visualization of threat artifacts, improving analyst visibility into malicious activity.

- Designed database schemas, developed end-to-end features for a SOC platform using MySQL and Vue.js, enabling case management, investigation workflows, analyst collaboration, and event-driven ticket generation.

- Developed a rule management platform for creating, validating, versioning, and deploying event-processing rules powering automated ticket generation workflows.

- Designed and implemented 20+ Spring Boot RESTful APIs supporting pagination, filtering, sorting, authentication, and workflow management, improving scalability and usability across enterprise applications.

- Implemented Redis-backed API rate limiting to safeguard security infrastructure against automated API loops and flood attacks, dropping malicious or malfunctioning traffic instantly at the edge layer.

- Engineered high-performance SOC queries with strict time-partitioning and streamlined string matches, increasing database efficiency and cutting execution delays by 70%.

- Designed Redis-based caching strategies for frequently accessed firewall rules and high-priority API metadata, significantly reducing database load and improving retrieval latency.

- Developed a rule management platform enabling users to create, edit, validate, and manage event-processing rules used for automated ticket generation and workflow automation.

- Built and maintained reusable Vue.js component libraries, reactive Pinia state management, dynamic forms, role-based workflows, and analytics dashboards used across enterprise platforms.

- Optimized database performance by restructuring data models and isolating infrequently accessed fields into dedicated tables loaded on demand, reducing query execution time by up to 70%.

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
- JavaScript
- Spring Boot

Domains:

- SOC
- Incident Response
- Detection Engineering
- Deployment
- Data Retention

Highlights:

- Contributed to incident management workflows for SOC operations and incident response, supporting analyst-driven incident creation and automated escalation of SLA-breached cases into security incidents, reducing investigation time by 30%.

- Developed rule management interfaces for detection engineering workflows, enabling analysts to author and maintain log-based detection rules that turn raw security events into investigation cases.

- Implemented key components of a six-stage incident response lifecycle, standardizing investigation, remediation and closure workflows for security analysts.

- Contributed to the development of incident management workflows for SOC operations and incident response, supporting analyst-driven incident creation and automated escalation of SLA-breached cases into security incidents, reducing investigation time by 30%.

- Implemented key components of a six-stage incident response lifecycle, helping standardize investigation, remediation, and closure workflows for security analysts.

- Developed rule management interfaces for detection engineering workflows, enabling analysts to manage log-based detection rules that generate investigation cases from security events.

- Implemented Service Worker-based request interception and proxying mechanisms to initialize internal application frameworks and streamline communication between frontend applications and backend services.

- Implemented data retention policies for high-volume enterprise workflow platforms, limiting active datasets to recent records and pruning historical data to maintain query performance at scale.

- Managed application deployments across multiple data centers using internal deployment tooling, supporting production releases and ensuring consistent application availability across distributed environments.

---

# Projects

## Project

Id: proj_001

Name: Triage Studio

Type: Personal

Technologies:

- Python
- OpenAI APIs
- MCP
- Chrome DevTools Protocol
- Accessibility Trees
- Vue.js
- REST APIs
- Browser Automation

Domains:

- Vulnerability Validation
- Browser Automation
- AI Agents
- Offensive Security
- Backend Development
- Workflow Automation
- Full Stack Development

Highlights:

- Built Triage Studio, an AI-powered vulnerability triage platform that reproduces and validates security findings by driving multiple browser and terminal sessions itself, executing authentication flows, triggering the vulnerability and collecting execution evidence for analyst verification.

- Developed an agent-based workflow engine over OpenAI APIs, CDP accessibility trees and human-in-the-loop guidance, coordinating multi-user attack scenarios and adapting the investigation plan in real time as the application responds, rather than replaying a fixed script.

- Implemented cross-session state coordination and evidence collection, validating vulnerabilities that only appear across multiple users, roles, browsers and execution environments while holding investigation context across the whole workflow.

- Built Triage Studio, an AI-powered vulnerability triage platform that reproduces and validates security findings by orchestrating multiple browser and terminal sessions, executing authentication flows, triggering vulnerabilities, and collecting execution evidence for analyst verification.

- Developed an agent-based workflow engine leveraging OpenAI APIs, CDP accessibility trees, and human-in-the-loop guidance to coordinate multi-user attack scenarios, adapt investigation plans in real time, and automate end-to-end vulnerability validation.

- Implemented cross-session state coordination and evidence collection capabilities, enabling validation of vulnerabilities across multiple users, roles, browsers, and execution environments while maintaining investigation context throughout the workflow.

- Built Triage Studio, a full-stack AI-powered platform using Vue.js, Python, REST APIs, and browser automation to orchestrate multi-user workflows, automate vulnerability validation, and provide real-time investigation tracking.

- Developed interactive Vue.js workflows and an agent-based execution engine with real-time status updates, browser automation, asynchronous processing, and human-in-the-loop guidance for multi-step investigations.

- Designed scalable backend services and data flows for cross-session state management, evidence collection, and real-time collaboration, enabling seamless coordination across multiple users, roles and execution environments.

---

## Project

Id: proj_002

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
- Backend Development
- AI Workflows
- Full Stack Development

Highlights:

- Built SOCrates, an AI-powered SOC assistant that automates IOC analysis and enrichment for indicators such as IPs and domains, cutting manual investigation effort by 60%.

- Designed an MCP-based orchestration architecture with LLM-driven tool routing and asynchronous workflows, letting the model pick which enrichment source to query rather than firing every integration at every indicator.

- Developed automated investigation pipelines with JSON-based data flows and ticketing integrations, improving triage efficiency and reducing response time by 40%.

- Built SOCrates, an AI-powered SOC assistant using Python, Vue.js, OpenAI APIs, MCP, and REST APIs, enabling automated IOC analysis and enrichment for indicators such as IPs and domains, reducing manual investigation effort by 60%.

- Designed an MCP-based orchestration architecture with LLM-driven tool routing, asynchronous workflows, and API integrations to support scalable enrichments.

- Developed automated security investigation pipelines using JSON-based data flows and ticketing integrations, improving triage efficiency while reducing response time by 40%.

- Built a full-stack AI application using Python, Vue.js, OpenAI APIs and REST APIs, implementing asynchronous workflows, tool orchestration and data enrichment pipelines.

- Developed automated investigation pipelines using JSON-based data flows and ticketing integrations, improving triage efficiency while reducing response time by 40%.

---

## Project

Id: proj_003

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

Id: edu_001

Institution: Velammal Engineering College

Degree: Bachelor of Engineering

Major: Computer Science and Engineering

CGPA: 9.18

Location: Chennai

Duration: 2020 - 2024
