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

    m = result.quality.metrics
    summary = [
        "# Live run\n",
        "- resume: `{0}`".format(resume_path),
        "- job description: `{0}`".format(jd_path),
        "- mode: **{0}**".format(mode.value),
        "- model: `{0}`".format(config.model),
        "- total wall clock: **{0:.1f}s**".format(elapsed),
        "- LLM calls: **{0}**  ({1})".format(
            len(provider.calls), ", ".join("{0:.0f}s".format(c["seconds"]) for c in provider.calls)),
        "\n## Quality verdict\n",
        "- passed: **{0}**".format(result.passed),
        "- pages: {0}".format(m.page_count),
        "- overfull hboxes: {0} (max {1}pt)".format(m.overfull_hbox_count, m.max_overfull_points),
        "- missing glyphs: {0}".format(m.missing_glyph_count),
        "- text overlaps: {0}".format(m.overlap_count),
        "- orphan words: {0}".format(m.orphan_word_count),
        "- rule collisions: {0}".format(m.rule_collision_count),
        "- total text lines: {0}".format(m.total_text_lines),
        "- overflow: {0} lines / {1:.1f}pt".format(m.overflow_line_count, m.overflow_height_points),
        "- overflowing sections: {0}".format(
            ", ".join(s.value for s in m.overflowing_sections) or "none"),
        "\n## Issues\n",
    ]
    for issue in result.quality.issues:
        summary.append("- `{0}` **{1}** — {2}".format(
            issue.severity.value, issue.code.value, issue.message))
    if not result.quality.issues:
        summary.append("- none")
    summary.append("\n## Soft failures (reported, never raised)\n")
    summary.append("- planner discarded: {0}".format(len(result.planner_discarded)))
    for note in result.planner_discarded:
        summary.append("  - {0}".format(note))
    summary.append("- generator discarded: {0}".format(len(result.generator_discarded)))
    for note in result.generator_discarded:
        summary.append("  - {0}".format(note))
    summary.append("- generator warnings: {0}".format(len(result.generator_warnings)))
    for warning in result.generator_warnings:
        summary.append("  - {0}: {1}".format(warning.code.value, warning.message))
    dump(out / "10_run_summary.md", "\n".join(summary) + "\n")

    print("\n=== {0} | pages={1} | passed={2} | {3:.1f}s ===".format(
        mode.value, m.page_count, result.passed, elapsed), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
