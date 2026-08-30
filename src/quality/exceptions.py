"""
Quality Gate exceptions.

House style: one package base class, flat subclasses, docstring-only bodies.

The distinction these encode is the one the task doc insists on. A quality
*failure* means the resume was evaluated successfully and is not
submission-ready — that is a ``QualityGateResult`` with ``passed=False``, not an
exception. An *error* means the evaluation itself could not be performed, and
must never be reported as a pass: a gate that cannot read the PDF knows nothing
about the PDF, which is not the same as knowing the PDF is fine.
"""


class QualityGateError(Exception):
    """Base class for every Quality Gate error."""


class GeometryUnavailableError(QualityGateError):
    """
    The PDF geometry backend could not be loaded.

    Raised when ``pdfminer.six`` is not importable. Stage 2 cannot run, and the
    gate refuses to fall back to a Stage-1-only pass.
    """


class PDFUnreadableError(QualityGateError):
    """
    The PDF exists but could not be analysed.

    Covers a missing file, bytes that are not a PDF, a PDF with no pages, and
    any parse failure inside the geometry backend. Note the Compiler
    deliberately accepts a degenerate ``%PDF-`` file with no pages -- judging
    that document is this package's job, and the honest verdict is an error.
    """


class QualityAnalysisError(QualityGateError):
    """
    The evaluation inputs were self-inconsistent.

    Raised when the compiler log cannot be parsed for a page count, or when the
    log and the PDF disagree about how many pages there are. Silently picking
    one would make the metric untrustworthy in exactly the case where it
    matters.
    """
