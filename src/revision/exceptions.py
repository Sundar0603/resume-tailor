"""
Exceptions raised by the Revision / Shortening Engine.

Mirrors the analyzer, planner, generator and compiler trees: one package base
class and a shallow set of subclasses, docstring-only bodies.

One deliberate divergence, for the same reason the compiler diverged:
:class:`OnePageInfeasibleError` carries the measured shortfall and the last
artifact paths as attributes. The engine raises rather than returning when it
cannot converge, so there is no result object for the diagnostics to travel on,
and "how far over was it, and where is the PDF that proves it" is exactly what
the caller needs to decide whether the floors or the source resume are at
fault.
"""

from typing import List, Optional


class RevisionError(Exception):
    """Base class for every Revision Engine failure."""


class OnePageInfeasibleError(RevisionError):
    """
    The one-page target cannot be reached under the retention floors.

    Raised once every legal deterministic removal is exhausted and either no
    eligible bullet remains for compression or the compression budget is spent.
    The engine never breaches a floor to avoid this: an explicit failure is
    preferable to silently shipping a resume with a two-bullet internship.

    Attributes
    ----------
    spill : int
        Lines still on page two when the engine gave up.
    steps_taken : int
        How many removals and compressions were applied before giving up.
    pdf_path : str or None
        The last PDF produced, preserved for inspection.
    trail_path : str or None
        The persisted ``revision_trail.json``.
    """

    def __init__(
        self,
        message: str,
        spill: int = 0,
        steps_taken: int = 0,
        pdf_path: Optional[str] = None,
        trail_path: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.spill = spill
        self.steps_taken = steps_taken
        self.pdf_path = pdf_path
        self.trail_path = trail_path


class InvalidCompressionResponse(RevisionError):
    """
    The model's compression reply could not be used at all.

    Raised for a structurally unusable reply — empty, or missing the
    ``compressions`` array. A reply whose *individual* entries fail
    verification is not an error: those entries are rejected and the original
    bullets are kept, which is the designed fallback.
    """


class InvalidCompressionJSON(RevisionError):
    """The compression reply was not parseable as JSON."""


class RevisionStateError(RevisionError):
    """
    The engine was asked to operate on a resume it cannot reason about.

    Raised when a stated invariant does not hold — most importantly the
    absence of an internship, which the removal order depends on. Failing
    loudly here is deliberate: silently mis-ordering the experience trim
    would be far harder to notice.

    Attributes
    ----------
    reasons : list of str
        Every violated invariant, so one call reports all of them.
    """

    def __init__(self, message: str, reasons: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.reasons = list(reasons or [])
