# Task 002 - Migrate Domain Models to Pydantic

The parser is complete and working correctly.

Refactor the existing domain models from Python `dataclasses` to **Pydantic v2** models.

## Requirements

- Replace every `@dataclass` with `pydantic.BaseModel`.
- Use Pydantic v2.
- Preserve all existing field names and type annotations.
- Preserve the existing parser API.
- The parser implementation should require minimal or no changes.
- Add the following configuration to every model:

```python
model_config = ConfigDict(
    extra="forbid",
    validate_assignment=True,
)
```

## Do NOT

- Add validation rules (`EmailStr`, `Field`, validators, etc.).
- Change the parser behavior.
- Rename fields.
- Add business logic or helper methods.

## Verification

The following should continue to work:

```python
parser = ResumeParser()
resume = parser.parse("content/cybersecurity.md")
```

The following should also succeed:

```python
resume.model_dump()

Resume.model_validate(
    resume.model_dump()
)
```

Finally, run all existing parser tests and ensure they continue to pass.
