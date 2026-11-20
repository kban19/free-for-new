"""Build the complete Rojava-format thesis .docx from verified repository data.

Charts are generated from docs/performance_data.json and the raw smoke log so
every number in the document is traceable. Nothing here invents a measurement.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx.enum.section import WD_SECTION  # noqa: E402

import docx_bidi as D  # noqa: E402
import thesis_common as T  # noqa: E402
import thesis_front  # noqa: E402
import thesis_ch1  # noqa: E402
import thesis_ch2  # noqa: E402
import thesis_ch3  # noqa: E402
import thesis_ch4  # noqa: E402
import thesis_back  # noqa: E402

OUT = ROOT / "docs" / "Kurmanji-TTS_Thesis_Rojava.docx"
CHART_DIR = ROOT / "docs" / "assets" / "thesis"
SMOKE = ROOT / "docs" / "smoke_results_2026-11-20.txt"

ROW_RE = re.compile(
    r"^(?P<name>\w+)\s+mode=(?P<mode>\S+)\s+spk=\s*(?P<spk>\d+)\s+"
    r"chars=\s*(?P<chars>\d+)\s+audio=\s*(?P<audio>[\d.]+)s\s+"
    r"gen=\s*(?P<gen>[\d.]+)s\s+RTF=\s*(?P<rtf>[\d.]+)"
)


def load_perf() -> dict:
    return json.loads((ROOT / "docs" / "performance_data.json").read_text(encoding="utf-8"))


def load_smoke() -> list:
    """Parse the raw smoke log; never fabricate a row if the file is missing."""
    rows = []
    if not SMOKE.exists():
        return rows
    for line in SMOKE.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line.strip())
        if m:
            rows.append({
                "name": m["name"],
                "chars": int(m["chars"]),
                "audio": float(m["audio"]),
                "gen": float(m["gen"]),
                "rtf": float(m["rtf"]),
                "engine": "piper" if m["mode"].startswith(("oneshot", "persistent"))
                else "mms_ara" if "ara" in m["name"] else "mms_kmr",
            })
    return rows


def _series(rows, prefix):
    pts = [(r["chars"], r["gen"]) for r in rows if r["name"].startswith(prefix)]
    return sorted(pts)


def _save(fig, name: str) -> Path:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / name
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def make_charts(perf: dict, rows: list) -> dict:
    plt.rcParams.update({
        "font.size": 10,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    figs = {
        "arch": ROOT / "docs" / "assets" / "architecture_hybrid.png",
        "pipeline": ROOT / "docs" / "assets" / "pipeline_hybrid.png",
        "vits": ROOT / "docs" / "assets" / "vits_flow.png",
    }

    # ---- Figure 4-1: generation time vs text length
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    for prefix, label, style in (
        ("oneshot_", "Piper (single call)", "o-"),
        ("persist_", "Piper (warm process)", "s-"),
        ("mms_", "Meta MMS (kmr / ara)", "^-"),
    ):
        pts = _series(rows, prefix)
        if pts:
            xs, ys = zip(*pts)
            ax.plot(xs, ys, style, label=label, linewidth=1.8, markersize=6)
    ax.set_xlabel("Input length (characters)")
    ax.set_ylabel("Generation time (seconds)")
    ax.set_title("Generation time versus input length", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    figs["gen"] = _save(fig, "fig_4_1_generation_time.png")

    # ---- Figure 4-2: RTF per measured case
    cases = [r for r in rows if r["name"] in (
        "oneshot_short_spk54", "oneshot_medium_spk54", "oneshot_long_spk3",
        "persist_short_spk54", "persist_medium_spk54", "persist_long_spk3",
        "mms_kmr_short", "mms_ara_arabic", "mms_kmr_long", "mms_ara_long")]
    if cases:
        labels = [c["name"].replace("_spk54", "").replace("_spk3", "")
                  .replace("_arabic", "") for c in cases]
        values = [c["rtf"] for c in cases]
        colors = ["#8C5A2E" if c["engine"].startswith("mms") else "#2E5E8C"
                  for c in cases]
        fig, ax = plt.subplots(figsize=(7.4, 3.9))
        bars = ax.bar(range(len(cases)), values, color=colors)
        ax.set_xticks(range(len(cases)))
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax.axhline(1.0, color="#B00020", linestyle="--", linewidth=1)
        ax.text(len(cases) - 0.5, 1.03, "real time", color="#B00020",
                fontsize=8, ha="right")
        for b, v in zip(bars, values):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}",
                    ha="center", fontsize=8)
        ax.set_ylabel("Real-time factor (lower is faster)")
        ax.set_title("RTF for every measured case (2026-11-20)", fontsize=11)
        figs["rtf"] = _save(fig, "fig_4_2_rtf.png")

    # ---- Figure 4-3: model sizes and measured memory
    sizes = [
        ("piper model", 77_231_312 / 1024 / 1024),
        ("mms_kmr model", 114_014_648 / 1024 / 1024),
        ("mms_ara model", 114_017_720 / 1024 / 1024),
    ]
    memory = [
        ("Piper worker", perf["memory"]["piper_worker_mb"]),
        ("Peak, short text", perf["memory"]["peak_rss_mb_short_inputs"]),
        ("Peak, long mms_kmr", perf["memory"]["peak_rss_mb_long_mms_kmr"]),
        ("Peak, long mms_ara", perf["memory"]["peak_rss_mb_long_mms_ara"]),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.4))
    for ax, data, title, color in (
        (axes[0], sizes, "Model file size (MB)", "#2E5E8C"),
        (axes[1], memory, "Measured memory (MB)", "#8C5A2E"),
    ):
        labels = [d[0] for d in data]
        values = [d[1] for d in data]
        bars = ax.barh(range(len(data)), values, color=color)
        ax.set_yticks(range(len(data)))
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        for b, v in zip(bars, values):
            ax.text(v + 2, b.get_y() + b.get_height() / 2, f"{v:.1f}",
                    va="center", fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.set_xlim(0, max(values) * 1.22)
    fig.tight_layout()
    figs["res"] = _save(fig, "fig_4_3_resources.png")
    return figs


def estimate_pages(doc) -> int:
    """Rough page estimate: body text at ~1500 chars/page + tables and figures."""
    chars = sum(len(p.text) for p in doc.paragraphs)
    tables = len(doc.tables)
    figures = sum(1 for p in doc.paragraphs
                  if p._p.findall(".//{http://schemas.openxmlformats.org/"
                                  "drawingml/2006/main}blip"))
    return math.ceil(chars / 1500) + math.ceil(tables * 0.45) + figures


def main() -> None:
    perf = load_perf()
    rows = load_smoke()
    figs = make_charts(perf, rows)

    doc = D.setup_document()
    T.ensure_styles(doc)

    ctx = {"perf": perf, "figs": figs, "chapter": 0, "table_no": 0, "fig_no": 0}

    thesis_front.build_front_matter(doc, ctx)

    # Main body: decimal numbering restarting at 1, Arabic margins and direction.
    body = doc.add_section(WD_SECTION.NEW_PAGE)
    D.set_margins(body, rtl=True)
    D.set_section_direction(body, rtl=True)
    D.set_page_numbering(body, "decimal", 1)
    D.add_footer_page_number(body, rtl=True)

    for module in (thesis_ch1, thesis_ch2, thesis_ch3, thesis_ch4):
        module.build(doc, ctx)

    thesis_back.build_references(doc, ctx)
    thesis_back.build_appendices(doc, ctx)
    thesis_back.build_abstract_en(doc, ctx)
    thesis_back.build_abstract_ku(doc, ctx)
    thesis_back.build_final_covers(doc, ctx)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)

    pages = estimate_pages(doc)
    print(f"OK -> {OUT}")
    print(f"size            : {OUT.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"paragraphs      : {len(doc.paragraphs)}")
    print(f"tables          : {len(doc.tables)}")
    print(f"smoke rows used : {len(rows)}")
    print(f"page estimate   : ~{pages} pages")


if __name__ == "__main__":
    main()
