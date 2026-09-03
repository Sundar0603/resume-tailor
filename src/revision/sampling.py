"""
Sampling parameters for the compression call.

Greedy, unlike the Generator. The Generator relaxes ``temperature`` and
``top_k`` together because greedy decoding produces flat, repetitive prose and
resume bullets are judged on their writing. Compression is not that job: the
bullet has already been written, and what is being asked for is constraint
satisfaction — keep these exact facts, lose these words, land under the limit.
For that, the highest-probability token is the right one every time, and
determinism is worth more than variety.

``json_mode`` is on for the same reason it is on everywhere else: it removes
the "sometimes wrapped in prose" class of failure at the provider level rather
than in the parser.

The budget is small. A compression reply is a handful of short sentences, so
the analyzer's 4096-token default is already generous and the context only has
to hold the selected bullets, never the resume.
"""

from typing import Any, Dict

from src.analyzer.sampling import deterministic_options

#: Response budget for a compression reply, in tokens. Ten bullets of fifteen
#: words plus JSON scaffolding is comfortably under this.
COMPRESSION_MAX_TOKENS = 2048


def compression_options(**overrides: Any) -> Dict[str, Any]:
    """
    Return the option dict for a compression request.

    Parameters
    ----------
    **overrides
        Option keys to override. Overriding the sampling knobs forfeits the
        reproducibility of the compression step.
    """
    return deterministic_options(max_tokens=COMPRESSION_MAX_TOKENS, **overrides)
