"""
Deterministic sampling parameters for the Job Description Analyzer.

The analyzer must return the same JobAnalysis every time it is given the
same job description. Pinning the temperature to zero is not sufficient on
its own — several other sampling knobs drift between calls unless they are
fixed explicitly:

``temperature``
    0.0 removes the softmax randomness.
``top_k`` / ``top_p``
    Greedy decoding. With ``top_k = 1`` only the highest-probability token
    is ever eligible, which removes tie-breaking randomness that survives a
    zero temperature on some runtimes (Ollama in particular).
``seed``
    Fixes the RNG for any sampling step that remains. Providers that expose
    no seed (Anthropic) rely on the remaining knobs.
``num_ctx``
    Pinned so that the context window never varies with job description
    length. A context that resizes between calls changes how the input is
    tokenised, which changes the output.
``max_tokens``
    Pinned so the response is never truncated at a provider default that
    differs between models or SDK versions.
``json_mode``
    Constrains decoding to valid JSON where the provider supports it, which
    removes the "sometimes wrapped in prose" class of variation entirely.

These are analyzer-level values, expressed in the provider-agnostic option
vocabulary documented on :class:`src.analyzer.provider.LLMProvider`. Each
provider translates them into its own dialect and ignores what it cannot
support.
"""

from types import MappingProxyType
from typing import Any, Dict, Mapping

#: Seed used for every analyzer request. The specific value is arbitrary;
#: only its stability across runs matters.
DETERMINISTIC_SEED = 42

#: Context window pinned for local runtimes, in tokens.
DETERMINISTIC_NUM_CTX = 8192

#: Response budget pinned across providers, in tokens.
DETERMINISTIC_MAX_TOKENS = 4096

#: The full deterministic option set. Read-only so callers cannot mutate the
#: shared default in place.
DETERMINISTIC_OPTIONS: Mapping[str, Any] = MappingProxyType(
    {
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": 1,
        "seed": DETERMINISTIC_SEED,
        "num_ctx": DETERMINISTIC_NUM_CTX,
        "max_tokens": DETERMINISTIC_MAX_TOKENS,
        "json_mode": True,
    }
)


def deterministic_options(**overrides: Any) -> Dict[str, Any]:
    """
    Return a fresh mutable copy of :data:`DETERMINISTIC_OPTIONS`.

    Parameters
    ----------
    **overrides
        Option keys to override. Intended for tests and for callers that
        need a larger token budget; overriding the sampling knobs forfeits
        the determinism guarantee.

    Returns
    -------
    dict
        A new dictionary. Mutating it never affects the shared defaults.
    """
    options = dict(DETERMINISTIC_OPTIONS)
    options.update(overrides)
    return options
