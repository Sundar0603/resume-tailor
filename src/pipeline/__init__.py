"""
Pipeline package.

Connects every stage into one runnable chain: analyze, plan, generate,
serialize, render, compile, judge. It adds no behaviour of its own — each stage
is tested in isolation, and this package exists so the *chain* is tested too.
"""

from .exceptions import PipelineError, PipelineStageError
from .models import PipelineResult
from .pipeline import (
    DEFAULT_JOB_NAME,
    DEFAULT_OUTPUT_DIRECTORY,
    MARKDOWN_FILENAME,
    ResumePipeline,
)

__all__ = [
    "ResumePipeline",
    "PipelineResult",
    "DEFAULT_OUTPUT_DIRECTORY",
    "DEFAULT_JOB_NAME",
    "MARKDOWN_FILENAME",
    "PipelineError",
    "PipelineStageError",
]
