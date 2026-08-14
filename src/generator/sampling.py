"""
Sampling parameters for the Resume Generator.

Unlike the Analyzer and the Planner, the Generator is deliberately **not**
deterministic. Those two produce decisions, where the same input must yield the
same output. The Generator produces prose, and greedy decoding produces flat,
repetitive prose — every bullet reaching for the same handful of verbs.

Three knobs move together here, and moving only one is a common mistake:

``temperature``
    Raised above zero to reintroduce variation.
``top_k`` / ``top_p``
    Widened. ``DETERMINISTIC_OPTIONS`` pins ``top_k = 1``, which means only the
    single highest-probability token is ever eligible. Raising the temperature
    while ``top_k`` stays at 1 changes nothing at all — there is never more
    than one candidate for the temperature to choose between.
``seed``
    Kept fixed at the deterministic value. A stable seed means a given
    temperature still reproduces run to run, which keeps failures debuggable
    without costing any prose quality.

``num_ctx`` is widened because a generation prompt carries the resume, the job
analysis and the relevant slice of the plan. ``max_tokens`` stays at the
default: each call returns one section, not a whole resume.
"""

from typing import Any, Dict

from ..analyzer.sampling import deterministic_options

#: Context window for generation prompts, in tokens. Larger than the analyzer's
#: because the prompt carries resume, job analysis and plan together.
GENERATOR_NUM_CTX = 16384

#: Response budget for a single section, in tokens.
GENERATOR_MAX_TOKENS = 4096

#: Default sampling temperature. Non-zero by design; see the module docstring.
GENERATOR_TEMPERATURE = 0.4

#: Candidate pool size. Must be widened alongside the temperature.
GENERATOR_TOP_K = 40

#: Nucleus sampling threshold.
GENERATOR_TOP_P = 0.9


def generator_options(temperature: float = GENERATOR_TEMPERATURE) -> Dict[str, Any]:
    """
    Return the provider option dict for a generation call.

    Parameters
    ----------
    temperature:
        Sampling temperature. ``0.0`` is accepted and, combined with the
        widened ``top_k``, produces near-deterministic output — useful for
        tests that need a stable response.

    Returns
    -------
    dict
        A fresh dictionary. Mutating it never affects the shared defaults.
    """
    return deterministic_options(
        temperature=temperature,
        top_k=GENERATOR_TOP_K,
        top_p=GENERATOR_TOP_P,
        num_ctx=GENERATOR_NUM_CTX,
        max_tokens=GENERATOR_MAX_TOKENS,
    )
