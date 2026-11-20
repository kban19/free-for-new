"""Opt-in smoke test against the REAL Piper CLI and Kurmanji ONNX model.

Run ``python setup_runtime.py`` first. Then::

    python tests/real_engine_smoke.py

Unlike test_kurmanji_tts.py, this script never uses mock_piper.
"""

from __future__ import annotations

import ctypes
import math
import sys
import time
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import AppSettings
from text_utils import (
    KURMANJI_SPECIAL_CHARS,
    SAMPLE_KURMANJI_TEXTS,
    analyze_text,
    prepare_text_for_mms,
    prepare_text_for_tts,
)
from tts_engine import KurmanjiTTSEngine, UnifiedTTSEngine

OUT_DIR = Path(__file__).resolve().parent / "real_output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HAWAR_SENTENCE = "Ç ç Ê ê Î î Ş ş Û û X x W w - ev hemû tîpên Hawarê ne."
SHORT = "Rojbaş! " + HAWAR_SENTENCE
MEDIUM = (
    "Zimanê kurdî yek ji zimanên kevnar ên Rojhilata Navîn e. "
    "Zaravayê kurmancî bi alfabeya latînî ya Hawarê tê nivîsandin. "
) + HAWAR_SENTENCE
LONG = SAMPLE_KURMANJI_TEXTS["Paragrafa Dirêj (Long)"] + " " + HAWAR_SENTENCE
LONG = (LONG + " ") * 2
ARABIC_TEXT = (
    "مرحباً، هذا اختبار لتوليد الصوت باللغة العربية الفصحى. "
    "السنة الحالية هي 2026، والنص يحتفظ بعلامات التشكيل."
)
# The worst case recorded in docs/performance_data.json: one long paragraph per
# MMS voice, because those two models are the slowest part of the project.
LONG_AR = (ARABIC_TEXT + " ") * 8


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _memory_counters(pid: int | None = None):
    """Return Windows memory counters for a PID (or the current process)."""
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel32.GetCurrentProcess() if pid is None else kernel32.OpenProcess(
        0x0400 | 0x0010, False, pid
    )
    if not handle:
        return None
    getter = getattr(ctypes.windll.kernel32, "K32GetProcessMemoryInfo", None) or \
        ctypes.windll.psapi.GetProcessMemoryInfo
    getter.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    getter.restype = wintypes.BOOL
    counters = _PMC()
    counters.cb = ctypes.sizeof(_PMC)
    if not getter(handle, ctypes.byref(counters), counters.cb):
        return None
    return counters


def peak_rss_mb() -> float:
    """Peak working set of the current process, in MB (Windows / POSIX)."""
    if sys.platform == "win32":
        try:
            counters = _memory_counters()
            return counters.PeakWorkingSetSize / (1024 * 1024) if counters else 0.0
        except Exception:
            return 0.0
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except ImportError:
        return 0.0


def worker_rss_mb(pid: int) -> float:
    """Current working set of the warm Piper worker, in MB."""
    if sys.platform != "win32":
        return 0.0
    try:
        counters = _memory_counters(pid)
        return counters.WorkingSetSize / (1024 * 1024) if counters else 0.0
    except Exception:
        return 0.0


def audio_rms(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        sw = wf.getsampwidth()
    if sw == 2:
        samples = [int.from_bytes(raw[i:i + 2], "little", signed=True)
                   for i in range(0, len(raw) - 1, 2)]
    elif sw == 4:
        samples = [int.from_bytes(raw[i:i + 4], "little", signed=True) >> 8
                   for i in range(0, len(raw) - 3, 4)]
    else:
        samples = [b - 128 for b in raw]
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def run_case(engine, name, text, sid, persistent, ls=None):
    out = OUT_DIR / f"{name}.wav"
    kwargs = {}
    if ls is not None:
        kwargs["length_scale"] = ls
    result = engine.synthesize(text=text, output_wav=out, speaker_id=sid, **kwargs)
    rms = audio_rms(out)
    with wave.open(str(out), "rb") as wf:
        channels, rate, frames = wf.getnchannels(), wf.getframerate(), wf.getnframes()
    analysis = analyze_text(text)
    missing = [c for c in KURMANJI_SPECIAL_CHARS if c not in analysis.special_chars_found]
    print(
        f"{name:24s} mode={result.mode_used:19s} spk={result.speaker_id:2d} "
        f"chars={result.text_length:4d} audio={result.duration_seconds:6.2f}s "
        f"gen={result.generation_time_seconds:5.2f}s RTF={result.real_time_factor:5.2f} "
        f"{rate}Hz ch={channels} RMS={rms:7.1f} size={out.stat().st_size / 1024:7.1f}KB "
        f"hawar_missing={missing}"
    )
    assert rms > 50, f"{name} looks silent (RMS={rms})"
    assert not missing, f"{name} missing Hawar chars: {missing}"
    return result


def run_mms_case(profile: str, text: str, label: str) -> None:
    """Synthesize one of the Meta MMS voices through the unified engine."""
    settings = AppSettings()
    engine = UnifiedTTSEngine(
        piper_path=Path(settings.piper_path),
        model_path=Path(settings.model_path),
        root=PROJECT_ROOT,
        engine_profile=profile,
    )
    status = engine.check_status()
    print(f"\n--- MMS {profile} ---")
    print(f"STATUS ready={status.ready} :: {status.message}")
    assert status.ready and status.metadata is not None

    prepared = prepare_text_for_mms(text, "ar" if profile == "mms_ara" else "kmr")
    out = OUT_DIR / f"{label}.wav"
    result = engine.synthesize(text=prepared, output_wav=out, speaker_id=0)
    rms = audio_rms(out)
    with wave.open(str(out), "rb") as wf:
        rate = wf.getframerate()
    print(
        f"{label:24s} mode={result.mode_used:19s} spk={result.speaker_id:2d} "
        f"chars={result.text_length:4d} audio={result.duration_seconds:6.2f}s "
        f"gen={result.generation_time_seconds:5.2f}s RTF={result.real_time_factor:5.2f} "
        f"{rate}Hz RMS={rms:7.1f} size={out.stat().st_size / 1024:7.1f}KB"
    )
    assert rms > 50, f"{label} looks silent (RMS={rms})"
    assert rate == 16000, f"Unexpected MMS sample rate: {rate}"
    engine.close()


def main() -> None:
    if "--mms-long" in sys.argv:
        # Only the long MMS case(s); used to refresh the rows in
        # docs/performance_data.json without re-timing the whole Piper sweep.
        # Pass one profile to measure it alone, so peak RSS reflects a single
        # loaded model exactly like the running application.
        index = sys.argv.index("--mms-long")
        only = sys.argv[index + 1] if len(sys.argv) > index + 1 else ""
        if only in ("", "mms_kmr"):
            run_mms_case("mms_kmr", LONG, "mms_kmr_long")
        if only in ("", "mms_ara"):
            run_mms_case("mms_ara", LONG_AR, "mms_ara_long")
        print(f"PYTHON PEAK RSS: {peak_rss_mb():.2f} MB")
        return

    settings = AppSettings()
    engine = KurmanjiTTSEngine(
        piper_path=Path(settings.piper_path),
        model_path=Path(settings.model_path),
        preferred_speaker=settings.default_speaker_id,
        use_persistent_process=False,
    )
    status = engine.check_status()
    print(f"STATUS ready={status.ready} :: {status.message}")
    meta = status.metadata
    print(
        f"MODEL {meta.model_path.name} | {meta.model_size_mb}MB | {meta.sample_rate}Hz | "
        f"speakers={meta.num_speakers} | default={meta.default_speaker_id} | "
        f"defaults L={meta.inference_length_scale} N={meta.inference_noise_scale} "
        f"W={meta.inference_noise_w}"
    )
    assert status.ready

    print("\n--- ONE-SHOT CLI ---")
    for name, text, sid in [
        ("oneshot_short_spk54", SHORT, 54),
        ("oneshot_medium_spk54", MEDIUM, 54),
        ("oneshot_long_spk3", LONG, 3),
    ]:
        run_case(engine, name, text, sid, persistent=False)

    print("\n--- PERSISTENT JSON CLI ---")
    engine.update_paths(
        piper_path=Path(settings.piper_path),
        model_path=Path(settings.model_path),
        preferred_speaker=54,
        use_persistent_process=True,
    )
    for name, text, sid in [
        ("persist_short_spk54", SHORT, 54),
        ("persist_medium_spk54", MEDIUM, 54),
        ("persist_long_spk3", LONG, 3),
    ]:
        res = run_case(engine, name, text, sid, persistent=True)
        assert res.mode_used == "persistent-json-cli", res.mode_used

    print("\n--- LENGTH SCALE HONOURED IN PERSISTENT MODE ---")
    slow = run_case(engine, "persist_ls060", MEDIUM, 54, persistent=True, ls=0.6)
    fast = run_case(engine, "persist_ls150", MEDIUM, 54, persistent=True, ls=1.5)
    # In Piper, a larger length_scale means longer phonemes -> longer audio.
    ratio = fast.duration_seconds / slow.duration_seconds
    print(f"duration ratio ls=1.5 / ls=0.6 = {ratio:.3f} (expected > 1.5)")
    assert ratio > 1.5, "length_scale still ignored in persistent mode"

    worker_pid = engine._proc.pid if engine._proc is not None else None
    print(f"\nPIPER WORKER PID: {worker_pid} | Working set: "
          f"{worker_rss_mb(worker_pid) if worker_pid else 0:.2f} MB")
    engine.close()

    run_mms_case("mms_kmr", SHORT, "mms_kmr_short")
    run_mms_case("mms_ara", ARABIC_TEXT, "mms_ara_arabic")
    print(f"PYTHON PEAK RSS: {peak_rss_mb():.2f} MB")


if __name__ == "__main__":
    main()
