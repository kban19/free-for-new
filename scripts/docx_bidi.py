"""docx_bidi.py - minimal, tested python-docx + lxml helpers for RTL/LTR documents.

Extracted from the multilingual DOCX skill so the thesis builder does not
duplicate low-level OOXML logic. Only the parts the Rojava thesis needs are
kept: schema-ordered element insertion, script-boundary run splitting,
logical alignment, RTL tables, real Word fields (PAGE / TOC), captions and
page numbering.

Key rules encoded here:
  * inside a <w:bidi/> paragraph, w:jc="left" means START (right edge);
  * Arabic runs need szCs/bCs/iCs twins or Word ignores the formatting;
  * theme fonts must be stripped or they silently override explicit fonts.
"""
import copy
import re
import unicodedata

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Twips
from lxml import etree

# ---------------------------------------------------------------------------
# 1. Schema order tables (children MUST appear in this order)
# ---------------------------------------------------------------------------
PPR_ORDER = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
    "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
    "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE",
    "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind",
    "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
    "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
    "sectPr", "pPrChange",
]
RPR_ORDER = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
    "dstrike", "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid",
    "vanish", "webHidden", "color", "spacing", "w", "kern", "position", "sz",
    "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign",
    "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath",
]
TBLPR_ORDER = [
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
    "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders",
    "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription",
]
TCPR_ORDER = [
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
    "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
]
SECTPR_ORDER = [
    "headerReference", "footerReference", "footnotePr", "endnotePr", "type",
    "pgSz", "pgMar", "paperSrc", "pgBorders", "lnNumType", "pgNumType", "cols",
    "formProt", "vAlign", "noEndnote", "titlePg", "textDirection", "bidi",
    "rtlGutter", "docGrid", "printerSettings", "sectPrChange",
]
_AFTER_UPDATEFIELDS = [
    "hdrShapeDefaults", "footnotePr", "endnotePr", "compat", "docVars", "rsids",
    "mathPr", "attachedSchema", "themeFontLang", "clrSchemeMapping",
    "doNotIncludeSubdocsInStats", "doNotAutoCompressPictures", "forceUpgrade",
    "captions", "readModeInkLockDown", "smartTagType", "schemaLibrary",
    "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol", "listSeparator",
]

CFG = dict(
    latin_font="Times New Roman",
    rtl_font="Times New Roman",
    size=14,
    lang_latin="en-US",
    lang_bidi="ar-SA",
    rtl_default=True,
)


# ---------------------------------------------------------------------------
# 2. Low-level XML helpers
# ---------------------------------------------------------------------------
def _name(el):
    return etree.QName(el).localname if isinstance(el.tag, str) else None


def get_or_add(parent, name, order):
    """Return child <w:name>, creating it at the schema-correct position."""
    el = parent.find(qn("w:" + name))
    if el is not None:
        return el
    el = OxmlElement("w:" + name)
    pos = order.index(name)
    for sib in parent:
        n = _name(sib)
        if n in order and order.index(n) > pos:
            sib.addprevious(el)
            return el
    parent.append(el)
    return el


def drop(parent, name):
    for el in parent.findall(qn("w:" + name)):
        parent.remove(el)


def flag_on(parent, name):
    """True if <w:name/> exists and is not switched off (w:val=0/false/off)."""
    el = parent.find(qn("w:" + name)) if parent is not None else None
    return el is not None and el.get(qn("w:val"), "1") not in ("0", "false", "off")


def set_flag(parent, name, order, on, explicit_off=False):
    drop(parent, name)
    if on:
        get_or_add(parent, name, order)
    elif explicit_off:
        get_or_add(parent, name, order).set(qn("w:val"), "0")


_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def clean(text):
    """Remove characters illegal in XML (they trigger Word repair prompts)."""
    return _BAD_XML.sub("", text or "")


# ---------------------------------------------------------------------------
# 3. Direction logic
# ---------------------------------------------------------------------------
_BIDI = unicodedata.bidirectional
_COMPOUND_LTR_RE = re.compile(r"(?<![0-9A-Za-z])(?:\d+(?:[-/.:]\d+)+)(?![0-9A-Za-z])")


def _word_dir(word):
    for ch in word:
        b = _BIDI(ch)
        if b in ("R", "AL"):
            return "R"
        if b == "L":
            return "L"
    return None


def detect_rtl(text, default=None):
    """Guess paragraph direction from the majority of strong words."""
    r = l = 0
    first = None
    for w in re.findall(r"[^\W\d_]+", text or ""):
        d = _word_dir(w)
        if d is None:
            continue
        first = first or d
        if d == "R":
            r += 1
        else:
            l += 1
    if r == l == 0:
        return CFG["rtl_default"] if default is None else default
    return (r > l) if r != l else first == "R"


def split_script_runs(text, rtl):
    """Split text into [(chunk, is_rtl_run)] so each Word run is single-script.

    Protects compound Western-digit tokens (2026-11-20, 3.45.1, 16:9) as LTR so
    Word never reverses hyphens, slashes or dots inside an RTL paragraph.
    """
    base = "R" if rtl else "L"
    n = len(text)
    if n == 0:
        return []
    cls = []
    for ch in text:
        b = _BIDI(ch)
        if b in ("R", "AL"):
            cls.append("R")
        elif b == "L":
            cls.append("L")
        elif b in ("AN", "EN", "ES", "CS", "ET"):
            cls.append(b)
        elif b in ("NSM", "BN"):
            cls.append("ADOPT")
        else:
            cls.append("N")

    for m in _COMPOUND_LTR_RE.finditer(text):
        for k in range(m.start(), m.end()):
            cls[k] = "L"

    for i in range(1, n - 1):
        a, b = cls[i - 1], cls[i + 1]
        if cls[i] == "ES" and a == b == "EN":
            cls[i] = "EN"
        elif cls[i] == "CS" and a == b and a in ("EN", "AN"):
            cls[i] = a
    for rng in (range(n), range(n - 1, -1, -1)):
        for i in rng:
            if cls[i] == "ET" and (
                (i > 0 and cls[i - 1] == "EN") or (i < n - 1 and cls[i + 1] == "EN")
            ):
                cls[i] = "EN"

    res, prev = [None] * n, None
    for i, c in enumerate(cls):
        if c in ("R", "L"):
            res[i] = prev = c
        elif c == "AN":
            res[i] = "R"
        elif c == "EN":
            res[i] = prev or base
        elif c == "ADOPT":
            res[i] = res[i - 1] if i else None

    i = 0
    while i < n:
        if res[i] is None:
            j = i
            while j < n and res[j] is None:
                j += 1
            before = res[i - 1] if i else base
            after = res[j] if j < n else base
            d = before if before == after else base
            for k in range(i, j):
                res[k] = d
            i = j
        else:
            i += 1

    out = []
    for ch, d in zip(text, res):
        if out and out[-1][1] == d:
            out[-1][0].append(ch)
        else:
            out.append([[ch], d])
    return [("".join(cs), d == "R") for cs, d in out]


def is_para_rtl(p):
    return flag_on(p._p.pPr, "bidi")


def cell_direction(text, table_rtl=True):
    """Table cells take the table's direction unless they hold Latin-only text.

    A cell like ``mms_kmr`` must stay LTR inside an Arabic table, while a cell that
    contains any Arabic letter must stay RTL even if it starts with a Latin token.
    """
    if any(_BIDI(ch) in ("R", "AL") for ch in text):
        return True
    return table_rtl if not any(_BIDI(ch) == "L" for ch in text) else False


def set_para_rtl(p, rtl):
    """Paragraph base direction; emits <w:bidi w:val="0"/> when default is RTL."""
    pPr = p._p.get_or_add_pPr()
    set_flag(pPr, "bidi", PPR_ORDER, rtl, explicit_off=CFG["rtl_default"])


def set_para_align(p, align="start", rtl=None):
    """Logical alignment: start | end | center | justify.

    In Word, a bidi paragraph reads jc=left as START (right edge), so mapping is
    inverted on purpose.
    """
    if rtl is None:
        rtl = is_para_rtl(p)
    a = align.lower()
    if a in ("left", "right"):
        a = "start" if (a == "left") != rtl else "end"
    val = {"start": "left", "end": "right", "center": "center", "justify": "both"}[a]
    pPr = p._p.get_or_add_pPr()
    get_or_add(pPr, "jc", PPR_ORDER).set(qn("w:val"), val)


# ---------------------------------------------------------------------------
# 4. Runs and paragraphs
# ---------------------------------------------------------------------------
def style_run(run, rtl, *, bold=False, italic=False, underline=False, size=None,
              color=None, font=None, lang_bidi=None, lang_latin=None,
              no_proof=False, explicit_ltr=False):
    """Direct run formatting with complex-script twins (bCs/iCs/szCs/cs font)."""
    rPr = run._r.get_or_add_rPr()
    if font:
        rf = get_or_add(rPr, "rFonts", RPR_ORDER)
        for a in ("ascii", "hAnsi", "cs", "eastAsia"):
            rf.set(qn("w:" + a), font)
        if rtl:
            rf.set(qn("w:hint"), "cs")
    if bold:
        get_or_add(rPr, "b", RPR_ORDER)
        get_or_add(rPr, "bCs", RPR_ORDER)
    if italic:
        get_or_add(rPr, "i", RPR_ORDER)
        get_or_add(rPr, "iCs", RPR_ORDER)
    if no_proof:
        get_or_add(rPr, "noProof", RPR_ORDER)
    if color:
        get_or_add(rPr, "color", RPR_ORDER).set(qn("w:val"), color.lstrip("#").upper())
    if size:
        v = str(int(round(size * 2)))
        get_or_add(rPr, "sz", RPR_ORDER).set(qn("w:val"), v)
        get_or_add(rPr, "szCs", RPR_ORDER).set(qn("w:val"), v)
    if underline:
        get_or_add(rPr, "u", RPR_ORDER).set(qn("w:val"), "single")
    set_flag(rPr, "rtl", RPR_ORDER, rtl, explicit_off=explicit_ltr or CFG["rtl_default"])
    if lang_bidi or lang_latin:
        lg = get_or_add(rPr, "lang", RPR_ORDER)
        if lang_latin:
            lg.set(qn("w:val"), lang_latin)
        if lang_bidi:
            lg.set(qn("w:bidi"), lang_bidi)


def add_text(p, text, rtl=None, **fmt):
    """Append text as script-split runs with explicit RTL/LTR flags."""
    text = clean(text)
    if rtl is None:
        rtl = is_para_rtl(p)
    runs = []
    for chunk, is_rtl in split_script_runs(text, rtl):
        r = p.add_run(chunk)
        style_run(r, is_rtl, explicit_ltr=(rtl and not is_rtl), **fmt)
        runs.append(r)
    return runs


def para(container, text="", *, style=None, rtl=None, align="start",
         space_before=None, space_after=None, line=None, keep_next=False,
         keep_lines=False, page_break_before=False, first_line_indent=None, **fmt):
    """New paragraph with explicit direction, logical alignment and spacing."""
    if rtl is None:
        rtl = detect_rtl(text)
    p = container.add_paragraph(style=style)
    set_para_rtl(p, rtl)
    set_para_align(p, align, rtl)
    pf = p.paragraph_format
    if space_before is not None:
        pf.space_before = Pt(space_before)
    if space_after is not None:
        pf.space_after = Pt(space_after)
    if line is not None:
        pf.line_spacing = line
    if first_line_indent is not None:
        pf.first_line_indent = first_line_indent
    if keep_next:
        pf.keep_with_next = True
    if keep_lines:
        pf.keep_together = True
    if page_break_before:
        pf.page_break_before = True
    if text:
        add_text(p, text, rtl, **fmt)
    return p


def heading(doc, text, level=1, rtl=None, align="start", **fmt):
    """Built-in 'Heading n' / 'Title' style, needed for the Navigation Pane and TOC."""
    return para(doc, text, style="Title" if level == 0 else f"Heading {level}",
                rtl=rtl, align=align, keep_next=True, **fmt)


def page_break(doc):
    from docx.enum.text import WD_BREAK

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------------------
# 5. Document setup
# ---------------------------------------------------------------------------
def _set_fonts(rPr, latin, cs, ea=None):
    rf = get_or_add(rPr, "rFonts", RPR_ORDER)
    for a in list(rf.attrib):
        if a.lower().endswith("theme"):
            del rf.attrib[a]
    rf.set(qn("w:ascii"), latin)
    rf.set(qn("w:hAnsi"), latin)
    rf.set(qn("w:cs"), cs)
    if ea:
        rf.set(qn("w:eastAsia"), ea)


def printable_width(doc):
    """Printable width of the last section, in twips (dxa)."""
    s = doc.sections[-1]
    return int(s.page_width.twips - s.left_margin.twips - s.right_margin.twips)


def add_update_fields(doc):
    """Ask Word to refresh fields (TOC, PAGE, NUMPAGES) on open, schema-ordered."""
    st = doc.settings.element
    if st.find(qn("w:updateFields")) is not None:
        return
    el = OxmlElement("w:updateFields")
    el.set(qn("w:val"), "true")
    for sib in st:
        if _name(sib) in _AFTER_UPDATEFIELDS:
            sib.addprevious(el)
            return
    st.append(el)


def setup_document(doc=None, *, rtl_default=True, size=14, line_spacing=1.5,
                   space_after=6, heading_color="000000"):
    """Prepare the document: A4, Times New Roman, complex-script twins, RTL default."""
    CFG.update(latin_font="Times New Roman", rtl_font="Times New Roman", size=size,
               rtl_default=rtl_default)
    doc = doc or Document()
    styles_el = doc.styles.element

    dd = styles_el.find(qn("w:docDefaults"))
    if dd is None:
        dd = OxmlElement("w:docDefaults")
        styles_el.insert(0, dd)
    rpd = dd.find(qn("w:rPrDefault"))
    if rpd is None:
        rpd = OxmlElement("w:rPrDefault")
        dd.insert(0, rpd)
    rpr = rpd.find(qn("w:rPr"))
    if rpr is None:
        rpr = etree.SubElement(rpd, qn("w:rPr"))
    _set_fonts(rpr, "Times New Roman", "Times New Roman")
    get_or_add(rpr, "sz", RPR_ORDER).set(qn("w:val"), str(int(size * 2)))
    get_or_add(rpr, "szCs", RPR_ORDER).set(qn("w:val"), str(int(size * 2)))
    lg = get_or_add(rpr, "lang", RPR_ORDER)
    lg.set(qn("w:val"), "en-US")
    lg.set(qn("w:bidi"), "ar-SA")

    # Strip theme fonts from every built-in style, they override explicit fonts.
    for st in styles_el.findall(qn("w:style")):
        srpr = st.find(qn("w:rPr"))
        if srpr is not None:
            rf = srpr.find(qn("w:rFonts"))
            if rf is not None and any(a.lower().endswith("theme") for a in rf.attrib):
                _set_fonts(srpr, "Times New Roman", "Times New Roman")

    normal = doc.styles["Normal"]
    normal.paragraph_format.space_after = Pt(space_after)
    normal.paragraph_format.line_spacing = line_spacing
    normal.font.name = "Times New Roman"
    set_flag(normal.element.get_or_add_pPr(), "bidi", PPR_ORDER, rtl_default)

    # Guide sizes: H1 16pt bold, H2 14pt bold, body 14pt.
    heading_sizes = {"Title": 22, "Heading 1": 16, "Heading 2": 14, "Heading 3": 14}
    for nm, sz in heading_sizes.items():
        try:
            s = doc.styles[nm]
        except KeyError:
            continue
        s.font.size = Pt(sz)
        s.font.bold = True
        s.font.italic = False
        s.font.name = "Times New Roman"
        s.font.color.rgb = RGBColor.from_string(heading_color)
        if nm != "Title":
            s.paragraph_format.space_before = Pt(12)
            s.paragraph_format.space_after = Pt(6)
            s.paragraph_format.keep_with_next = True
            s.paragraph_format.keep_together = True
            s.paragraph_format.line_spacing = 1.5

    # Add the complex-script twins the auditor checks for.
    for st in styles_el.findall(qn("w:style")):
        srpr = st.find(qn("w:rPr"))
        if srpr is None:
            continue
        for lat, twin in (("sz", "szCs"), ("b", "bCs"), ("i", "iCs")):
            e = srpr.find(qn("w:" + lat))
            if e is not None and srpr.find(qn("w:" + twin)) is None:
                t = get_or_add(srpr, twin, RPR_ORDER)
                if e.get(qn("w:val")) is not None:
                    t.set(qn("w:val"), e.get(qn("w:val")))

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Twips(11906), Twips(16838)
    sec.orientation = WD_ORIENT.PORTRAIT
    set_section_direction(sec, rtl=True)
    set_margins(sec, rtl=True)
    doc.core_properties.language = "ar-SA"
    return doc


def set_margins(section, rtl=True, top_cm=2.5, bottom_cm=2.5, right_cm=3.18, left_cm=2.5):
    """Guide margins: top/bottom 2.5 cm, binding side 3.18 cm, other side 2.5 cm.

    For RTL (Arabic) the binding side is the right; for LTR it swaps to the left.
    """
    cm = 566.93
    section.top_margin = Twips(int(top_cm * cm))
    section.bottom_margin = Twips(int(bottom_cm * cm))
    if rtl:
        section.right_margin = Twips(int(right_cm * cm))
        section.left_margin = Twips(int(left_cm * cm))
    else:
        section.right_margin = Twips(int(left_cm * cm))
        section.left_margin = Twips(int(right_cm * cm))


def set_section_direction(section, rtl=True):
    """Section-level bidi so columns and gutters flow in the right direction."""
    set_flag(section._sectPr, "bidi", SECTPR_ORDER, rtl)


def set_page_numbering(section, fmt="decimal", start=1):
    """Restart page numbering per section (upperRoman for preliminaries, then 1)."""
    sectPr = section._sectPr
    pg = get_or_add(sectPr, "pgNumType", SECTPR_ORDER)
    pg.set(qn("w:fmt"), fmt)
    pg.set(qn("w:start"), str(int(start)))


# ---------------------------------------------------------------------------
# 6. Fields, headers/footers, captions, images, TOC
# ---------------------------------------------------------------------------
def add_field(p, instr, placeholder="1", rtl=False, **fmt):
    """Complex field: begin / instrText / separate / result / end."""
    runs = []

    def fld(kind):
        r = p.add_run()
        e = OxmlElement("w:fldChar")
        e.set(qn("w:fldCharType"), kind)
        r._r.append(e)
        style_run(r, rtl, **fmt)
        runs.append(r)

    fld("begin")
    r = p.add_run()
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = f" {instr} "
    r._r.append(it)
    style_run(r, rtl, **fmt)
    runs.append(r)
    fld("separate")
    r = p.add_run(placeholder)
    style_run(r, rtl, **fmt)
    runs.append(r)
    fld("end")
    return runs


def add_footer_page_number(section, rtl=True, size=11, prefix=""):
    """Centered PAGE field footer; used only by numbered sections."""
    section.footer.is_linked_to_previous = False
    p = section.footer.paragraphs[0]
    set_para_rtl(p, rtl)
    set_para_align(p, "center", rtl)
    if prefix:
        add_text(p, prefix, rtl, size=size, font="Times New Roman")
    add_field(p, "PAGE", "1", rtl, size=size, font="Times New Roman")


def clear_footer(section):
    """No page number on cover / approval / final covers."""
    section.footer.is_linked_to_previous = False
    p = section.footer.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)


def add_caption(container, text, *, kind="Figure", rtl=True, size=12):
    """Static caption, 12 pt bold. Figures below, tables above (caller decides).

    Numbering is written literally (e.g. 'الشكل (3-2) - الاسم') instead of using
    SEQ fields, so the printed document never shows an un-updated field.
    """
    style = "FigureCaption" if kind == "Figure" else "TableCaption"
    p = container.add_paragraph(style=style)
    set_para_rtl(p, rtl)
    set_para_align(p, "center", rtl)
    p.paragraph_format.keep_with_next = kind == "Table"
    p.paragraph_format.line_spacing = 1.15
    add_text(p, text, rtl, bold=True, size=size, font="Times New Roman")
    return p


def add_image(doc, path, *, width_twips=None, alt="", rtl=True):
    """Picture clamped to printable width, aspect ratio preserved, alt text set."""
    maxw = printable_width(doc)
    wt = min(width_twips or maxw, maxw)
    shape = doc.add_picture(str(path), width=Twips(wt))
    shape._inline.docPr.set("descr", alt)
    p = doc.paragraphs[-1]
    set_para_rtl(p, rtl)
    set_para_align(p, "center", rtl)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(6)
    return shape


def add_toc(doc, *, instr, title, hint, rtl=True):
    """TOC-style field (contents / tables / figures) with a localized hint."""
    if title:
        para(doc, title, rtl=rtl, bold=True, size=16, keep_next=True, space_after=8)
    p = para(doc, "", rtl=rtl)
    add_field(p, instr, "", rtl, size=12)
    runs = p.runs
    sep = [
        i for i, r in enumerate(runs)
        if r._r.find(qn("w:fldChar")) is not None
        and r._r.find(qn("w:fldChar")).get(qn("w:fldCharType")) == "separate"
    ][0]
    # Split the hint by script: a single run holding both would flip Latin tokens.
    placeholder = runs[sep + 1]._r
    for chunk, is_rtl in split_script_runs(hint, rtl):
        r = p.add_run(chunk)
        style_run(r, is_rtl, explicit_ltr=(rtl and not is_rtl), size=12)
        placeholder.addprevious(r._r)
    placeholder.getparent().remove(placeholder)
    add_update_fields(doc)
    return p


# ---------------------------------------------------------------------------
# 7. Tables
# ---------------------------------------------------------------------------
def shade_cell(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    drop(tcPr, "shd")
    shd = get_or_add(tcPr, "shd", TCPR_ORDER)
    shd.set(qn("w:val"), "clear")  # never "solid": renders black in Word
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill.lstrip("#").upper())


def fill_cell(cell, text, *, rtl=None, align="start", space=0, **fmt):
    """Write into a cell's first paragraph with explicit direction."""
    p = cell.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    if rtl is None:
        rtl = detect_rtl(text)
    set_para_rtl(p, rtl)
    set_para_align(p, align, rtl)
    p.paragraph_format.space_before = Pt(space)
    p.paragraph_format.space_after = Pt(space)
    p.paragraph_format.line_spacing = 1.0
    add_text(p, text, rtl, **fmt)
    return p


def add_table(doc, rows, widths=None, *, rtl=True, header=True, header_fill="D9E2F3",
              border="808080", pad=90, size=12, col_align=None):
    """rows in LOGICAL reading order (column 0 = first column; RTL puts it right)."""
    ncols = max(len(r) for r in rows)
    total = printable_width(doc)
    if widths:
        widths = list(widths)
        widths[-1] += total - sum(widths)
    else:
        widths = [total // ncols] * ncols
        widths[-1] += total - sum(widths)

    t = doc.add_table(rows=len(rows), cols=ncols)
    t.autofit = False
    tblPr = t._tbl.tblPr
    get_or_add(tblPr, "tblLayout", TBLPR_ORDER).set(qn("w:type"), "fixed")
    tblW = get_or_add(tblPr, "tblW", TBLPR_ORDER)
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(sum(widths)))
    set_flag(tblPr, "bidiVisual", TBLPR_ORDER, rtl)

    borders = get_or_add(tblPr, "tblBorders", TBLPR_ORDER)
    for ch in list(borders):
        borders.remove(ch)
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + side)
        for k, v in (("val", "single"), ("sz", "4"), ("space", "0"), ("color", border)):
            e.set(qn("w:" + k), v)
        borders.append(e)

    mar = get_or_add(tblPr, "tblCellMar", TBLPR_ORDER)
    for ch in list(mar):
        mar.remove(ch)
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + side)
        e.set(qn("w:w"), str(pad if side in ("left", "right") else 40))
        e.set(qn("w:type"), "dxa")
        mar.append(e)

    for i, w in enumerate(widths):
        t.columns[i].width = Twips(w)
    for ri, row in enumerate(rows):
        tr = t.rows[ri]
        trPr = tr._tr.get_or_add_trPr()
        etree.SubElement(trPr, qn("w:cantSplit"))
        if header and ri == 0:
            etree.SubElement(trPr, qn("w:tblHeader"))
        for ci in range(ncols):
            cell = tr.cells[ci]
            cell.width = Twips(widths[ci])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            txt = row[ci] if ci < len(row) else ""
            is_head = header and ri == 0
            al = "center" if is_head else (col_align[ci] if col_align else "start")
            fill_cell(cell, str(txt), rtl=cell_direction(str(txt), rtl),
                      align=al, bold=is_head, size=size, space=1)
            if is_head:
                shade_cell(cell, header_fill)
    return t


def set_cell_shading_table(table, fill="F2F2F2", skip_header=True):
    """Light zebra shading, applied after the table is built."""
    for ri, row in enumerate(table.rows):
        if skip_header and ri == 0:
            continue
        if ri % 2 == 0:
            for cell in row.cells:
                shade_cell(cell, fill)


# ---------------------------------------------------------------------------
# 8. Real Word lists (never fake bullets with manual "•" text)
# ---------------------------------------------------------------------------
_BULLETS = ["•", "◦", "▪"]


def new_list(doc, kind="bullet"):
    """Create a numbering instance; call again to restart numbering at 1."""
    root = doc.part.numbering_part.element
    aids = [int(e.get(qn("w:abstractNumId"))) for e in root.findall(qn("w:abstractNum"))]
    nids = [int(e.get(qn("w:numId"))) for e in root.findall(qn("w:num"))]
    aid, nid = max(aids + [-1]) + 1, max(nids + [0]) + 1

    ab = etree.SubElement(etree.Element("tmp"), qn("w:abstractNum"))
    ab.set(qn("w:abstractNumId"), str(aid))
    etree.SubElement(ab, qn("w:multiLevelType")).set(qn("w:val"), "hybridMultilevel")
    for lv in range(9):
        lvl = etree.SubElement(ab, qn("w:lvl"))
        lvl.set(qn("w:ilvl"), str(lv))
        etree.SubElement(lvl, qn("w:start")).set(qn("w:val"), "1")
        etree.SubElement(lvl, qn("w:numFmt")).set(qn("w:val"), "bullet" if kind == "bullet" else kind)
        etree.SubElement(lvl, qn("w:lvlText")).set(
            qn("w:val"), _BULLETS[lv % 3] if kind == "bullet" else f"%{lv + 1}."
        )
        etree.SubElement(lvl, qn("w:lvlJc")).set(qn("w:val"), "left")
        ppr = etree.SubElement(lvl, qn("w:pPr"))
        ind = etree.SubElement(ppr, qn("w:ind"))
        ind.set(qn("w:left"), str(720 * (lv + 1)))
        ind.set(qn("w:hanging"), "360")
        if kind == "bullet":
            rp = etree.SubElement(lvl, qn("w:rPr"))
            rf = etree.SubElement(rp, qn("w:rFonts"))
            for a in ("ascii", "hAnsi", "cs"):
                rf.set(qn("w:" + a), "Times New Roman")
            rf.set(qn("w:hint"), "default")

    first_num = root.find(qn("w:num"))
    if first_num is not None:
        first_num.addprevious(ab)
    else:
        root.append(ab)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(nid))
    etree.SubElement(num, qn("w:abstractNumId")).set(qn("w:val"), str(aid))
    tail = root.find(qn("w:numIdMacAtCleanup"))
    (tail.addprevious(num) if tail is not None else root.append(num))
    return nid


def list_item(container, text, num_id, level=0, *, rtl=True, **kw):
    """Paragraph belonging to list ``num_id`` at level 0-8."""
    p = para(container, text, rtl=rtl, **kw)
    pPr = p._p.get_or_add_pPr()
    numPr = get_or_add(pPr, "numPr", PPR_ORDER)
    for ch in list(numPr):
        numPr.remove(ch)
    etree.SubElement(numPr, qn("w:ilvl")).set(qn("w:val"), str(level))
    etree.SubElement(numPr, qn("w:numId")).set(qn("w:val"), str(num_id))
    return p


def paragraph_with_page_break(doc, *, rtl=True):
    """A nearly empty paragraph that only carries a page break."""
    p = doc.add_paragraph()
    set_para_rtl(p, rtl)
    run = p.add_run()
    from docx.enum.text import WD_BREAK

    run.add_break(WD_BREAK.PAGE)
    return p
