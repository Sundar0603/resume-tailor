# Task 014 – LaTeX Renderer

## Objective

Implement the LaTeX Renderer.

The renderer converts a structured `Resume` object into a complete LaTeX document using the existing user-provided LaTeX template.

The renderer must preserve the template's visual design and must not make layout decisions.

Its only responsibility is:

```text
Resume Object
      ↓
LaTeX Renderer
      ↓
resume.tex
```

---

# Background

The current pipeline is:

```text
Source Resume
      +
JobAnalysis
      +
ResumePlan
      +
Mode
      ↓
Resume Generator
      ↓
Resume Object
      ↓
Markdown Serializer
      ↓
generated.md
```

The next stage is to produce the LaTeX source that will later be compiled into a PDF.

The user already has LaTeX templates that define the resume's visual design.

The renderer must populate those templates with resume content.

---

# Scope

Implement:

- LaTeX template loading
- Resume → LaTeX rendering
- LaTeX escaping
- template variable replacement
- rendering errors
- unit tests

Do NOT implement:

- PDF compilation
- page counting
- layout optimization
- font-size changes
- spacing changes
- content shortening
- content prioritization
- revision logic
- visual inspection
- LLM calls

---

# Project Structure

Use the existing renderer area of the project.

Recommended structure:

```text
src/
    renderer/
        __init__.py
        latex_renderer.py
        exceptions.py
```

If a renderer package already exists, use it rather than creating a duplicate package.

Do not reorganize unrelated modules.

---

# Templates

Templates are stored under:

```text
templates/
```

Example:

```text
templates/
    backend.tex
    fullstack.tex
    cybersecurity.tex
```

Templates are part of the presentation layer.

The renderer must never rewrite or redesign the template.

The generated templates should be placed in a new directory inside the output directory: output/resumes/latex/.

---

# Template Selection

The renderer should select the template using the `template` information associated with the Resume metadata.

Example:

```python
resume.metadata.template
```

If the template is:

```text
cybersecurity
```

load:

```text
templates/cybersecurity.tex
```

Do not hardcode resume types inside the renderer.

---

# Public API

Expose a simple API such as:

```python
renderer = LatexRenderer(template_directory="templates")

latex = renderer.render(resume)
```

Return:

```python
str
```

The returned string must be a complete compilable LaTeX document.

Do not return partial fragments.

---

# Template Strategy

Use the existing templates as the authoritative layout definition.

Do not generate a new LaTeX template from scratch.

Do not allow the LLM to modify LaTeX.

The renderer should only populate the template with content from the `Resume` object.

---

# Recommended Template Approach

The existing LaTeX templates may need clearly defined placeholders.

For example:

```latex
{{CONTACT_NAME}}
{{CONTACT_EMAIL}}
{{SUMMARY}}
{{SKILLS}}
{{EXPERIENCE}}
{{PROJECTS}}
{{EDUCATION}}
```

Use a deterministic placeholder replacement mechanism.

If the existing templates already use a different placeholder mechanism, preserve that mechanism rather than changing the template unnecessarily.

The renderer should not perform arbitrary string manipulation outside the defined placeholders.

---

# Resume → LaTeX Mapping

## Contact

Map:

```text
Resume.contact
```

to the template's contact placeholders.

Typical fields:

- Name
- Phone
- Email
- LinkedIn
- GitHub

Preserve the template's existing formatting.

---

# Summary

Map:

```text
Resume.summary
```

to the summary placeholder.

Do not add or remove sentences.

Do not rewrite the summary.

---

# Skills

Map each skill category and its skills into the template's existing skills structure.

Preserve:

- category order
- skill order

Do not alphabetize or reorder skills.

Do not deduplicate skills.

---

# Work Experience

Map each Experience object into the template's existing work-experience structure.

Preserve:

- experience order
- technology order
- domain order
- highlight order

Every highlight should become the appropriate LaTeX bullet.

Example conceptually:

```latex
\item First highlight
\item Second highlight
\item Third highlight
```

The renderer must not change bullet ordering.

---

# Projects

Map each Project object into the template's existing project structure.

Preserve:

- project order
- technology order
- domain order
- highlight order

Every highlight must be rendered using the template's existing bullet structure.

---

# Education

Map every Education object into the existing education structure.

Preserve education order.

Do not modify education content.

---

# LaTeX Escaping

All user/model-generated text must be safely escaped before insertion into LaTeX.

At minimum, correctly handle characters such as:

```text
\
&
%
$
#
_
{
}
~
^
```

The exact escaping implementation should be compatible with the existing LaTeX templates.

Do not blindly escape text that is intentionally inserted as trusted LaTeX markup by the template itself.

Only resume content should be escaped.

---

# URLs

URLs must remain usable in the generated LaTeX.

The implementation should account for URLs containing characters such as:

```text
_
%
&
#
?
=
```

Do not corrupt links while escaping text.

Use the template's existing URL/link mechanism.

---

# Unicode

Resume content may contain Unicode characters.

The renderer must preserve Unicode whenever the selected LaTeX engine/template supports it.

Do not silently discard or replace characters.

If the current template cannot support a character, raise a clear rendering error rather than silently corrupting the content.

---

# Optional Fields

Optional fields should be handled gracefully.

If an optional field is absent:

- do not render `None`
- do not render the string `"None"`
- use the template's intended empty representation
- omit the corresponding content when appropriate

---

# Empty Collections

Handle empty optional collections safely.

For example:

```text
technologies = []
domains = []
repository = None
```

should not produce malformed LaTeX.

Required sections must remain structurally valid.

---

# Generated Entities

Projects and skill categories may have:

```python
source = EntitySource.GENERATED
```

The renderer should treat generated entities exactly like canonical entities.

Do not display runtime source metadata unless it is explicitly part of the LaTeX template.

Do not display runtime IDs.

---

# Runtime Metadata

The following are runtime-only and must never appear in the rendered resume unless explicitly represented by the template:

- entity IDs
- entity source
- validation state
- resume plan
- job analysis
- mode
- generation metadata
- revision metadata

The output is a normal professional resume.

---

# Determinism

Rendering the same Resume using the same template must produce byte-for-byte identical LaTeX.

Example:

```python
first = renderer.render(resume)
second = renderer.render(resume)

assert first == second
```

The renderer must not:

- use randomness
- use timestamps
- generate IDs
- modify content
- perform network calls

---

# No Mutation

Rendering must not modify the Resume object.

Example:

```python
before = resume.model_dump(deep=True)

renderer.render(resume)

after = resume.model_dump(deep=True)

assert before == after
```

---

# Template Preservation

The renderer must preserve the template's:

- document class
- packages
- fonts
- colors
- margins
- section styling
- spacing definitions
- custom macros
- header/footer configuration
- overall layout

The renderer must not:

- change font sizes
- change margins
- reduce spacing
- increase spacing
- remove packages
- add layout hacks
- modify the visual design based on content length

Layout optimization belongs to the later Quality Gate / Revision pipeline.

---

# Rendering Errors

Create a renderer-specific exception if one does not already exist.

Suggested:

```python
RenderingError
```

Raise a clear error when:

- template is missing
- template cannot be read
- required placeholder is missing
- unsupported template configuration is encountered
- content cannot be safely represented in the template

Do not silently produce incomplete LaTeX.

---

# Testing

Implement tests covering:

## Template Loading

- valid template loads
- missing template raises `RenderingError`

---

## Contact

Verify all contact fields are rendered correctly.

---

## Summary

Verify exact summary preservation.

---

## Skills

Verify:

- category order
- skill order
- multiple categories
- empty optional category content

---

## Experience

Verify:

- multiple experiences
- experience order
- technology order
- domain order
- highlight order
- exact text preservation

---

## Projects

Verify:

- multiple projects
- generated projects
- project order
- technology order
- highlight order

---

## Education

Verify multiple entries and exact preservation.

---

## LaTeX Escaping

Test content containing:

```text
&

%

$

#

_

{

}

~

^

```

Verify the generated LaTeX remains correctly escaped.

---

## URLs

Test URLs containing special characters.

Verify they remain valid.

---

## Optional Fields

Verify:

- missing repository
- empty technologies
- empty domains
- missing optional contact links

do not produce `None` or malformed LaTeX.

---

## Determinism

Rendering the same Resume twice must produce identical output.

---

## No Mutation

Verify the Resume is unchanged after rendering.

---

## Template Preservation

Verify that rendering does not modify the template file.

---

# Round-Trip / Integration Verification

The renderer should eventually support:

```text
Resume
  ↓
Markdown Serializer
  ↓
Markdown
```

and separately:

```text
Resume
  ↓
LaTeX Renderer
  ↓
resume.tex
```

For this task, only the second path needs to be implemented.

Do not add PDF compilation yet.

---

# Out of Scope

Do NOT implement:

- PDF generation
- pdflatex invocation
- page count
- overflow detection
- orphan-word detection
- visual analysis
- one-page optimization
- shortening
- revision loops
- ATS analysis
- LLM integration

---

# Definition of Done

The task is complete when:

- `LatexRenderer` is implemented.
- The correct template is selected from Resume metadata.
- Resume content is rendered into the existing LaTeX template.
- Template design is preserved.
- LaTeX-sensitive content is escaped correctly.
- URLs remain valid.
- Optional fields are handled safely.
- Generated and canonical entities render identically.
- Runtime metadata is not leaked into the resume.
- Rendering is deterministic.
- Rendering does not mutate the Resume.
- Missing/invalid templates produce clear errors.
- Unit tests pass.
- The resulting `.tex` output is a complete LaTeX document ready for compilation.
