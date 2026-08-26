"""
Shared fakes for the compiler tests.

Plain factory functions and hand-written fakes, matching the renderer and
generator suites. The compiler takes a ``runner`` callable precisely so these
tests can drive every branch without ``unittest.mock``.
"""

import subprocess
import sys
from pathlib import Path

# The task's minimal document. Deliberately not a real resume: the compiler
# knows nothing about resumes and its tests should not either.
MINIMAL_DOCUMENT = (
    "\\documentclass{article}\n"
    "\n"
    "\\begin{document}\n"
    "\n"
    "Resume Tailor PDF Compiler Test\n"
    "\n"
    "\\end{document}\n"
)

BROKEN_DOCUMENT = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\undefinedcommand\n"
    "\\end{document}\n"
)

# Smallest thing that passes the magic-byte check.
VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

# An engine that is guaranteed to exist and be executable, so unit tests can
# reach the runner without a TeX distribution installed.
RESOLVABLE_ENGINE = sys.executable


class FakeRunner:
    """
    Stands in for the subprocess call, and records how it was invoked.

    Writes whatever artifacts it is told to into the workspace, so the
    compiler's own checks run against real files.
    """

    def __init__(
        self,
        exit_code=0,
        write_pdf=True,
        write_log=True,
        pdf_bytes=VALID_PDF_BYTES,
        log_text="fake engine log\n",
        stdout="fake captured stdout\n",
    ):
        self.exit_code = exit_code
        self.write_pdf = write_pdf
        self.write_log = write_log
        self.pdf_bytes = pdf_bytes
        self.log_text = log_text
        self.stdout = stdout
        self.calls = []

    def __call__(self, argv, cwd, timeout, env):
        self.calls.append(
            {
                "argv": list(argv),
                "cwd": cwd,
                "timeout": timeout,
                "env": dict(env),
            }
        )
        workspace = Path(cwd)
        job_name = Path(argv[-1]).stem
        if self.write_log:
            (workspace / (job_name + ".log")).write_text(self.log_text, encoding="utf-8")
        if self.write_pdf:
            (workspace / (job_name + ".pdf")).write_bytes(self.pdf_bytes)
        return self.exit_code, self.stdout

    @property
    def call(self):
        """The single call, for the common case."""
        assert len(self.calls) == 1
        return self.calls[0]


class TimeoutRunner:
    """Raises the timeout the real subprocess call would raise."""

    def __init__(self, output=b"partial output before the kill\n", write_log=False):
        self.output = output
        self.write_log = write_log
        self.calls = []

    def __call__(self, argv, cwd, timeout, env):
        self.calls.append({"argv": list(argv), "cwd": cwd, "timeout": timeout})
        if self.write_log:
            job_name = Path(argv[-1]).stem
            (Path(cwd) / (job_name + ".log")).write_text("partial log\n", encoding="utf-8")
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout, output=self.output)


class WorkspaceProbe:
    """Records the workspace path so a test can assert it was cleaned up."""

    def __init__(self):
        self.workspaces = []

    def __call__(self, argv, cwd, timeout, env):
        self.workspaces.append(cwd)
        workspace = Path(cwd)
        job_name = Path(argv[-1]).stem
        (workspace / (job_name + ".log")).write_text("log\n", encoding="utf-8")
        (workspace / (job_name + ".pdf")).write_bytes(VALID_PDF_BYTES)
        (workspace / (job_name + ".aux")).write_text("aux\n", encoding="utf-8")
        return 0, "out"
