"""
One real end-to-end run: real provider, real LLM calls, real PDF.

Dumps every stage's output under output/runs/<name>/ so each hand-off can be
inspected on its own. Not a test — this is the actual flow.
"""
import json, sys, time
from pathlib import Path
from typing import Any, Dict, Optional

from src.analyzer.provider import LLMProvider
from src.config.credentials import CredentialManager
from src.config.manager import ConfigManager
from src.parser import ResumeParser
from src.pipeline import ResumePipeline
from src.planner.models import PlanningMode
from src.providers.factory import ProviderFactory
from src.report import (
    CHANGES_FILENAME,
    REPORT_FILENAME,
    REPORT_JSON_FILENAME,
    Reporter,
)


class TimingProvider(LLMProvider):
    """Wraps the real provider and records what each call cost."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.calls = []

    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        started = time.time()
        reply = self._inner.generate(prompt, options)
        self.calls.append({
            "index": len(self.calls) + 1,
            "seconds": round(time.time() - started, 1),
            "prompt_chars": len(prompt),
            "reply_chars": len(reply),
        })
        print("  call {0}: {1:.1f}s  prompt={2}  reply={3}".format(
            self.calls[-1]["index"], self.calls[-1]["seconds"],
            len(prompt), len(reply)), flush=True)
        return reply


def dump(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print("  wrote {0} ({1} bytes)".format(path.name, len(text.encode())), flush=True)


def main() -> int:
    resume_path = sys.argv[1] if len(sys.argv) > 1 else "content/backend_resume.md"
    jd_path = sys.argv[2] if len(sys.argv) > 2 else "tests/fixtures/job_descriptions/backend.md"
    mode = PlanningMode.parse(sys.argv[3] if len(sys.argv) > 3 else "STRICT")
    # Keyed on resume *and* mode: keying on mode alone makes two pairings
    # clobber each other's artifacts, which is the whole point of keeping them.
    out = Path("output/runs") / "{0}_{1}".format(
        Path(resume_path).stem.replace("_resume", ""), mode.value.lower())
    out.mkdir(parents=True, exist_ok=True)

    config = ConfigManager().load()
    provider = TimingProvider(ProviderFactory.create(config, CredentialManager()))
    resume = ResumeParser().parse(resume_path)
    jd = Path(jd_path).read_text(encoding="utf-8")

    print("resume={0}\njd={1}\nmode={2}\nmodel={3}\nout={4}\n".format(
        resume_path, jd_path, mode.value, config.model, out), flush=True)

    dump(out / "00_source_resume.json", resume.model_dump_json(indent=2))
    dump(out / "01_job_description.md", jd)

    started = time.time()
    result = ResumePipeline(provider).run(
        source_resume=resume, job_description=jd, mode=mode,
        output_directory=str(out), job_name="resume",
    )
    elapsed = time.time() - started

    dump(out / "02_job_analysis.json", result.job_analysis.model_dump_json(indent=2))
    dump(out / "03_resume_plan.json", result.resume_plan.model_dump_json(indent=2))
    dump(out / "04_generated_resume.json", result.generated_resume.model_dump_json(indent=2))
    dump(out / "09_quality_report.json", result.quality.model_dump_json(indent=2))
    # the pipeline itself wrote generated.md; the compiler wrote resume.{tex,pdf,log}
    for old, new in (("generated.md", "05_generated.md"), ("resume.tex", "06_resume.tex"),
                     ("resume.pdf", "07_resume.pdf"), ("resume.log", "08_resume.log")):
        src = out / old
        if src.exists():
            src.replace(out / new)
            print("  renamed {0} -> {1}".format(old, new), flush=True)

    # The pipeline's own compile ran *before* revision, so 07_resume.pdf is the
    # pre-revision artifact. Dump what was actually delivered alongside it.
    dump(out / "11_final_resume.json", result.final_resume.model_dump_json(indent=2))
    final = out / "final"
    for name, new_name in (("resume.tex", "12_final.tex"), ("resume.pdf", "13_final.pdf")):
        src = final / name
        if src.exists():
            (out / new_name).write_bytes(src.read_bytes())
            print("  copied final/{0} -> {1}".format(name, new_name), flush=True)

    m = result.quality.metrics

    # The Reporter owns the run's narrative. This script keeps only what a
    # report must never carry: wall clock, model name and per-call timings are
    # non-deterministic, and a report has to satisfy first == second.
    reporter = Reporter()
    report = reporter.build(result)
    reporter.write(report, str(out))
    for old_name, new_name in (
        (REPORT_FILENAME, "14_report.md"),
        (CHANGES_FILENAME, "15_changes.md"),
        (REPORT_JSON_FILENAME, "16_report.json"),
    ):
        (out / old_name).replace(out / new_name)
        print("  wrote {0}".format(new_name), flush=True)

    dump(out / "10_run_provenance.md", "\n".join([
        "# Live run provenance\n",
        "- resume: `{0}`".format(resume_path),
        "- job description: `{0}`".format(jd_path),
        "- mode: **{0}**".format(mode.value),
        "- model: `{0}`".format(config.model),
        "- total wall clock: **{0:.1f}s**".format(elapsed),
        "- LLM calls: **{0}**  ({1})".format(
            len(provider.calls),
            ", ".join("{0:.0f}s".format(c["seconds"]) for c in provider.calls)),
        "",
        "The run itself is described in `14_report.md`, `15_changes.md` and",
        "`16_report.json`, all produced by the Reporter.",
    ]) + "\n")

    print("\n=== {0} | pages={1} | passed={2} | {3:.1f}s ===".format(
        mode.value, m.page_count, result.passed, elapsed), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
