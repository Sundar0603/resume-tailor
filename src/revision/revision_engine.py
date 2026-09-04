r"""
The Revision / Shortening Engine — the loop that makes a resume fit one page.

Position in the chain::

    Resume -> Renderer -> Compiler -> Quality Gate -> [ RevisionEngine ] -> done

It owns the complete shortening policy: deletion ordering, retention floors,
shortfall calculation, bullet selection for compression, protected-fact
extraction and verification, re-rendering, recompiling, re-judging, and knowing
when to stop. No other component deletes content.

**Deterministic deletion is always exhausted first.** Only when no legal removal
remains and the page still overflows may the engine make a single consolidated
LLM call to compress selected two-line bullets. The model never decides what to
delete, what matters, or which bullets to touch.

**It works on ``Resume`` objects, never on ``resume.tex``.** Every attempt goes
Resume -> Renderer -> LaTeX, so entity ids and ``EntitySource`` lineage survive
and the frozen template is never hand-edited.

Two loop bounds, and they are different on purpose:

- Deterministic iterations are **uncapped**. Every step strictly reduces the
  resume, so the loop provably terminates, and at roughly half a second per
  compile a full convergence costs a couple of seconds.
  :data:`MAX_DETERMINISTIC_STEPS` is a guard against a policy bug, not a budget.
- Compression passes are capped at :data:`MAX_COMPRESSION_PASSES`, matching
  ``ARCHITECTURE.md``'s ``max_revisions: 3``, because each one is an LLM call
  against a 180-second run budget.

**Failure is explicit.** If the one-page target cannot be reached without
breaching a retention floor, the engine raises
:class:`~src.revision.exceptions.OnePageInfeasibleError`. It never returns the
original failing resume as a success, and it never quietly breaches a floor.
"""

import json
import shutil
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from src.analyzer.provider import LLMProvider
from src.compiler.pdf_compiler import PDFCompiler
from src.parser.models import Resume
from src.quality.models import QualityGateResult
from src.quality.quality_gate import QualityGate
from src.renderer.latex_renderer import LatexRenderer

from . import compression, deletion, floors
from .exceptions import OnePageInfeasibleError, RevisionStateError
from .measure import shortfall as compute_shortfall
from .models import (
    CompressionOutcome,
    RemovalStep,
    RevisionAction,
    RevisionReason,
    RevisionResult,
    RevisionStep,
)
from .prompts import build_compression_prompt
from .sampling import compression_options

#: Where a run's artifacts land when the caller does not say.
DEFAULT_OUTPUT_DIRECTORY = "output/runs"

#: Base name for the LaTeX, PDF and log artifacts of every attempt.
DEFAULT_JOB_NAME = "resume"

#: Subdirectory every intermediate attempt compiles into, overwritten each
#: time. Eight intermediate PDFs nobody opens are clutter; the trail is what
#: gets read, so only checkpoints get their own directory.
WORK_DIRECTORY = "work"

#: Where the accepted resume ends up.
FINAL_DIRECTORY = "final"

#: The persisted trail.
TRAIL_FILENAME = "revision_trail.json"

#: Consolidated LLM compression passes allowed per revision.
MAX_COMPRESSION_PASSES = 3

#: Guard against a deletion policy that fails to shrink the resume. A real
#: exhaustion run is well under sixty steps.
MAX_DETERMINISTIC_STEPS = 500


def _guard_invariants(resume: Resume) -> None:
    """
    Raise unless the resume is a shape the removal policy can reason about.

    Called before anything is rendered or compiled, so a resume the engine was
    never designed for costs nothing and fails with a reason rather than a
    quietly mis-ordered trim.
    """
    reasons = floors.check_invariants(resume)
    if reasons:
        raise RevisionStateError(
            "the resume does not satisfy the Revision Engine's stated "
            "invariants: {0}".format("; ".join(reasons)),
            reasons=reasons,
        )


def _unchanged(resume: Resume, quality: QualityGateResult) -> RevisionResult:
    """Return the result for a resume that already passes: nothing to do."""
    return RevisionResult(
        resume=resume.model_copy(deep=True),
        quality=quality,
        revised=False,
        attempts=0,
        deterministic_steps=0,
        compression_passes=0,
        llm_calls=0,
    )


def _give_up(run: "_Run", quality: QualityGateResult) -> None:
    """
    Raise :class:`OnePageInfeasibleError`, preserving the evidence first.

    The last attempt's artifacts are checkpointed before the exception, for the
    same reason the compiler writes its log before raising: the workspace is
    the only proof of what went wrong, and it is about to be overwritten.
    """
    if run.attempts:
        run.checkpoint(run.attempts)
    raise OnePageInfeasibleError(
        "one page is unreachable without breaching a retention floor: "
        "{0} lines still overflow after {1} attempts".format(
            quality.metrics.overflow_line_count, run.attempts
        ),
        spill=quality.metrics.overflow_line_count,
        steps_taken=len(run.trail),
        pdf_path=run.last_pdf_path,
        trail_path=str(run.trail_path),
    )


class RevisionEngine:
    """
    Shortens a resume that failed the Quality Gate until it passes.

    Stateless between calls. Every collaborator is injectable, matching
    :class:`~src.pipeline.pipeline.ResumePipeline` — tests substitute a gate
    and a compiler that need no TeX distribution, and a caller can tune the
    compile timeout or the gate's tolerances.
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        template_directory: str = "templates",
        renderer: Optional[LatexRenderer] = None,
        compiler: Optional[PDFCompiler] = None,
        quality_gate: Optional[QualityGate] = None,
        max_compression_passes: int = MAX_COMPRESSION_PASSES,
    ) -> None:
        """
        Parameters
        ----------
        provider
            Used only for bullet compression. ``None`` disables that path
            entirely, leaving a fully deterministic, offline engine that raises
            rather than calling out.
        """
        self._provider = provider
        self._renderer = (
            renderer
            if renderer is not None
            else LatexRenderer(template_directory=template_directory)
        )
        self._compiler = compiler if compiler is not None else PDFCompiler()
        self._gate = quality_gate if quality_gate is not None else QualityGate()
        self._max_compression_passes = max_compression_passes

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def revise(
        self,
        *,
        source_resume: Resume,
        current_resume: Resume,
        quality_result: QualityGateResult,
        output_directory: str = DEFAULT_OUTPUT_DIRECTORY,
        job_name: str = DEFAULT_JOB_NAME,
    ) -> RevisionResult:
        """
        Shorten ``current_resume`` until it clears the Quality Gate.

        Parameters
        ----------
        source_resume
            The resume the run started from. Never modified, and never read for
            content — it is here so the result can be validated against it.
        current_resume
            The latest generated or revised resume. Operated on as a deep copy.
        quality_result
            Why the current resume failed. A passing result returns it
            unchanged, per the task specification.
        output_directory
            Root for this run's artifacts. The engine owns attempt numbering
            beneath it; the compiler owns only the job name.

        Raises
        ------
        RevisionStateError
            A stated invariant does not hold — most importantly, no internship.
        OnePageInfeasibleError
            One page is unreachable without breaching a retention floor.
        """
        _guard_invariants(current_resume)
        if quality_result.passed:
            return _unchanged(current_resume, quality_result)

        run = _Run(Path(output_directory), job_name, source_resume, quality_result)
        working = current_resume.model_copy(deep=True)

        working, quality = self._delete_until_fit(working, run)
        if not quality.passed:
            working, quality = self._compress_until_fit(working, quality, run)

        run.write_trail()
        if not quality.passed:
            _give_up(run, quality)

        run.promote_to_final()
        return run.result(working, quality)

    # ------------------------------------------------------------------
    # Phase 1 — deterministic deletion
    # ------------------------------------------------------------------

    def _delete_until_fit(
        self, working: Resume, run: "_Run"
    ) -> Tuple[Resume, QualityGateResult]:
        """
        Remove content in the authoritative order until the page fits.

        Returns as soon as the Quality Gate passes, or when no legal removal
        remains. The verdict is always the compiled one — the line estimates in
        :mod:`src.revision.measure` size the work, they never decide it.
        """
        quality = run.quality
        for _ in range(MAX_DETERMINISTIC_STEPS):
            step = deletion.next_removal(working)
            if step is None:
                return working, quality
            working = deletion.apply_removal(working, step)
            run.deterministic_steps += 1
            entry = _entry_for(step, run.attempts + 1)
            quality = self._attempt(working, run, entry)
            if quality.passed:
                return working, quality

        raise RuntimeError(
            "deterministic deletion did not terminate; the policy is not shrinking"
        )

    # ------------------------------------------------------------------
    # Phase 2 — consolidated LLM compression
    # ------------------------------------------------------------------

    def _compress_until_fit(
        self, working: Resume, quality: QualityGateResult, run: "_Run"
    ) -> Tuple[Resume, QualityGateResult]:
        """
        Shorten selected two-line bullets, one consolidated call per pass.

        Deterministic deletion is exhausted by the time this runs, so nothing
        is freeable and the shortfall is the whole remaining spill. The
        arithmetic is still computed through :func:`measure.shortfall` and
        recorded, because it is what says the LLM path is warranted at all.
        """
        if self._provider is None:
            return working, quality

        for _ in range(self._max_compression_passes):
            spill = quality.metrics.overflow_line_count
            gap = compute_shortfall(spill, deletion.freeable_lines(working))
            candidates = compression.select_candidates(working, gap)
            if not candidates:
                return working, quality

            raw = self._provider.generate(
                build_compression_prompt(candidates), compression_options()
            )
            run.llm_calls += 1
            outcomes = compression.evaluate_response(raw, candidates)
            run.outcomes.extend(outcomes)
            if not any(o.accepted for o in outcomes):
                return working, quality

            working = compression.apply_compressions(working, candidates, outcomes)
            run.compression_passes += 1
            quality = self._attempt(working, run, _compression_entry(run, outcomes, gap))
            if quality.passed:
                return working, quality

        return working, quality

    # ------------------------------------------------------------------
    # One render -> compile -> judge cycle
    # ------------------------------------------------------------------

    def _attempt(
        self, working: Resume, run: "_Run", entry: RevisionStep
    ) -> QualityGateResult:
        """
        Render, compile and judge one candidate resume; record the outcome.

        A ``CompilationFailedError`` is deliberately **not** caught. Overflow is
        the failure this engine handles; a resume that stops compiling means a
        removal broke the document, which is a defect and must surface with its
        log path rather than be absorbed as "still too long".
        """
        latex = self._renderer.render(working)
        compilation = self._compiler.compile(
            latex, output_directory=str(run.work_directory), job_name=run.job_name
        )
        quality = self._gate.evaluate(
            compilation.pdf_path, compilation.tex_path, compilation
        )

        run.attempts += 1
        run.quality = quality
        run.gate_results.append(quality)
        run.last_pdf_path = compilation.pdf_path
        run.last_tex_path = compilation.tex_path
        entry.page_count = quality.metrics.page_count
        entry.spill = quality.metrics.overflow_line_count
        entry.passed = quality.passed
        run.trail.append(entry)

        if quality.passed or entry.action is RevisionAction.COMPRESS_BULLETS:
            run.checkpoint(entry.attempt)
        return quality


# ----------------------------------------------------------------------
# Trail entries
# ----------------------------------------------------------------------


def _entry_for(step: RemovalStep, attempt: int) -> RevisionStep:
    """Return the trail entry for one deterministic removal."""
    return RevisionStep(
        attempt=attempt,
        action=step.action,
        reason=step.reason,
        entity_id=step.entity_id,
        entity_kind=step.entity_kind,
        detail=step.detail or None,
    )


def _compression_entry(
    run: "_Run", outcomes: Sequence[CompressionOutcome], gap: int
) -> RevisionStep:
    """Return the trail entry for one consolidated compression pass."""
    return RevisionStep(
        attempt=run.attempts + 1,
        action=RevisionAction.COMPRESS_BULLETS,
        reason=RevisionReason.SHORTFALL_REMAINS,
        bullet_ids=[o.bullet_id for o in outcomes if o.accepted],
        shortfall_before=gap,
        detail="{0} of {1} compressions accepted".format(
            sum(1 for o in outcomes if o.accepted), len(outcomes)
        ),
    )


# ----------------------------------------------------------------------
# Run state and artifacts
# ----------------------------------------------------------------------


class _Run:
    """
    Mutable bookkeeping for one revision, and the owner of its artifacts.

    Layout::

        <output_directory>/
            work/                  every attempt compiles here, overwritten
            attempt_<n>/           checkpoints only
            final/                 the accepted resume
            revision_trail.json    every step, including non-checkpoints
    """

    def __init__(
        self,
        root: Path,
        job_name: str,
        source_resume: Resume,
        quality: QualityGateResult,
    ) -> None:
        self.root = root
        self.job_name = job_name
        self.source_resume = source_resume
        self.attempts = 0
        self.deterministic_steps = 0
        self.compression_passes = 0
        self.llm_calls = 0
        self.trail = []  # type: List[RevisionStep]
        self.outcomes = []  # type: List[CompressionOutcome]
        #: The latest verdict. Seeded with the one that caused this revision,
        #: so a run where no legal removal exists still has a result to report.
        self.quality = quality
        #: Every attempt's verdict, in order, for the Reporter's gate history.
        #: The seed above is *not* included: it belongs to the pipeline's own
        #: pre-revision compile, and the pipeline reports it separately.
        self.gate_results = []  # type: List[QualityGateResult]
        self.last_pdf_path = None  # type: Optional[str]
        self.last_tex_path = None  # type: Optional[str]

    @property
    def work_directory(self) -> Path:
        """Return the scratch directory every attempt compiles into."""
        return self.root / WORK_DIRECTORY

    @property
    def trail_path(self) -> Path:
        """Return the path the trail is persisted to."""
        return self.root / TRAIL_FILENAME

    def checkpoint(self, attempt: int) -> None:
        """Copy the current attempt's artifacts into their own directory."""
        self._copy_artifacts(self.root / "attempt_{0}".format(attempt))

    def promote_to_final(self) -> None:
        """Copy the accepted attempt's artifacts into ``final/``."""
        self._copy_artifacts(self.root / FINAL_DIRECTORY)

    def _copy_artifacts(self, destination: Path) -> None:
        """Copy every artifact the last attempt produced into ``destination``."""
        destination.mkdir(parents=True, exist_ok=True)
        for suffix in (".tex", ".pdf", ".log"):
            produced = self.work_directory / "{0}{1}".format(self.job_name, suffix)
            if produced.is_file():
                shutil.copy2(str(produced), str(destination / produced.name))

    def write_trail(self) -> None:
        """Persist every step taken, including the ones without a checkpoint."""
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "attempts": self.attempts,
            "deterministic_steps": self.deterministic_steps,
            "compression_passes": self.compression_passes,
            "llm_calls": self.llm_calls,
            "steps": [json.loads(step.model_dump_json()) for step in self.trail],
            "compression_outcomes": [
                json.loads(o.model_dump_json()) for o in self.outcomes
            ],
        }
        self.trail_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def result(self, resume: Resume, quality: QualityGateResult) -> RevisionResult:
        """Assemble the result object for a converged run."""
        return RevisionResult(
            resume=resume,
            quality=quality,
            revised=True,
            attempts=self.attempts,
            deterministic_steps=self.deterministic_steps,
            compression_passes=self.compression_passes,
            llm_calls=self.llm_calls,
            trail=list(self.trail),
            compression_outcomes=list(self.outcomes),
            gate_results=list(self.gate_results),
            pdf_path=str(self.root / FINAL_DIRECTORY / "{0}.pdf".format(self.job_name)),
            tex_path=str(self.root / FINAL_DIRECTORY / "{0}.tex".format(self.job_name)),
            trail_path=str(self.trail_path),
        )
