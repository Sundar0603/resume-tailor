"""
Internal utilities shared across all section parsers.

Provides helpers for:
- Splitting a Markdown body into top-level sections (# Heading)
- Splitting a section body into sub-blocks (## Heading)
- Reading Key: Value scalar fields
- Reading bullet list fields
"""

import re
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def split_top_level_sections(body: str) -> Dict[str, str]:
    """
    Split the Markdown body (everything after front matter) into a dict
    keyed by the H1 heading text (lowercased).

    Example
    -------
    '# Contact\n...\n# Summary\n...' ->
        {'contact': '...', 'summary': '...'}
    """
    sections: Dict[str, str] = {}
    pattern = re.compile(r'^# (.+)$', re.MULTILINE)
    matches = list(pattern.finditer(body))

    for idx, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        sections[heading.lower()] = body[start:end].strip()

    return sections


def split_sub_blocks(section_body: str, heading: str) -> List[str]:
    """
    Split a section body into sub-blocks delimited by '## <heading>'.

    Parameters
    ----------
    section_body : str
        The text content of a top-level section (without its own H1 line).
    heading : str
        The H2 heading to split on (e.g. 'Experience', 'Project', 'Degree').

    Returns
    -------
    List[str]
        Each element is the text of one sub-block (without the H2 line itself).
    """
    pattern = re.compile(
        r'^## ' + re.escape(heading) + r'\s*$',
        re.MULTILINE | re.IGNORECASE,
    )
    parts = pattern.split(section_body)
    # The first element is text before the first match (usually empty)
    return [p.strip() for p in parts[1:] if p.strip()]


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def get_scalar(block: str, key: str) -> Optional[str]:
    """
    Extract a scalar value from a 'Key: Value' line in a block.

    Returns None if the key is not found.
    """
    pattern = re.compile(
        r'^' + re.escape(key) + r':\s*(.+)$',
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(block)
    if match:
        return match.group(1).strip()
    return None


def get_list(block: str, key: str) -> List[str]:
    """
    Extract a bullet list that follows a 'Key:' label in a block.

    The list ends when a non-bullet, non-blank line is encountered,
    or when the block ends.

    Returns an empty list if the key is not found or has no items.
    """
    key_pattern = re.compile(
        r'^' + re.escape(key) + r':\s*$',
        re.MULTILINE | re.IGNORECASE,
    )
    match = key_pattern.search(block)
    if not match:
        return []

    rest = block[match.end():]
    items: List[str] = []
    for line in rest.splitlines():
        stripped = line.strip()
        if stripped.startswith('- '):
            items.append(stripped[2:].strip())
        elif stripped == '':
            continue
        else:
            # Non-bullet, non-blank line signals end of list
            break
    return items
