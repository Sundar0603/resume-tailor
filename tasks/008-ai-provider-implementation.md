# Task 008 – Implement AI Providers

## Objective

Implement all supported AI providers for Resume Tailor.

The project currently contains:

- the `LLMProvider` abstraction
- provider configuration
- secure credential storage
- provider factory

This task implements the concrete providers.

The implementation must be provider-agnostic and extensible so that future providers can be added with minimal changes.

---

# Background

Resume Tailor communicates with AI models exclusively through the existing `LLMProvider` abstraction.

Both the Job Description Analyzer and the Resume Generator depend only on this abstraction.

Neither component should know:

- which provider is being used
- how authentication works
- how requests are sent
- how SDKs work

Those responsibilities belong entirely to the provider implementations.

---

# Existing Provider Interface

The project already contains:

```
src/
    analyzer/
        provider.py
```

This remains the canonical abstraction.

The interface should be enhanced to support modern LLM APIs.

Current:

```python
class LLMProvider(ABC):

    @abstractmethod
    def generate(self, prompt: str) -> str:
        ...
```

Update it to:

```python
class LLMProvider(ABC):

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        ...
```

Rationale:

Modern providers distinguish between:

- system prompts
- user prompts

and expose generation parameters such as temperature.

The analyzer and generator should not need provider-specific code to use these capabilities.

Also, add whatever parameters you think are important for future extensibility and make it as optional as possible.

---

# Supported Providers

Implement:

- Ollama
- OpenAI
- Anthropic
- Gemini
- OpenRouter

---

# Project Structure

```
src/

    analyzer/
        provider.py

    providers/
        __init__.py
        base.py
        factory.py

        ollama.py
        openai.py
        anthropic.py
        gemini.py
        openrouter.py
```

---

# Provider Responsibilities

Each provider is responsible for:

- validating its configuration
- loading credentials
- constructing SDK clients
- sending prompts
- returning raw model output

Providers must never:

- parse JSON
- validate JobAnalysis
- construct prompts
- understand resumes
- perform ATS optimization

---

# Provider Metadata

Each provider should expose the configuration it requires.

Example:

```python
required_configuration()
```

or an equivalent mechanism.

Example:

Ollama

```
Host

Model
```

OpenAI

```
API Key

Model

Base URL (optional)
```

Anthropic

```
API Key

Model
```

Gemini

```
API Key

Model
```

OpenRouter

```
API Key

Model
```

The CLI should use this metadata to know what configuration to collect.

The CLI must not contain provider-specific logic.

Adding a new provider should require no CLI changes.

---

# Authentication

Use the existing Credential Manager.

Never read secrets directly from configuration files.

Never store secrets on disk.

API keys should be loaded from the operating system credential store.

---

# SDKs

Use the official SDK for each provider.

Ollama

```
ollama
```

OpenAI

```
openai
```

Anthropic

```
anthropic
```

Gemini

```
google-genai
```

OpenRouter

```
openai
```

using OpenRouter's base URL.

Do not manually construct HTTP requests unless required.

---

# Provider Factory

Update the provider factory.

Public API:

```python
provider = ProviderFactory.create(config)
```

The factory should instantiate the appropriate provider.

The rest of the application should never instantiate providers directly.

---

# Error Handling

Translate provider-specific exceptions into project-specific exceptions.

The analyzer and generator should never receive SDK exceptions.

Suggested:

```
ProviderError

AuthenticationError

ConnectionError

RateLimitError

ProviderResponseError
```

Provider implementations should map SDK errors appropriately.

---

# Unit Tests

Mock all SDKs.

Tests must never perform real network requests.

Cover:

## Ollama

- successful generation
- connection failure
- invalid model

---

## OpenAI

- successful generation
- authentication failure
- timeout

---

## Anthropic

- successful generation
- authentication failure

---

## Gemini

- successful generation
- authentication failure

---

## OpenRouter

- successful generation
- authentication failure

---

## Factory

Verify correct provider is returned.

Unknown provider raises exception.

---

## Configuration Metadata

Verify each provider exposes the correct required configuration.

---

# Dependencies

Allowed:

- ollama
- openai
- anthropic
- google-genai

No additional networking libraries.

---

# Out of Scope

Do NOT implement:

- conversation memory
- streaming
- retry policies
- prompt templates
- JSON parsing
- resume generation
- JD analysis

---

# Definition of Done

Task is complete when:

- all five providers implemented
- `LLMProvider` enhanced with system prompt and temperature support
- all additional parameters you think are important for future extensibility and make them as optional as possible.
- provider metadata implemented
- provider factory updated
- secure credential loading integrated
- SDK exceptions translated into project exceptions
- comprehensive unit tests pass
- analyzer and generator remain completely provider-agnostic
