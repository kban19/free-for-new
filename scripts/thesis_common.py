"""Shared building blocks for the Rojava thesis modules.

Every chapter module imports these helpers so numbering, spacing, captions and
bidi handling stay identical across the whole document.
"""
from __future__ import annotations

from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

import docx_bidi as D

BODY_FORMAT = dict(line=1.5, space_after=6, first_line_indent=Cm(1.27))
PLACEHOLDER = "[يُملأ بعد القياس]"


def ensure_styles(doc):
    """Create the two caption styles used by the table/figure indexes."""
    for name in ("FigureCaption", "TableCaption"):
        try:
            style = doc.styles[name]
        except KeyError:
            style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            style.base_style = doc.styles["Normal"]
        style.font.name = "Times New Roman"
        style.font.size = Pt(12)
        style.font.bold = True
        # Word reads bCs/szCs for Arabic; without the twins the style is ignored.
        rpr = style.element.get_or_add_rPr()
        for tag in ("b", "sz"):
            if rpr.find(qn("w:" + tag)) is not None:
                D.get_or_add(rpr, f"{tag}Cs", D.RPR_ORDER)


def start_chapter(ctx, number: int) -> None:
    """Reset table/figure counters so captions read (chapter-index)."""
    ctx["chapter"] = number
    ctx["table_no"] = 0
    ctx["fig_no"] = 0


def chapter_heading(doc, ctx, ordinal: str, title: str) -> None:
    """Bold 16 pt chapter title at the start (right) margin, on a new page.

    The Rojava guide right-aligns level-1 headings; only the covers and the
    abstracts are centred, so chapter titles use ``start`` here.
    """
    D.heading(doc, f"{ordinal}: {title}", 1, rtl=True, align="start",
              size=16, bold=True, space_before=0, space_after=18)


def h2(doc, text: str) -> None:
    """Bold 14 pt section heading such as ``2-3``."""
    D.heading(doc, text, 2, rtl=True, align="start")


def h3(doc, text: str) -> None:
    """Bold 14 pt sub-subsection heading such as ``2-3-1``."""
    D.heading(doc, text, 3, rtl=True, align="start")


def body(doc, text: str, **kwargs):
    """Justified 14 pt body paragraph with the guide's 1.5 spacing and tab indent."""
    fmt = dict(BODY_FORMAT)
    fmt.update(kwargs)
    return D.para(doc, text, rtl=True, align="justify", **fmt)


def body_plain(doc, text: str, **kwargs):
    """Body paragraph without the first-line indent (after a list or a table)."""
    fmt = dict(line=1.5, space_after=6)
    fmt.update(kwargs)
    return D.para(doc, text, rtl=True, align="justify", **fmt)


def labeled(doc, label: str, text: str):
    """Paragraph that opens with a bold lead-in, common in Arabic academic prose."""
    p = D.para(doc, "", rtl=True, align="justify", **BODY_FORMAT)
    D.add_text(p, label + ": ", True, bold=True)
    D.add_text(p, text, True)
    return p


def bullets(doc, items) -> None:
    """Real Word bullet list (never manual '•' characters)."""
    num = D.new_list(doc, "bullet")
    for item in items:
        D.list_item(doc, item, num, rtl=True, line=1.5, space_after=3)


def numbered(doc, items) -> None:
    """Real Word numbered list, restarting at 1 on each call."""
    num = D.new_list(doc, "decimal")
    for item in items:
        D.list_item(doc, item, num, rtl=True, line=1.5, space_after=3)


def _numbered(ctx, kind: str, title: str, key: str) -> str:
    """Build 'جدول (3-2) - ...' or a plain label outside the chapters."""
    ctx[key] += 1
    chapter = ctx.get("chapter")
    if chapter in (None, 0):
        return f"{kind}: {title}"
    return f"{kind} ({chapter}-{ctx[key]}) - {title}"


def table_caption(doc, ctx, title: str) -> str:
    """Caption above the table, 12 pt bold, numbered (chapter-index)."""
    text = _numbered(ctx, "جدول", title, "table_no")
    D.add_caption(doc, text, kind="Table", rtl=True)
    return text


def figure_caption(doc, ctx, title: str) -> str:
    """Caption below the figure, 12 pt bold, numbered (chapter-index)."""
    text = _numbered(ctx, "الشكل", title, "fig_no")
    D.add_caption(doc, text, kind="Figure", rtl=True)
    return text


def table(doc, ctx, title: str, rows, widths=None, size=10, first_col_bold=False):
    """Caption + real RTL table. ``rows`` stay in logical reading order."""
    table_caption(doc, ctx, title)
    t = D.add_table(doc, rows, widths=widths, rtl=True, size=size)
    D.set_cell_shading_table(t, "F2F2F2")
    if first_col_bold:
        for ri, row in enumerate(t.rows):
            if ri == 0:
                continue
            for p in row.cells[0].paragraphs:
                for r in p.runs:
                    D.style_run(r, True, bold=True, size=size)
    D.para(doc, "", rtl=True, space_after=4)
    return t


def figure(doc, ctx, path, title: str, width_twips: int = 8100, alt: str = ""):
    """Picture clamped to the printable width plus its caption underneath."""
    D.add_image(doc, path, width_twips=width_twips, alt=alt or title, rtl=True)
    figure_caption(doc, ctx, title)
    D.para(doc, "", rtl=True, space_after=2)


def note(doc, text: str, *, fill: str = "FFF4D6", border: str = "BF9000"):
    """Shaded callout paragraph with an accent bar on the start (right) side."""
    p = D.para(doc, "", rtl=True, align="justify", line=1.4, space_before=6, space_after=10)
    pPr = p._p.get_or_add_pPr()

    pBdr = D.get_or_add(pPr, "pBdr", D.PPR_ORDER)
    bar = OxmlElement("w:right")
    for k, v in (("val", "single"), ("sz", "18"), ("space", "6"), ("color", border)):
        bar.set(qn("w:" + k), v)
    pBdr.append(bar)

    shd = D.get_or_add(pPr, "shd", D.PPR_ORDER)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)

    ind = D.get_or_add(pPr, "ind", D.PPR_ORDER)
    ind.set(qn("w:left"), "170")
    ind.set(qn("w:right"), "170")

    D.add_text(p, text, True, size=12, color="7F6000")
    return p


def new_page(doc) -> None:
    """Start the next chapter on a fresh page."""
    D.paragraph_with_page_break(doc, rtl=True)


def center_line(doc, text: str, size: int = 14, bold: bool = False, space: int = 0):
    """Centered single line (covers, approvals, poem-style dedication)."""
    return D.para(doc, text, rtl=True, align="center", size=size, bold=bold,
                  line=1.5, space_after=space)
