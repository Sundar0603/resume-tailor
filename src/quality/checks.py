"""
The deterministic Stage 2 rules.

Every threshold here was calibrated against the nine compiled resumes in
``output/compile/`` (all known-good: zero overfull boxes, zero missing glyphs)
and the regression fixture ``tests/fixtures/latex/overlapping_bullets.tex``
(one page, zero overfull boxes, text colliding). The measured separation is
recorded beside each constant. A threshold that was not measured against both
populations is a guess, and §10d is the standing reminder of what a plausible
guess costs here.
"""

from typing import Dict, List, Optional, Tuple

from .geometry import PageGeometry, Rule, TextLine
from .models import ResumeSection

# --------------------------------------------------------------------------
# Text overlap
# --------------------------------------------------------------------------
# Vertical ink overlap between vertically-adjacent rows that also intersect
# horizontally. Measured: all nine known-good PDFs produce *zero* such pairs;
# the broken fixture produces three, at 1.79pt, 3.79pt and 4.69pt. Anything in
# (0, 1.79) separates them; 0.5 leaves room for font-rounding drift without
# reaching the smallest real collision.
OVERLAP_TOLERANCE_POINTS = 0.5

# --------------------------------------------------------------------------
# Orphan words
# --------------------------------------------------------------------------
# A stranded final word ("runt"), not the typographic orphan/widow, which is a
# stranded *line* at a page boundary. The task doc's name is kept.
#
# Measured across the nine: five genuine orphans ('60%.', 'verification.',
# 'systems.', 'integrations.', 'validation.'), all with a preceding-line fill
# between 0.904 and 0.932. The word-count test is what discriminates -- it
# correctly rejects the two-word skills line 'Databases: MySQL' at fill 0.978.
ORPHAN_MAX_WORDS = 1

# The preceding line must have genuinely wrapped. Note this guard is *not*
# doing much work in the current corpus: no single-word final line was found
# with a low preceding fill. It defends against a failure mode the sample does
# not contain, and the template's \raggedright means an unjustified line can
# legitimately stop a whole word short (~0.87), so it must stay well below the
# 0.904 floor of the real orphans.
ORPHAN_PRECEDING_FILL_RATIO = 0.85

# Rows within this many points vertically, at the same indent, are one block.
BLOCK_LINE_SPACING_POINTS = 16.0
BLOCK_INDENT_TOLERANCE_POINTS = 2.0

# --------------------------------------------------------------------------
# Bullet spacing
# --------------------------------------------------------------------------
# The glyph \labelitemi renders to, and how far inside its bullet a wrapped
# continuation line sits. Measured across the nine recompiled resumes: real
# continuations land at +9.27pt (148 of them), while section headings sit at
# +2.37 and other structural rows at +2.07. 5.0 separates the two cleanly.
#
# Getting this wrong is not harmless: at +0.5 a heading is swallowed as a
# continuation of the bullet above it, the run never breaks, and the next
# section's first bullet is measured against the heading.
BULLET_GLYPH = "•"
BULLET_CONTINUATION_INDENT_POINTS = 5.0

# Gap between two sibling bullets, measured from the last line of one to the
# first line of the next. Calibrated after the \resumeItem stray-space fix:
# 115 sibling gaps across the nine recompiled resumes give a median of 3.88
# and a maximum of 7.36 -- that maximum being the structural project-title to
# first-sub-bullet step, which every document shows and which is not a defect.
#
# The defect population is the phantom empty line: 15.99 in four of the nine
# before the fix, and 14.57 / 14.62 in the two output/runs finals that first
# exposed it. The excess is one \baselineskip (11.95pt), so nothing can land
# between 7.36 and 14.57. 10.0 sits in that empty band, comfortably clear of
# the legitimate 7.36 step.
BULLET_GAP_MAX_POINTS = 10.0

# A \titlerule spans the text column; a link underline does not.
RULE_MIN_WIDTH_RATIO = 0.5
# The heading sits immediately above its rule.
HEADING_SEARCH_POINTS = 14.0

_SECTION_BY_STRIPPED = {
    section.value.replace(" ", ""): section
    for section in ResumeSection
    if section is not ResumeSection.UNKNOWN
}


def _document_order(pages: List[PageGeometry]) -> List[TextLine]:
    """All analysed lines, ordered as a reader meets them."""
    ordered = []
    for page in sorted(pages, key=lambda p: p.page_number):
        ordered.extend(sorted(page.lines, key=lambda line: -line.y0))
    return ordered


def find_overlaps(pages: List[PageGeometry]) -> List[Tuple[TextLine, TextLine, float]]:
    """
    Rows whose ink collides.

    Uses the *raw* rows, never the analysed lines: layout analysis merges two
    colliding rows into one and the collision then cannot be seen. Verified on
    the fixture, where the analysed pass loses all three collisions.

    Two adjacent rows overlap when the lower one's top rises above the upper
    one's bottom by more than the tolerance, *and* their horizontal ranges
    intersect. Requiring both axes is what keeps ``\\resumeSubheading``'s
    right-aligned dates -- same visual row, horizontally disjoint -- from
    registering.
    """
    found = []
    for page in pages:
        rows = sorted(page.raw_rows, key=lambda row: -row.baseline)
        for upper, lower in zip(rows, rows[1:]):
            ink = lower.y1 - upper.y0
            if ink <= OVERLAP_TOLERANCE_POINTS:
                continue
            if upper.x1 < lower.x0 or lower.x1 < upper.x0:
                continue
            found.append((upper, lower, ink))
    return found


def find_rule_collisions(pages: List[PageGeometry]) -> List[Tuple[Rule, TextLine]]:
    """
    Section rules drawn through text.

    Cheap, and invisible to any text-only check: a rule is a vector element, so
    discarding rects would hide a heading rule slicing through a bullet.
    """
    found = []
    for page in pages:
        wide = [
            rule
            for rule in page.rules
            if (rule.x1 - rule.x0) >= page.width * RULE_MIN_WIDTH_RATIO
        ]
        for rule in wide:
            for line in page.lines:
                if not (line.y0 < rule.y1 and rule.y0 < line.y1):
                    continue
                if line.x1 < rule.x0 or rule.x1 < line.x0:
                    continue
                found.append((rule, line))
    return found


def _blocks(lines: List[TextLine]) -> List[List[TextLine]]:
    """Runs of consecutive lines at the same indent — one wrapped paragraph."""
    blocks = []
    current: List[TextLine] = []
    for line in sorted(lines, key=lambda item: -item.y0):
        if (
            current
            and abs(line.x0 - current[-1].x0) <= BLOCK_INDENT_TOLERANCE_POINTS
            and (current[-1].y0 - line.y0) <= BLOCK_LINE_SPACING_POINTS
        ):
            current.append(line)
        else:
            if len(current) > 1:
                blocks.append(current)
            current = [line]
    if len(current) > 1:
        blocks.append(current)
    return blocks


def _column_width(pages: List[PageGeometry]) -> float:
    """
    Text-column width, measured from the rendered document.

    Prefers the section rules: ``\\titlerule`` spans the text column exactly, by
    construction, so it defines the width regardless of how the content happens
    to wrap. Falls back to the widest text extent when a document has no rules.

    The fallback is the weaker measure — on a page whose every line is short it
    reports the *content* width, which would make each line look completely
    full and turn the orphan check's fill guard into a no-op. Real resumes
    always carry rules, so the fallback is a backstop, not the normal path.

    Derived from the rendering rather than the template's ``\\addtolength``
    values, so it stays correct if the page geometry is ever retuned.
    """
    widths = [
        rule.x1 - rule.x0
        for page in pages
        for rule in page.rules
        if (rule.x1 - rule.x0) >= page.width * RULE_MIN_WIDTH_RATIO
    ]
    if widths:
        return max(widths)

    lines = [line for page in pages for line in page.lines]
    if not lines:
        return 0.0
    return max(line.x1 for line in lines) - min(line.x0 for line in lines)


def find_orphans(pages: List[PageGeometry]) -> List[TextLine]:
    """
    Final lines left holding a single word after a full line wrapped.

    Headings are excluded by name; the contact block is excluded because it is
    not a multi-line block at a shared indent.
    """
    column = _column_width(pages)
    if column <= 0.0:
        return []

    orphans = []
    for page in pages:
        for block in _blocks(page.lines):
            last, preceding = block[-1], block[-2]
            if last.text.strip().replace(" ", "") in _SECTION_BY_STRIPPED:
                continue
            if last.word_count > ORPHAN_MAX_WORDS or last.word_count == 0:
                continue
            if (preceding.width / column) < ORPHAN_PRECEDING_FILL_RATIO:
                continue
            orphans.append(last)
    return orphans


def _bullet_items(lines: List[TextLine]) -> List[List[List[TextLine]]]:
    """
    Group a page's lines into bullet items, in reading order.

    An item opens on a line beginning with the bullet glyph and absorbs the
    wrapped continuation lines that follow it at a deeper indent. Any other
    line -- a heading, a rule caption, a skills row -- closes the run, so a
    heading is never measured against the bullet beneath it.

    Returned as runs rather than one flat list: only items inside the same run
    are siblings, and comparing across a run boundary would pair the last
    bullet of one list with the first of the next.
    """
    runs: List[List[List[TextLine]]] = []
    current: List[List[TextLine]] = []

    for line in sorted(lines, key=lambda item: -item.y0):
        if line.text.lstrip().startswith(BULLET_GLYPH):
            current.append([line])
        elif (
            current
            and line.x0 > current[-1][0].x0 + BULLET_CONTINUATION_INDENT_POINTS
            and line.y0 < current[-1][-1].y0
        ):
            current[-1].append(line)
        else:
            if len(current) > 1:
                runs.append(current)
            current = []

    if len(current) > 1:
        runs.append(current)
    return runs


def find_bullet_spacing_anomalies(
    pages: List[PageGeometry],
) -> List[Tuple[TextLine, TextLine, float]]:
    """
    Sibling bullets separated by more space than the list's own rhythm.

    Returns ``(preceding_item_last_line, following_item_first_line, gap)``.

    The defect this catches is a phantom empty line: when a bullet's final line
    fills the measure exactly, a stray space token after it cannot fit, and TeX
    emits an extra line one ``\\baselineskip`` tall. It carries no glyphs, so
    nothing in the compile log or the overlap check sees it -- only the
    distance between the two bullets gives it away.

    Only items at the same indent within one run are compared, so the wider
    structural gap between a project title and its first sub-bullet is not a
    finding.
    """
    found = []
    for page in pages:
        for run in _bullet_items(page.lines):
            for preceding, following in zip(run, run[1:]):
                if (
                    abs(following[0].x0 - preceding[0].x0)
                    > BLOCK_INDENT_TOLERANCE_POINTS
                ):
                    continue
                gap = preceding[-1].y0 - following[0].y1
                if gap <= BULLET_GAP_MAX_POINTS:
                    continue
                found.append((preceding[-1], following[0], gap))
    return found


def attribute_sections(
    pages: List[PageGeometry],
) -> Dict[int, Dict[float, ResumeSection]]:
    """
    Map every line to the section it sits under.

    Anchored on the ``\\titlerule`` positions rather than on heading strings:
    each ``\\section`` emits exactly one full-width rule, so the rules *are* the
    boundaries. The heading text is used only to *name* a section, matched with
    spaces stripped because the raw pass yields ``TECHNICALSKILLS``.

    Walks in document order across pages, because a section can span a page
    break — which is exactly the case that matters when measuring overflow.
    """
    markers: List[Tuple[int, float, ResumeSection]] = []
    for page in pages:
        for rule in page.rules:
            if (rule.x1 - rule.x0) < page.width * RULE_MIN_WIDTH_RATIO:
                continue
            heading = ResumeSection.UNKNOWN
            best = None
            for line in page.lines:
                gap = line.y0 - rule.y1
                if 0 <= gap <= HEADING_SEARCH_POINTS and (best is None or gap < best):
                    named = _SECTION_BY_STRIPPED.get(
                        line.text.strip().replace(" ", "").upper()
                    )
                    if named is not None:
                        heading, best = named, gap
            markers.append((page.page_number, rule.y1, heading))

    markers.sort(key=lambda m: (m[0], -m[1]))

    attribution: Dict[int, Dict[float, ResumeSection]] = {}
    for page in pages:
        attribution[page.page_number] = {}
        for line in page.lines:
            # A heading sits *above* its own rule, so the marker walk below
            # would file it under the previous section. Name it directly.
            named = _SECTION_BY_STRIPPED.get(line.text.strip().replace(" ", "").upper())
            if named is not None:
                attribution[page.page_number][line.y0] = named
                continue
            current = ResumeSection.UNKNOWN
            for page_number, rule_y, section in markers:
                if page_number < page.page_number or (
                    page_number == page.page_number and rule_y >= line.y1
                ):
                    current = section
                else:
                    break
            attribution[page.page_number][line.y0] = current
    return attribution


def measure_overflow(
    pages: List[PageGeometry],
) -> Tuple[int, float, List[ResumeSection], Dict[ResumeSection, int]]:
    """
    How much content spilled past page one, and out of which sections.

    Returns ``(overflow_line_count, overflow_height_points,
    overflowing_sections, lines_per_section)``. The Revision Engine uses these
    to choose a trim target; they are an accelerator, not a correctness
    requirement, since it can also trim one bullet and recompile.
    """
    attribution = attribute_sections(pages)
    per_section: Dict[ResumeSection, int] = {}
    overflowing: List[ResumeSection] = []
    overflow_lines = 0
    overflow_height = 0.0

    for page in pages:
        for line in page.lines:
            section = attribution.get(page.page_number, {}).get(
                line.y0, ResumeSection.UNKNOWN
            )
            per_section[section] = per_section.get(section, 0) + 1
            if page.page_number > 1:
                overflow_lines += 1
                if section not in overflowing:
                    overflowing.append(section)
        if page.page_number > 1 and page.lines:
            top = max(line.y1 for line in page.lines)
            bottom = min(line.y0 for line in page.lines)
            overflow_height += top - bottom

    overflowing.sort(key=lambda section: section.value)
    return overflow_lines, overflow_height, overflowing, per_section
