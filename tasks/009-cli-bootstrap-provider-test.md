# Task 009 – CLI Bootstrap & Provider Smoke Test

## Objective

Implement the initial Resume Tailor CLI and verify that the AI infrastructure works end-to-end.

This task is intentionally limited in scope.

The goal is **not** to generate resumes.

The goal is to verify that:

- CLI
- Configuration Manager
- Credential Manager
- Provider Factory
- Provider
- LLM

can successfully communicate together.

This task acts as the integration test for all AI infrastructure implemented so far.

---

# Background

The following components have already been implemented:

- Configuration Manager
- Credential Manager
- Provider Factory
- AI Providers
- LLMProvider abstraction

Before building the JD Analyzer, we must verify that the entire provider stack functions correctly.

---

# Scope

Implement:

- CLI bootstrap
- Provider configuration flow
- Provider selection
- Provider initialization
- Provider smoke test
- Friendly terminal output

Do NOT implement:

- Resume parsing
- JD analysis
- Resume generation
- Prompt templates
- Rendering
- Validation
- Reports

---

# Commands

Implement the following command.

```
resume-tailor doctor
```

This command will become the standard diagnostic command for Resume Tailor.

Future versions may extend it.

For this task, it only verifies provider connectivity.

---

# Execution Flow

## Step 1

Load configuration.

```
Configuration exists?
```

If yes

↓

Load configuration

↓

Create provider

↓

Run provider test

---

If configuration does not exist

↓

Launch first-time setup.

---

# First-Time Setup

Display:

```
No AI provider is configured.

Let's configure Resume Tailor.
```

The CLI should discover all supported providers dynamically.

Do not hardcode provider names inside the CLI.

The provider metadata should drive the configuration process.

Example:

```
Select AI Provider

1. Ollama

2. OpenAI

3. Anthropic

4. Gemini

5. OpenRouter
```

The CLI should obtain this list from the provider registry/factory.

---

# Dynamic Configuration

After a provider is selected,

the CLI should ask only for the configuration fields required by that provider.

Examples

## Ollama

```
Host

Model
```

---

## OpenAI

```
API Key

Model

Base URL (optional)
```

---

## Anthropic

```
API Key

Model
```

---

## Gemini

```
API Key

Model
```

---

## OpenRouter

```
API Key

Model
```

The CLI must not contain provider-specific conditional logic.

It should simply iterate over the configuration metadata exposed by the provider.

---

# Configuration Persistence

After configuration:

Save

- provider
- model
- host

using the Configuration Manager.

Store

- API keys

using the Credential Manager.

Never write secrets to disk.

---

# Smoke Test

After configuration,

immediately test the provider.

Construct the provider using:

```
ProviderFactory
```

Send the following prompt.

System Prompt

```
You are a diagnostic endpoint.

Reply with the exact requested output.

Do not include explanations.
```

User Prompt

```
Reply with exactly:

Resume Tailor is working.
```

Expected output

```
Resume Tailor is working.
```

Print the model response to the terminal.

---

# Subsequent Runs

If configuration already exists,

the CLI should:

Load configuration

↓

Construct provider

↓

Run the smoke test

↓

Display the response

The user should not be prompted again.

---

# Terminal Output

Successful example

```
Resume Tailor Doctor

✓ Configuration loaded

Provider : Ollama

Model    : qwen3:32b

Testing connection...

✓ Connected successfully

Model Response

Resume Tailor is working.

All checks passed.
```

---

Configuration example

```
Resume Tailor Doctor

No provider configured.

Launching setup...
```

---

Failure example

```
Resume Tailor Doctor

Provider : Ollama

Testing connection...

✗ Failed to connect

Reason

Connection refused.

Verify that:

• Ollama is running

• The configured host is reachable

• The model is installed
```

No Python stack traces should be shown.

Errors should be user-friendly.

---

# Error Handling

Handle gracefully:

Configuration missing

Credential missing

Connection refused

Host unreachable

Authentication failure

Model not found

Timeout

Invalid configuration

Unexpected provider errors

Translate provider exceptions into clear CLI messages.

---

# Design Constraints

The CLI must never know:

- HTTP
- SDKs
- API Keys
- Provider implementations

The CLI communicates only with:

- Configuration Manager
- Credential Manager
- Provider Factory

The ProviderFactory returns an LLMProvider.

Everything beyond that should be transparent to the CLI.

---

# Verification

Cover:

## CLI

Configuration exists

Configuration missing

Interactive configuration flow

Smoke test success

Smoke test failure

---

## Provider Selection

Verify provider list is discovered dynamically.

No provider names should be hardcoded inside the CLI.

---

## Configuration

Configuration persisted correctly.

Credentials stored securely.

---

## Integration

Mock providers.

Verify:

CLI

↓

Provider Factory

↓

LLMProvider.generate()

is invoked correctly.

---

# Out of Scope

Do NOT implement:

Resume Parser

JD Analyzer

Resume Generator

LaTeX Rendering

Quality Gate

Reports

Streaming

Conversation Memory

Retry Policies

---

# Definition of Done

Task is complete when:

✓ `resume-tailor doctor` is fully functional.

✓ First-time users can configure a provider.

✓ Configuration is persisted.

✓ Secrets are stored securely.

✓ Providers are discovered dynamically.

✓ Provider-specific configuration is driven by provider metadata.

✓ ProviderFactory constructs the selected provider.

✓ The selected provider successfully communicates with the configured LLM.

✓ The terminal displays the model response.

✓ Subsequent executions reuse the saved configuration.