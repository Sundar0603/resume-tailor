"""
Live determinism check for the Job Description Analyzer.

Runs the real configured provider against one job description N times and
reports how much the resulting JobAnalysis objects differ from each other.
Unlike test_determinism.py, this talks to the network (or to a local Ollama)
and is therefore a script rather than a pytest module — pytest only collects
``test_*.py``, so this file is never picked up by the suite.

Usage::

    python tests/analyzer/verify_determinism.py --jd path/to/jd.md
    python tests/analyzer/verify_determinism.py --jd path/to/jd.md --iterations 10

Scoring:

    list fields    Jaccard index over the case-folded entries
    scalar fields  difflib ratio, with None == None scoring 1.0

Every iteration is compared against the first. The run passes when no field
scores below ``--min-field`` and the mean across all fields is at least
``--min-mean``. Exit code is 0 on pass, 1 on drift, 2 on setup failure.
"""

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.analyzer import JDAnalyzer, JobAnalysis, LLMProvider  # noqa: E402
from src.analyzer.canonical import (  # noqa: E402
    PROSE_FIELDS,
    SCALAR_FIELDS,
    SET_LIKE_FIELDS,
    canonical_text,
)
from src.config.credentials import CredentialManager  # noqa: E402
from src.config.manager import ConfigManager  # noqa: E402
from src.providers.factory import ProviderFactory  # noqa: E402

LIST_FIELDS = SET_LIKE_FIELDS + PROSE_FIELDS
ALL_FIELDS = SCALAR_FIELDS + LIST_FIELDS

DEFAULT_ITERATIONS = 5
DEFAULT_MIN_FIELD = 0.90
DEFAULT_MIN_MEAN = 0.95
DEFAULT_RESPONSE_DIR = (
    _REPO_ROOT / "tests" / "fixtures" / "job_descriptions" / "model_based_responses"
)


# ---------------------------------------------------------------------------
# Provider wrapper
# ---------------------------------------------------------------------------


class RecordingProvider(LLMProvider):
    """Delegates to a real provider while keeping each raw response."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.responses: List[str] = []

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        response = self._inner.generate(prompt, options=options)
        self.responses.append(response)
        return response


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    """Return the Jaccard index of two case-insensitive collections."""
    left_set = {item.casefold() for item in left}
    right_set = {item.casefold() for item in right}

    if not left_set and not right_set:
        return 1.0

    union = left_set | right_set
    return len(left_set & right_set) / len(union)


def text_ratio(left: Optional[str], right: Optional[str]) -> float:
    """Return the similarity of two optional strings."""
    left_text = canonical_text(left)
    right_text = canonical_text(right)

    if left_text is None and right_text is None:
        return 1.0
    if left_text is None or right_text is None:
        return 0.0
    if left_text == right_text:
        return 1.0

    return SequenceMatcher(None, left_text.casefold(), right_text.casefold()).ratio()


def field_score(field: str, baseline: JobAnalysis, other: JobAnalysis) -> float:
    """Score one field of *other* against *baseline*."""
    left = getattr(baseline, field)
    right = getattr(other, field)

    if field in LIST_FIELDS:
        return jaccard(left, right)
    return text_ratio(left, right)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def report(analyses: List[JobAnalysis], min_field: float, min_mean: float) -> bool:
    """Print the per-field table and return True when the run is stable."""
    baseline = analyses[0]
    others = analyses[1:]

    scores: Dict[str, List[float]] = {
        field: [field_score(field, baseline, other) for other in others]
        for field in ALL_FIELDS
    }

    identical = sum(1 for other in others if other == baseline)

    print()
    print(f"{'field':<20}{'min':>8}{'mean':>8}   detail")
    print("-" * 70)

    all_values: List[float] = []
    worst_fields: List[str] = []

    for field in ALL_FIELDS:
        values = scores[field] or [1.0]
        all_values.extend(values)
        minimum = min(values)
        mean = sum(values) / len(values)

        detail = ""
        if minimum < 1.0:
            detail = _describe_drift(field, baseline, others)
            worst_fields.append(field)

        print(f"{field:<20}{_fmt(minimum):>8}{_fmt(mean):>8}   {detail}")

    overall_mean = sum(all_values) / len(all_values) if all_values else 1.0
    overall_min = min(all_values) if all_values else 1.0

    print("-" * 70)
    print(f"{'OVERALL':<20}{_fmt(overall_min):>8}{_fmt(overall_mean):>8}")
    print()
    print(
        f"identical to iteration 1: {identical}/{len(others)} "
        f"(byte-for-byte equal JobAnalysis objects)"
    )

    stable = overall_min >= min_field and overall_mean >= min_mean

    if stable and identical == len(others):
        print("VERDICT: deterministic — every iteration returned the same analysis")
    elif stable:
        print(
            f"VERDICT: stable — all fields >= {min_field:.2f}, "
            f"mean {overall_mean:.2f} >= {min_mean:.2f}"
        )
    else:
        print(
            f"VERDICT: DRIFT — required all fields >= {min_field:.2f} "
            f"and mean >= {min_mean:.2f}"
        )
        print(f"         unstable fields: {', '.join(worst_fields) or 'none'}")

    return stable


def _describe_drift(
    field: str, baseline: JobAnalysis, others: List[JobAnalysis]
) -> str:
    """Summarise how a field varied across iterations."""
    if field not in LIST_FIELDS:
        values = {canonical_text(getattr(other, field)) for other in others}
        values.discard(canonical_text(getattr(baseline, field)))
        return "also saw: " + ", ".join(repr(value) for value in sorted(map(str, values)))

    base_set = {item.casefold() for item in getattr(baseline, field)}
    added, dropped = set(), set()

    for other in others:
        other_set = {item.casefold() for item in getattr(other, field)}
        added |= other_set - base_set
        dropped |= base_set - other_set

    parts = []
    if added:
        parts.append("+" + ", ".join(sorted(added)))
    if dropped:
        parts.append("-" + ", ".join(sorted(dropped)))
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_artifacts(
    directory: Path,
    jd_name: str,
    raw_responses: List[str],
    analyses: List[JobAnalysis],
) -> Path:
    """Write raw responses and parsed analyses for later inspection."""
    target = directory / jd_name
    target.mkdir(parents=True, exist_ok=True)

    for index, raw in enumerate(raw_responses, start=1):
        (target / f"run-{index}.raw.txt").write_text(raw, encoding="utf-8")

    for index, analysis in enumerate(analyses, start=1):
        (target / f"run-{index}.json").write_text(
            json.dumps(analysis.model_dump(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    return target


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the analyzer N times on one job description and "
        "report how much the results drift."
    )
    parser.add_argument(
        "--jd",
        required=True,
        type=Path,
        help="Path to the job description file.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Number of analyses to run (default: {DEFAULT_ITERATIONS}).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Override the configuration file path.",
    )
    parser.add_argument(
        "--min-field",
        type=float,
        default=DEFAULT_MIN_FIELD,
        help=f"Lowest acceptable per-field score (default: {DEFAULT_MIN_FIELD}).",
    )
    parser.add_argument(
        "--min-mean",
        type=float,
        default=DEFAULT_MIN_MEAN,
        help=f"Lowest acceptable mean score (default: {DEFAULT_MIN_MEAN}).",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write raw responses to disk.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if not args.jd.is_file():
        print(f"Job description not found: {args.jd}")
        return 2
    if args.iterations < 2:
        print("At least 2 iterations are needed to measure drift.")
        return 2

    job_description = args.jd.read_text(encoding="utf-8").strip()
    if not job_description:
        print(f"Job description is empty: {args.jd}")
        return 2

    config_manager = ConfigManager(config_path=args.config)
    if not config_manager.exists():
        print("No AI provider is configured. Run `resume-tailor doctor` first.")
        return 2

    try:
        config = config_manager.load()
        provider = ProviderFactory.create(config, CredentialManager())
    except Exception as exc:  # noqa: BLE001 — surface any setup failure verbatim
        print(f"Could not construct the provider: {exc}")
        return 2

    recorder = RecordingProvider(provider)
    analyzer = JDAnalyzer(provider=recorder)

    print(f"job description : {args.jd}")
    print(f"provider        : {config.provider.value}")
    print(f"model           : {config.model}")
    print(f"iterations      : {args.iterations}")
    print()

    analyses: List[JobAnalysis] = []
    for iteration in range(1, args.iterations + 1):
        print(f"  run {iteration}/{args.iterations} ...", end="", flush=True)
        try:
            analyses.append(analyzer.analyze(job_description))
        except Exception as exc:  # noqa: BLE001 — a failed run is a result too
            print(f" FAILED: {type(exc).__name__}: {exc}")
            return 1
        print(" ok")

    if not args.no_save:
        target = save_artifacts(
            DEFAULT_RESPONSE_DIR / config.model,
            args.jd.stem,
            recorder.responses,
            analyses,
        )
        print(f"\nresponses written to {target}")

    return 0 if report(analyses, args.min_field, args.min_mean) else 1


if __name__ == "__main__":
    raise SystemExit(main())
