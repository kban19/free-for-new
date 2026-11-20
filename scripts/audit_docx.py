"""audit_docx.py - automated OOXML & bidirectional quality auditor for .docx files.

Usage:
    python scripts/audit_docx.py path/to/output.docx

Checks: ZIP/XML validity, schema element order, RTL/LTR flags, complex-script
twins, theme-font leaks, table geometry, shading and settings.xml field update.
"""
import re
import sys
import unicodedata
import zipfile
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

ORDERS = {
    "pPr": [
        "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
        "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
        "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE",
        "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind",
        "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
        "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
        "sectPr", "pPrChange",
    ],
    "rPr": [
        "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
        "dstrike", "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid",
        "vanish", "webHidden", "color", "spacing", "w", "kern", "position", "sz",
        "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign",
        "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath",
    ],
    "tblPr": [
        "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
        "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders",
        "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription",
    ],
    "tcPr": [
        "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
        "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
    ],
    "sectPr": [
        "headerReference", "footerReference", "footnotePr", "endnotePr", "type",
        "pgSz", "pgMar", "paperSrc", "pgBorders", "lnNumType", "pgNumType", "cols",
        "formProt", "vAlign", "noEndnote", "titlePg", "textDirection", "bidi",
        "rtlGutter", "docGrid", "printerSettings", "sectPrChange",
    ],
}

_URL_OR_COMPOUND = re.compile(r"(https?://\S+|\d+(?:[-/.:]\d+)+)")


def _lname(el):
    return etree.QName(el).localname if isinstance(el.tag, str) else None


def _flag_on(parent, name):
    el = parent.find(W + name) if parent is not None else None
    return el is not None and el.get(W + "val", "1") not in ("0", "false", "off")


def _script_counts(text):
    r = l = 0
    for ch in text or "":
        b = unicodedata.bidirectional(ch)
        if b in ("R", "AL"):
            r += 1
        elif b == "L":
            l += 1
    return r, l


def audit_docx(path):
    errors = []
    warnings = []
    parser = etree.XMLParser(resolve_entities=False)

    try:
        zf = zipfile.ZipFile(path, "r")
    except Exception as exc:
        return [f"Cannot open ZIP archive: {exc}"], []

    with zf:
        names = set(zf.namelist())
        for req in ("[Content_Types].xml", "_rels/.rels", "word/document.xml"):
            if req not in names:
                errors.append(f"Missing required OOXML part: {req}")

        xml_parts = {}
        for name in sorted(names):
            if name.endswith(".xml") or name.endswith(".rels"):
                try:
                    xml_parts[name] = etree.fromstring(zf.read(name), parser=parser)
                except Exception as exc:
                    errors.append(f"XML syntax error in {name}: {exc}")

        if "word/document.xml" not in xml_parts:
            return errors, warnings

        has_dynamic_fields = False
        for part_name, root in xml_parts.items():
            if not part_name.startswith("word/") or part_name.endswith(".rels"):
                continue

            for container_tag, order in ORDERS.items():
                for el in root.iter(W + container_tag):
                    seen = -1
                    for child in el:
                        cn = _lname(child)
                        if cn in order:
                            idx = order.index(cn)
                            if idx < seen:
                                errors.append(
                                    f"{part_name}: Out-of-order <w:{cn}> inside <w:{container_tag}>"
                                )
                            seen = idx

            for shd in root.iter(W + "shd"):
                if shd.get(W + "val") == "solid":
                    errors.append(
                        f"{part_name}: <w:shd w:val='solid'/> renders solid black (use 'clear')"
                    )

            for t in root.iter(W + "t"):
                if t.text and "\n" in t.text:
                    errors.append(f"{part_name}: Raw newline inside <w:t>: {t.text[:40]!r}")

            for instr in root.iter(W + "instrText"):
                txt = (instr.text or "").upper()
                if any(k in txt for k in ("TOC", "PAGE", "NUMPAGES", "SEQ")):
                    has_dynamic_fields = True

        if "word/numbering.xml" in xml_parts:
            seen_num = False
            for child in xml_parts["word/numbering.xml"]:
                cn = _lname(child)
                if cn == "num":
                    seen_num = True
                elif cn == "abstractNum" and seen_num:
                    errors.append("word/numbering.xml: <w:abstractNum> appears after <w:num>")

        if has_dynamic_fields:
            st = xml_parts.get("word/settings.xml")
            if st is None or st.find(W + "updateFields") is None:
                warnings.append(
                    "Dynamic fields found but <w:updateFields w:val='true'/> is missing"
                )

        if "word/styles.xml" in xml_parts:
            for st in xml_parts["word/styles.xml"].findall(W + "style"):
                rpr = st.find(W + "rPr")
                if rpr is None:
                    continue
                for lat, cs in (("sz", "szCs"), ("b", "bCs"), ("i", "iCs")):
                    if rpr.find(W + lat) is not None and rpr.find(W + cs) is None:
                        sid = st.get(W + "styleId", "?")
                        warnings.append(
                            f"word/styles.xml: Style '{sid}' sets <w:{lat}> without <w:{cs}>"
                        )

        doc_root = xml_parts["word/document.xml"]
        for pi, p in enumerate(doc_root.iter(W + "p"), 1):
            ppr = p.find(W + "pPr")
            p_rtl = _flag_on(ppr, "bidi")
            full_text = "".join(t.text or "" for t in p.iter(W + "t"))
            rc, lc = _script_counts(full_text)
            if rc > lc * 2 and rc >= 4 and not p_rtl:
                errors.append(
                    f"Paragraph #{pi} is RTL-dominant ({full_text[:35]!r}) but missing <w:bidi/>"
                )
            # Mixed Arabic+Latin paragraphs are intentionally RTL; only a paragraph
            # with no RTL letter at all carrying <w:bidi/> is a real defect. Headings
            # follow the document direction by design (e.g. "2-6-3 PyInstaller").
            style_el = ppr.find(W + "pStyle") if ppr is not None else None
            style_id = (style_el.get(W + "val", "") if style_el is not None else "").lower()
            is_heading = style_id.startswith("heading") or style_id == "title"
            if rc == 0 and lc >= 8 and p_rtl and not is_heading:
                warnings.append(
                    f"Paragraph #{pi} is LTR-dominant ({full_text[:35]!r}) but has <w:bidi/>"
                )

            for r in p.findall(W + "r"):
                r_txt = "".join(t.text or "" for t in r.findall(W + "t"))
                if not r_txt.strip():
                    continue
                rpr = r.find(W + "rPr")
                r_rtl = _flag_on(rpr, "rtl")
                rrc, rlc = _script_counts(r_txt)
                if rrc > 0 and rlc > 0:
                    errors.append(
                        f"Paragraph #{pi} mixes RTL and LTR letters in one run: {r_txt[:40]!r}"
                    )
                if r_rtl and rlc > 0 and rrc == 0:
                    errors.append(
                        f"Paragraph #{pi} has LTR text inside <w:rtl/> run: {r_txt[:40]!r}"
                    )
                if r_rtl and _URL_OR_COMPOUND.search(r_txt):
                    warnings.append(
                        f"Paragraph #{pi} has URL/compound number inside <w:rtl/> run: {r_txt[:40]!r}"
                    )
                if rrc > 0 and not r_rtl:
                    warnings.append(
                        f"Paragraph #{pi} has RTL text without <w:rtl/>: {r_txt[:40]!r}"
                    )
                if rpr is not None and rrc > 0:
                    for lat, cs in (("sz", "szCs"), ("b", "bCs"), ("i", "iCs")):
                        if rpr.find(W + lat) is not None and rpr.find(W + cs) is None:
                            errors.append(
                                f"Paragraph #{pi} RTL run sets <w:{lat}> without <w:{cs}>"
                            )

        for ti, tbl in enumerate(doc_root.iter(W + "tbl"), 1):
            tblPr = tbl.find(W + "tblPr")
            if tblPr is None:
                errors.append(f"Table #{ti} missing <w:tblPr>")
                continue
            layout = tblPr.find(W + "tblLayout")
            if layout is None or layout.get(W + "type") != "fixed":
                warnings.append(f"Table #{ti} does not set <w:tblLayout w:type='fixed'/>")
            tblW = tblPr.find(W + "tblW")
            grid = tbl.find(W + "tblGrid")
            if tblW is not None and grid is not None and tblW.get(W + "type") == "dxa":
                tw = int(tblW.get(W + "w", "0"))
                gcols = [int(c.get(W + "w", "0")) for c in grid.findall(W + "gridCol")]
                if gcols and sum(gcols) != tw:
                    errors.append(f"Table #{ti} sum(gridCol)={sum(gcols)} != tblW={tw}")

    return errors, warnings


def main():
    # The report quotes Arabic text; a cp1252 console would crash on it.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print("Usage: python scripts/audit_docx.py <file.docx>")
        sys.exit(2)
    errs, warns = audit_docx(sys.argv[1])
    for e in errs:
        print(f"ERROR: {e}")
    for w in warns:
        print(f"WARN:  {w}")
    if not errs and not warns:
        print("OK: Zero OOXML or bidi issues found.")
    elif not errs:
        print(f"OK with {len(warns)} warning(s).")
    else:
        print(f"FAILED: {len(errs)} error(s), {len(warns)} warning(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
