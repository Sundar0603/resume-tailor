
# Task 007 – AI Provider Configuration & Credential Management

## Objective

Implement the AI provider configuration system for Resume Tailor.

Users should configure their preferred AI provider once. The configuration should be persisted locally and automatically loaded on subsequent executions.

The system must support multiple providers while keeping the rest of the application completely provider-agnostic.

This task establishes the infrastructure only.

It does **not** implement communication with any AI provider.

---

# Background

Resume Tailor communicates with AI models through the existing `LLMProvider` abstraction.

Both the Job Description Analyzer and the Resume Generator will depend only on this abstraction.

Instead of hardcoding an AI provider, users should configure their preferred provider once.

Example:

```
resume-tailor init
```

The tool stores the configuration locally.

Future commands automatically load this configuration.

---

# Existing Provider Interface

The project already contains the following abstraction.

```
src/
    analyzer/
        provider.py
```

```python
class LLMProvider(ABC):

    @abstractmethod
    def generate(self, prompt: str) -> str:
        ...
```

This file is the canonical provider abstraction.

Requirements:

- Keep this abstraction.
- Do not duplicate it.
- Do not move it unless absolutely necessary.
- Future provider implementations must implement this interface.

The Resume Generator will also depend on this same interface.

---

# Scope

Implement:

- configuration models
- configuration manager
- credential manager
- provider enumeration
- provider factory
- configuration persistence
- secure credential storage

Do NOT implement:

- Ollama HTTP communication
- OpenAI API communication
- Anthropic API communication
- Gemini API communication
- OpenRouter communication
- Resume generation
- JD analysis

---

# Supported Providers

The configuration system should support the following providers.

```
Ollama

OpenAI

Anthropic

Gemini

OpenRouter
```

No provider implementation is required in this task.

Only configuration support.

---

# Project Structure

```
src/

    analyzer/
        provider.py

    config/
        __init__.py
        models.py
        manager.py
        credentials.py
        exceptions.py

    providers/
        __init__.py
        factory.py
```

Notes:

- `analyzer/provider.py` already exists and must remain the provider abstraction.
- `providers/` will eventually contain concrete provider implementations in future tasks.
- The provider factory belongs in the `providers` package.

---

# Configuration File

Store configuration inside the user's home directory.

Use:

```
~/.resume-tailor/config.toml
```

The directory should be created automatically.

---

# Configuration Model

Implement using Pydantic v2.

Suggested model:

```python
class ProviderType(Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
```

```python
class ResumeTailorConfig(BaseModel):

    provider: ProviderType

    model: str

    host: str | None = None
```

Only non-sensitive configuration belongs here.

---

# Secure Credential Storage

API keys must never be stored in `config.toml`.

Use the Python `keyring` package.

The implementation should automatically use:

- macOS Keychain
- Windows Credential Manager
- Linux Secret Service / Keyring

The credential manager should expose something similar to:

```python
save(provider, api_key)

load(provider)

delete(provider)
```

Internally it should use:

```python
keyring.set_password(...)
keyring.get_password(...)
keyring.delete_password(...)
```

The configuration manager must not interact with keyring directly.

Credential storage should be isolated inside `credentials.py`.

---

# Configuration Manager

The configuration manager is responsible only for filesystem operations.

Responsibilities:

```
load()

save()

exists()

delete()
```

The configuration manager must never store secrets.

---

# Provider Factory

Create a provider factory.

Public API:

```python
provider = ProviderFactory.create(config)
```

Responsibilities:

- inspect configured provider
- construct the appropriate provider implementation

Since provider implementations do not yet exist, the factory may temporarily raise:

```
NotImplementedError
```

for supported providers.

The goal is to establish the architecture.

---

# Configuration Format

Example:

```toml
provider = "ollama"
model = "qwen3:32b"
host = "http://localhost:11434"
```

Example:

```toml
provider = "anthropic"
model = "claude-sonnet-4"
```

Example:

```toml
provider = "gemini"
model = "gemini-2.5-pro"
```

No secrets should ever appear inside this file.

---

# Separation of Responsibilities

Configuration Manager

```
config.toml

↓

ResumeTailorConfig
```

Credential Manager

```
OS Credential Store

↓

API Key
```

Provider Factory

```
ResumeTailorConfig

+

CredentialManager

↓

Concrete LLMProvider
```

JD Analyzer

```
LLMProvider
```

Resume Generator

```
LLMProvider
```

Neither the analyzer nor the generator should know anything about:

- config.toml
- keyring
- filesystem
- API keys

---

# Unit Tests

Implement tests covering:

## Configuration

- save configuration
- load configuration
- overwrite configuration
- delete configuration
- configuration existence

---

## TOML

- serialize
- deserialize
- malformed TOML

---

## Validation

- invalid provider
- missing required fields
- invalid model

---

## Credential Manager

Mock keyring.

Verify:

- save
- load
- delete
- missing credential

Tests must not modify the user's real credential store.

---

## Provider Factory

Unknown provider raises exception.

Known providers currently raise `NotImplementedError`.

---

# Dependencies

Allowed:

- pydantic
- tomllib / tomli
- keyring

No additional dependencies unless absolutely necessary.

---

# Out of Scope

Do NOT implement:

- HTTP communication
- API requests
- Streaming
- Retry logic
- Prompt construction
- Conversation memory
- Provider implementations
- CLI
- Resume generation
- Job description analysis

---

# Definition of Done

Task is complete when:

- configuration model implemented
- provider enumeration implemented
- configuration manager implemented
- credential manager implemented
- TOML persistence implemented
- secure credential storage implemented
- provider factory implemented
- comprehensive unit tests pass
- analyzer depends only on `LLMProvider`
- generator depends only on `LLMProvider`
- no secrets are written to disk