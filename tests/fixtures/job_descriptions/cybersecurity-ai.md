About the job

Senior Security Engineer, AI Systems & Detection Engineering

Location: Bengaluru, India (Hybrid) | Team: Product Security & Threat Detection | Career Level: IC3/IC4

About the Role

We are building the security layer for a platform that runs large language model (LLM) workloads for enterprise customers. This role sits at the intersection of two disciplines: hardening the platform against conventional and AI-specific attacks, and building the machine learning systems that detect attacks in the first place. You will write production code — this is an engineering role, not a policy or GRC role. Roughly 60% of your time will be spent building detection and defense services, and 40% on offensive testing, red-teaming of AI systems, and incident response.

You will own the security posture of our model-serving infrastructure end to end: the inference gateway, the retrieval-augmented generation (RAG) pipelines that feed it, the agentic tool-execution sandbox, and the data plane that stores customer prompts and embeddings.

Responsibilities

AI/ML Security Engineering
- Design and implement prompt-injection, jailbreak, and data-exfiltration defenses for LLM-backed products, including input/output classifiers, structured-output validation, and content provenance checks.
- Build and maintain a guardrail service that sits in front of model inference: sub-100ms p99 latency, fail-closed semantics, and per-tenant policy configuration.
- Harden the agentic tool-execution path — sandboxing, capability scoping, egress controls, and human-in-the-loop approval gates for irreversible actions.
- Secure RAG pipelines against index poisoning, cross-tenant embedding leakage, and untrusted-document instruction injection.
- Threat-model and red-team our own models and agents. Run adversarial evaluations, build automated attack harnesses, and track model risk over releases.
- Evaluate and defend against the OWASP Top 10 for LLM Applications and MITRE ATLAS techniques; map findings to controls and drive remediation with product teams.

Detection Engineering & Applied ML
- Build ML-based detection pipelines over security telemetry (authentication logs, API gateway traffic, EDR events, cloud audit logs) — anomaly detection, entity behavior analytics, and supervised classifiers for known attack patterns.
- Reduce false positives through feature engineering, model retraining loops, and detection-as-code practices with versioned rules and regression test suites.
- Instrument end-to-end observability for detections: metrics, traces, drift monitoring, and alert quality dashboards.
- Own the ML lifecycle for detection models — training data curation, offline evaluation, shadow deployment, and safe rollout.

Platform & Application Security
- Perform secure design reviews, threat modeling (STRIDE), and code review for services written in Python and Go.
- Build and maintain security automation: SAST/DAST/SCA in CI, secrets scanning, dependency and container image policy enforcement.
- Secure the software supply chain — signed artifacts, SBOM generation, provenance attestation (SLSA), and build-system isolation.
- Harden cloud infrastructure (AWS/GCP/Azure) and Kubernetes workloads: IAM least privilege, network policy, admission control, and runtime security.
- Implement and review cryptographic controls: key management, envelope encryption, mTLS service identity, and token/secret lifecycle.

Incident Response & Collaboration
- Participate in an on-call rotation for security incidents; lead investigations, contain and eradicate, and write blameless postmortems.
- Partner with platform, ML, and product engineering teams to land security work in their roadmaps rather than blocking releases.
- Mentor engineers on secure coding, and raise the security engineering bar across the organization.
- Support customer security questionnaires, audits, and compliance evidence (SOC 2, ISO 27001) with engineering artifacts rather than manual toil.

Minimum Qualifications
- 5+ years of professional software engineering experience, with at least 3 years focused on security engineering, application security, or detection engineering.
- Strong production coding ability in Python; working proficiency in at least one of Go, Rust, or Java.
- Demonstrated experience building or defending systems that use large language models, embeddings, or other ML models in production.
- Hands-on experience with threat modeling, secure design review, and vulnerability discovery in web services and APIs.
- Practical knowledge of cloud security on at least one major provider, and of containerized/Kubernetes workloads.
- Experience with security telemetry pipelines and SIEM/detection tooling (Splunk, Elastic, Chronicle, or equivalent).
- Solid grounding in applied cryptography, authentication, and authorization (OAuth 2.0, OIDC, JWT, mTLS).
- Familiarity with CI/CD pipelines and infrastructure-as-code (Terraform, Helm).

Preferred Qualifications
- Experience red-teaming LLM applications or publishing research on adversarial ML, prompt injection, or model extraction.
- Experience building guardrail, moderation, or abuse-detection systems at scale.
- Contributions to open-source security tooling, CVEs, or CTF/bug-bounty track record.
- Familiarity with MLOps tooling (MLflow, Kubeflow, vector databases such as pgvector, Pinecone, or Qdrant).
- Experience with eBPF-based runtime security, or with sandboxing technologies (gVisor, Firecracker, seccomp).
- Working knowledge of MITRE ATT&CK, ATLAS, NIST AI RMF, and the EU AI Act's technical obligations.
- Certifications such as OSCP, GPEN, GCIH, CISSP, or CKS.
- Experience presenting at security conferences or writing public technical content.

What Success Looks Like
- In 3 months: you have shipped at least one guardrail or detection improvement to production and completed a threat model of one critical AI surface.
- In 6 months: you own a security-critical service end to end, and measurable false-positive rates on your detections are trending down.
- In 12 months: your red-team findings have shaped the product roadmap, and other teams consult you before shipping AI features.
