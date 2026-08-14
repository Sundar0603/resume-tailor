# Resume Planner — build verdict

Companion to `tasks/011-resume-planner.md`. That file is the spec as written; this one is
what happened when it was built and run against a real local model. Written to be handed
to whoever plans the next task.

**Status: complete and verified.** `src/planner/` and `resume-tailor plan` are built and
match the spec — models, exception hierarchy, validation ruleset, canonicalization
contract and CLI all as designed. The decisions table in the spec held; nothing in it
needed revisiting.

---

## 1. Two bugs that only a live model exposes

The offline suite passed at 318 tests while every real invocation failed. Both bugs sat in
the gap between "schema is correct" and "a model will actually produce it".

### 1.1 Reasoning models return an empty response

`src/providers/ollama.py` called `chat()` without disabling reasoning. qwen3/qwen3.6 spend
their entire `num_predict` budget on hidden thinking tokens and return an empty
`message.content`, surfacing as `InvalidAnalyzerResponse` / `InvalidPlannerResponse` —
indistinguishable from a dead provider.

Fixed by passing `think: False`. Applies to any thinking-capable local model, benefits the
analyzer identically, and is harmless on non-thinking models (verified against
`qwen2.5:7b`). Guarded by `tests/providers/test_ollama.py::test_reasoning_is_always_disabled`.

### 1.2 Schema field order in the prompt is load-bearing

The spec's risk 2 anticipated *prompt size* as the local-model hazard. The real hazard was
*field order*.

The skeleton asks for four entry shapes in one JSON object, and a small model reproduces
them **positionally**. `skills_plans` listed `new_category_name` immediately after
`priority` with `reasoning` last, while the other three shapes had `reasoning` in that
slot. The model wrote a skills-shaped `GENERATE` entry, then carried that layout into
`project_plans` — emitting `"new_category_name": null` where `reasoning` belonged. One
positional slip, two validation failures at once: a required field missing and an
`extra="forbid"` violation.

Fixed by uniformity: `reasoning` immediately after `priority` in **all four** shapes, with
shape-specific fields after it. Pinned by
`tests/planner/test_determinism.py::TestSchemaFieldOrder`, which was confirmed to fail when
the old order is reinstated.

**Generalise this.** When one JSON object contains several similar-but-distinct shapes,
keep their shared fields in identical positions, and phrase required fields
unconditionally. `reasoning` was rendered `"<why>"` and was always emitted; conditionally
phrased slots (`"<non-null only if action is REWRITE>"`) get skipped by small models. Prose
rules elsewhere in the prompt do not compensate — the skeleton wins. This was demonstrated
twice, on two different models, in two different ways.

### 1.3 A wrong fix, recorded deliberately

The first diagnosis was "strip foreign keys whose value is null in `canonical.py`". That
would have removed the stray `new_category_name` and **still failed**, because `reasoning`
was also missing — one cause, two symptoms, and the symptom-level fix addresses one.

It looked correct because an accidentally-different input made the failure appear
intermittent: a debug script read the JD with `read_text()` while `src/cli/plan.py` uses
`read_text().strip()`. Different bytes, different prompt, different outcome.

**Any harness compared against a CLI run must reproduce the CLI's input handling exactly.**

---

## 2. Determinism — decided, and it earned its keep

**Decision: the analyzer and the planner stay deterministic. The generator need not be.**

Both analyzer and planner emit structured *decisions*, where two different answers to the
same input cannot both be right, so variety has no value. The generator writes prose, where
it does.

Note the analyzer is deterministic by construction regardless of mode: `analyze()` takes no
mode parameter, so aggressive/strict is purely a planner concept and cannot reach it.

The practical argument is debugging, not purity. Determinism is what turned the field-order
bug from an apparent flake into a fixable defect: identical runs produced identical
failures, the exact payload could be dumped, and two identical passes afterwards proved the
fix rather than suggesting it. At a nonzero temperature the wrong fix in §1.3 would have
"passed" often enough to ship.

Coverage: `tests/planner/test_determinism.py` (offline, 17 tests) and
`tests/planner/verify_determinism.py` (live N-iteration identity check, named `verify_*`
so pytest does not collect it). Closes risk 7 in the spec.

### Consequence for the revision engine

**`max_revisions: 3` cannot work at temperature 0.** A pinned seed at temperature 0 returns
byte-identical text, so "revise this section" is a no-op. Revision needs either a changed
prompt per pass or a nonzero temperature. Decide this before building it — it has the
widest blast radius of any open decision.

Also: greedy decoding (`top_k=1`) tends toward flat, repetitive prose. Fine for decisions,
a quality cost for resume bullets.

---

## 3. Model choice is a project decision

Three local models, same resume and JD. Each failed in a way the others did not — there is
no single "make small models work" fix, only a sequence of per-model tics.

| Model | Aggressive | Strict | Per-plan latency | Failure mode |
| ---------------- | ---------- | ------ | ---------------- | -------------------------------------------- |
| `qwen2.5:7b` | fails | passes | 75–90s | omits `rewrite_strategy` on `REWRITE` entries |
| `gemma4:12b` | passes | fails | 150–170s | misspells `keywords_to_include`; null lists |
| `qwen3.6:latest` | passes | passes | 19–83s (see §4) | none across 18 combinations, twice |

**`qwen3.6:latest` is the working model.** Do not re-litigate without re-running the sweep.

`gemma4:12b` is excluded on latency alone — 2m32s for planning against a three-minute
end-to-end budget that does not yet include generation.

`qwen2.5:7b` reproduced the originally reported symptom exactly: `REWRITE` with no
`rewrite_strategy` — "change this" with no instruction for how. Root cause was the
conditional phrasing described in §1.2. Rephrasing to
`"<REQUIRED when action is REWRITE: ...>"` halved the failures but did not eliminate them.
The rephrasing is kept because it is strictly more accurate.

**Validation passing is not the same as a good plan.** 7b's output is poor in ways no
schema can catch: the *byte-identical* `rewrite_strategy` on an internship, a senior role
and a personal project; the same four keywords on every entry; no use of `CRITICAL`; and
four skill removals including `System Design` and `Concurrency` from a backend resume.
qwen3.6 emitted **zero** removals across all 18 combinations. A plan that quietly deletes
real skills is worse than one that fails loudly.

One model-independent fix came out of this: `_canonical_list` in
`src/analyzer/canonical.py` now maps `None` to `[]`. For a list field null can only mean
"nothing here", and several models spell an empty list that way.

---

## 4. Verification performed

Every resume × JD × mode combination (3 × 3 × 2 = 18) planned against `qwen3.6:latest`,
asserting that each resume entity receives exactly one plan, every entry carries
`reasoning`, every `REWRITE` carries a `rewrite_strategy`, and `STRICT` emits no
`GENERATE`. **All 18 passed, on two separate full sweeps.** Three consecutive aggressive
runs were byte-identical. Nothing is written to disk. Full suite: 339 tests.

### Latency is not a stable number — plan against the slow end

The same 18 combinations, two runs:

| | Analysis | Per plan |
| ------------ | -------- | -------- |
| First sweep | 12–19s | 19–30s |
| Second sweep | 37–49s | 58–83s |

Near-identical code; the variable is the state of the Mac Studio (model resident in memory
or not, competing load). **At the slow end, analysis plus planning alone consumes 1.5–2
minutes of the three-minute end-to-end target**, leaving under a minute for generation,
LaTeX compilation and any revision pass. Either revisit the budget or ensure the model is
warm — do not design around the optimistic figure.

---

## 5. Reproducing a run

- `ConfigManager` reads `~/.resume-tailor/config.toml`. **`config/config.yaml` is inert** —
  nothing in `src/` reads it, and it was not valid YAML (a stray title line made it
  unparseable, and the `llm:` block was unindented). Retained because
  `docs/ARCHITECTURE.md:187` mandates the path and `max_revisions` is specified at
  `ARCHITECTURE.md:548`, but it now carries a header saying nothing reads it. **Editing its
  `llm` block does not change which model runs.**
- The model runs on a Mac Studio reached by SSH local forward:
  `ssh -N -L 11434:localhost:11434 ai-test@10.71.21.226`. `-N` produces no output after the
  password — expected, not a hang. Verify with `lsof -i :11434` and
  `curl localhost:11434/api/tags`. No `OLLAMA_HOST` change needed.
- `src/cli/plan.py` reads the JD with `.strip()`. See §1.3.

---

## 6. For the next task (Resume Generator)

### Day-one blockers

1. **You must mint IDs for generated entities.** `_validate_runtime_ids`
   (`src/validation/validator.py:604`) requires every entity to have a non-empty, unique
   ID — but a `GENERATE` plan entry deliberately carries `project_id: null` /
   `category_id: null`. The plan says "create this" and gives you no ID. Decide the minting
   scheme before writing generation code. (Spec risk 5, now concrete.)
2. **Set `source=EntitySource.GENERATED` on entities you create.** The field exists on all
   four entity models (`src/parser/models.py:51,67,89,109`) and defaults to `CANONICAL`, so
   fabricated content will otherwise silently claim to come from the original resume.
   `tests/validation/test_validator.py:182` already asserts generated projects are
   accepted — the machinery is waiting, currently unused anywhere in `src/`.

### Decide before building

3. **Generator temperature**, and its interaction with `max_revisions` — see §2.
4. **`priority` serialises as an int, not a name.** Verified: `.name` gives `MEDIUM`,
   `model_dump_json()` gives `3`. Fine internally and it re-parses correctly, but any
   consumer reading the JSON — or a human reading a log — sees `3`.
5. **Extract `src/cli/_common.py`.** The generator is the third copy of ~60 lines of
   provider bootstrap and error ladder (`analyze.py`, `plan.py`). This is the point where
   extraction pays, and it is the natural seam for the eventual one-shot command.
   (Spec risk 6.)

### Behaviours to handle that are legal but currently unexercised

6. **`REMOVE` on projects, and `skills_to_remove`.** qwen3.6 emitted zero skill removals
   across 18 combinations, but it *did* emit `REMOVE` on a project in an earlier run. Both
   paths are legal and nothing downstream consumes them yet.
7. **Strict mode's real constraint is yours to enforce.** `PlanningModeViolation` only
   catches `GENERATE` in strict mode — that is the sole structurally checkable rule. "No
   fabricated metrics, employers or responsibilities" is unenforceable at the plan layer;
   it propagates via the prompt's strict block and via `ResumePlan.mode`, which the
   generator must honour.
8. **The plan is never persisted.** Deliberate. The one-shot command will need to chain
   analyze → plan → generate in memory.

### Constraints carried forward

9. **Prompt schema field order** — see §1.2. Applies directly if the generator prompt asks
   for more than one entry shape.
10. **Do not parallelise one `ResumePlanner` instance.** `last_discarded` is instance state
    reset at the top of each `plan()` call: safe sequentially, racy if several resumes are
    planned concurrently. If the one-shot command ever fans out, return the discard list
    alongside the plan instead of hanging it off the instance.
11. **Bullet-level targeting does not exist.** Themes are free text, so the plan cannot say
    "rewrite highlight #2 of exp_001". If the generator needs it, add
    `highlight_indices: List[int]` with a bounds check — cheap now, expensive after prompt
    tuning. (Spec risk 4.)

---

## 7. Deferred, not rejected

- **The `canonical.py` foreign-key filter.** No longer needed for the observed bug, but
  still the right shape of defence if a model invents keys for reasons other than
  positional confusion.
- **Prompt-level defences for small models.** Two untried levers, both of which would also
  benefit qwen3.6: a worked few-shot example in the prompt (small models imitate examples
  far better than they follow rules — demonstrated twice here), and a single retry that
  feeds the validation error back. Neither is needed while qwen3.6 is the target.
- **`json_mode`** (spec risk 3) was never implicated. If a model ever returns a
  structurally valid but semantically empty plan — all `KEEP`, all `MEDIUM` — suspect
  `json_mode` before the prompt.
