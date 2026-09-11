# Resume Tailor

An AI-powered CLI that rewrites a canonical Markdown resume to fit a specific job
description, renders it through a frozen LaTeX template, compiles it, checks the
page geometry, shortens it to one page when needed, and writes a report
explaining every change.

```text
Source Resume + Job Description + Mode
    ↓
JD Analyzer → Resume Planner → Resume Generator
    ↓
Validator → LaTeX Renderer → pdflatex → Quality Gate
    ↓
Revision Engine   (only when the page overflows)
    ↓
Reporter → report.md + changes.md + report.json
```

A typical run takes **60–80 seconds** and produces a submission-ready one-page PDF.

---

## Install

Python **3.9** (the venv is 3.9; `X | Y` unions will not parse).

```bash
python -m venv .venv
.venv/bin/pip install -e .
```

This installs the `resume-tailor` console script. Every example below can also be
run as `.venv/bin/python -m src.cli.main <command>` without activating the venv.

### LaTeX

PDF compilation needs **pdflatex**. This project uses TinyTeX:

```bash
export PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$PATH"
```

`pdflatex` is **not on PATH in a non-login shell**, so tooling that shells out
with plain `bash` silently skips every compilation step. Export the path above
first, or `resume-tailor doctor` will report the toolchain as missing.

Required TeX packages: `babel-english`, `tools`, `fontawesome5`, `graphics`,
`pgf`, `xcolor`, `cormorantgaramond`, `charter`, `psnfss`, `symbol`, `zapfding`,
`etoolbox`, `fontaxes`. Install a missing one with `tlmgr install <pkg>`; find
which package owns a missing file with `tlmgr search --global --file /<name>.sty`.

### Configuration

Configuration lives at `~/.resume-tailor/config.toml`; API keys go in the OS
keyring, never in a file. Run `resume-tailor doctor` once and it will walk you
through provider setup.

> **Note:** `config/config.yaml` in this repo is **inert**. Nothing in `src/`
> reads it. Editing it does nothing.

---

## Commands

| command | what it does |
|---|---|
| [`resume-tailor doctor`](#resume-tailor-doctor) | Configure a provider and verify everything is reachable |
| [`resume-tailor tailor`](#resume-tailor-tailor) | **The main command.** Job description → finished PDF + reports |
| [`resume-tailor analyze`](#resume-tailor-analyze) | Debug view: what the AI extracted from a job description |
| [`resume-tailor plan`](#resume-tailor-plan) | Debug view: what the AI intends to change, before it writes anything |

Every command exits **0** on success and **1** on any failure, and prints a
message rather than a stack trace.

---

### `resume-tailor doctor`

Verifies the install: provider configuration, credentials, a live round trip to
the model, and the LaTeX toolchain. On a fresh machine it runs a setup wizard
that lists the available providers and prompts for model, host and API key.

```bash
resume-tailor doctor
```

The LaTeX check is **diagnostic only and never changes the exit code** — a
missing TeX distribution still leaves analysis, planning and generation working.

---

### `resume-tailor tailor`

The whole pipeline, autonomously. Once the run starts there are no confirmation
prompts.

```bash
resume-tailor tailor
```

That form discovers your canonical resumes, asks which one to use if there is
more than one, and then waits for you to paste a job description.

| option | default | meaning |
|---|---|---|
| `--resume PATH` | *discovered* | Use this resume. Skips discovery entirely. |
| `--jd PATH` | *paste on stdin* | Read the job description from a file. |
| `--mode aggressive\|strict` | `aggressive` | How much licence the AI has. See [Modes](#modes). |
| `--content-dir DIR` | `content` | Where canonical resumes live. |
| `--output DIR` | *timestamped* | Override the run's artifact directory. |

**Examples**

```bash
# Fully interactive: pick a resume, paste the posting, press Ctrl+D
resume-tailor tailor

# Everything specified
resume-tailor tailor \
    --resume content/backend_resume.md \
    --jd tests/fixtures/job_descriptions/backend.md \
    --mode aggressive

# Pipe a job description in
pbpaste | resume-tailor tailor --resume content/backend_resume.md --mode strict
cat posting.txt | resume-tailor tailor
```

**Choosing a resume.** Everything matching `*.md` in the content directory is a
candidate. None is an error; exactly one is selected silently; several are
offered as a numbered list. There is no `--template` flag — each resume names its
own template in its front matter.

**Pasting a job description.** When `--jd` is omitted the command reads stdin to
EOF. Paste, then press **Ctrl+D** (Ctrl+Z on Windows). There is no size limit.

**Output.** Each run gets its own directory,
`output/runs/<resume>_<mode>_<YYYYMMDD-HHMMSS>/`, so runs never overwrite one
another:

```text
output/runs/backend_aggressive_20260904-173738/
├── generated.md            the tailored resume as Markdown
├── resume.tex / .pdf / .log    the first compile, before any shortening
├── work/                   scratch space for each revision attempt
├── attempt_<n>/            checkpoints
├── final/resume.pdf        ← the resume to submit, when revision ran
├── revision_trail.json     every removal, with the resulting page count
├── report.md               what changed and why
├── changes.md              per-entity before/after
└── report.json             the same, machine-readable
```

The command prints the path to the final PDF, so you never have to work out
whether to open `final/resume.pdf` or `resume.pdf`.

**Failure.** A run that cannot reach one page within the retention floors stops
with the shortfall, the last PDF and the revision trail, and writes no report —
there is no finished run to describe. A run that compiles but fails the quality
gate *does* get a report, lists the blocking findings, and still exits 1. The
command never claims a resume it does not have.

---

### `resume-tailor analyze`

Prints what the AI extracted from a job description — role, seniority, required
and preferred skills, technologies, domains, responsibilities, keywords. Useful
for checking whether a posting is being read the way you expect. Writes nothing
to disk.

```bash
resume-tailor analyze              # paste, then Ctrl+D
pbpaste | resume-tailor analyze
cat posting.txt | resume-tailor analyze
```

Reads stdin only — there is no `--jd` option on this command.

---

### `resume-tailor plan`

Prints what the AI intends to change *before* it writes any prose: per section,
the action (KEEP / REWRITE / REMOVE / GENERATE), a priority, a rewrite strategy
and the reasoning. This is the best place to look when a tailored resume comes
out wrong — it separates a bad decision from bad writing.

```bash
resume-tailor plan --resume content/backend_resume.md --jd posting.md
resume-tailor plan --resume content/backend_resume.md --jd posting.md --mode strict
```

| option | required | default | meaning |
|---|---|---|---|
| `--resume PATH` | yes | — | Resume Markdown file |
| `--jd PATH` | yes | — | Job description file |
| `--mode aggressive\|strict` | no | `aggressive` | See [Modes](#modes) |

The plan is never written to disk.

---

## Modes

| mode | what it allows |
|---|---|
| `strict` | **No new facts.** Nothing may appear that is not already in your resume. Roles are immutable, no projects or skill categories are invented, and no number reaches the output that was not in the source. |
| `aggressive` | May invent a project or a skill category from the job description, may rewrite a role title, and asks for one quantified outcome per experience — drawn from the source where one fits. |

Both modes filter technologies and domains against a vocabulary, so a term that
appears in neither your resume nor the job description cannot reach the output.

---

## Development

```bash
# All tests. uv is not on PATH here — use the venv's python directly.
.venv/bin/python -m pytest

# With LaTeX, or 83 compilation tests skip silently
export PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$PATH"
.venv/bin/python -m pytest

# One package
.venv/bin/python -m pytest tests/pipeline -q
.venv/bin/python -m pytest tests/cli -q
```

Current baseline: **1503 passing, 3 skipped**.

### Live verification scripts

Offline tests are not evidence — this project once shipped a component with 318
green tests while every real invocation failed. These drive real models and are
**not collected by pytest**:

```bash
# Full chain, one pairing, dumping every stage to output/runs/<name>/
.venv/bin/python scripts/live_run.py content/backend_resume.md \
    tests/fixtures/job_descriptions/backend.md STRICT

# Replay the Revision Engine over resumes already on disk. Real pdflatex,
# real Quality Gate, zero LLM calls.
.venv/bin/python scripts/replay_revision.py [run-name ...]

# Before/after matrix for the planner's entry manifest: 3 pairings x 2 modes.
.venv/bin/python scripts/manifest_matrix.py [trials]

# Per-component live checks
.venv/bin/python tests/pipeline/verify_pipeline.py
.venv/bin/python tests/generator/verify_generation.py
.venv/bin/python tests/planner/verify_determinism.py
.venv/bin/python tests/renderer/verify_round_trip.py
.venv/bin/python tests/renderer/verify_latex_render.py
.venv/bin/python tests/analyzer/verify_determinism.py
.venv/bin/python tests/verify_parser.py
```

> `scripts/live_run.py` keys its output directory on resume + mode and
> **overwrites in place**, so a crashed run can leave the previous run's
> artifacts looking current. `resume-tailor tailor` does not have this problem —
> it writes a fresh timestamped directory every time.

### Local models

Models run on a Mac Studio reached by an SSH local port forward:

```bash
ssh -N -L 11434:localhost:11434 ai-test@10.71.21.226
```

`-N` means the terminal shows no output after the password — that is expected,
not a hang. Verify with `lsof -i :11434` (ssh should be LISTEN) and
`curl localhost:11434/api/tags`. No `OLLAMA_HOST` change is needed.

---

## Layout

```text
content/            canonical resumes (Markdown, one per target role)
templates/          frozen LaTeX templates; the AI never touches these
  masterTemplates/  the hand-tuned originals, kept for reference
src/
  cli/              the four commands, plus shared plumbing in _common.py
  parser/           Markdown → Resume, and the domain models
  validation/       structural rules the generated resume must satisfy
  analyzer/         job description → JobAnalysis
  planner/          what to change, and why
  generator/        the words
  renderer/         Markdown serializer + LaTeX renderer
  compiler/         pdflatex
  quality/          page geometry: overflow, overlap, orphans, glyphs
  revision/         shortening to one page
  report/           report.md, changes.md, report.json
  pipeline/         the chain, end to end
  providers/        Ollama, OpenAI, Anthropic, Gemini, OpenRouter
  config/           TOML config + OS keyring
docs/
  PROJECT_KNOWLEDGE.md   dense reference; read this before changing anything
  ARCHITECTURE.md        frozen, with an amendment log
output/             every run's artifacts (gitignored)
```

`docs/PROJECT_KNOWLEDGE.md` is the file to read before making a change. It
records what was measured, what was tried and abandoned, and why each
non-obvious decision is the way it is.
