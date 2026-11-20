# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""Application constants, cross-platform path resolution and settings persistence.

This module is the single source of truth for every path the app touches. It is
the only place that knows how a frozen PyInstaller build finds its own folder,
and the only place that decides where ``settings.json`` lives. Every other
module asks ``config`` instead of guessing a relative path, which is exactly what
keeps the packaged ``.exe`` working once the source tree is gone.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional


APP_NAME = "Kurmanji-TTS"
APP_VERSION = "1.0.0"
DEFAULT_SPEAKER_ID = 54
KURMANJI_MODEL_FILENAME = "model.onnx"
MMS_KMR_MODEL_FILENAME = "mms_kmr/model.onnx"
MMS_ARA_MODEL_FILENAME = "mms_ara/model.onnx"
ENGINE_PROFILES = ("piper_kmr", "mms_kmr", "mms_ara")


def get_app_root() -> Path:
    """Return the application root, whether running from source or a frozen build.

    A frozen build unpacks its Python modules into a temporary folder, so
    ``Path(__file__).parent`` would point at a throw-away directory. Using the
    executable's own folder is what lets ``models/`` and ``piper/`` sit next to
    ``Kurmanji-TTS.exe`` after packaging.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_user_config_dir() -> Path:
    """Return a writable per-user configuration directory across Windows and Linux."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    cfg_dir = base / "kurmanji-tts"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def discover_default_model(models_dir: Path) -> Path:
    """Prefer the Kurmanji model; fall back to the first .onnx model present."""
    canonical = models_dir / KURMANJI_MODEL_FILENAME
    if canonical.exists():
        return canonical
    if models_dir.exists():
        onnx_files = sorted(models_dir.glob("*.onnx"))
        if onnx_files:
            return onnx_files[0]
    return models_dir / "kurmanci.onnx"


def model_path_for_voice(root: Path, tts_language: str) -> Path:
    """Return the ONNX model path for the selected speech language."""
    file_name = MMS_ARA_MODEL_FILENAME if tts_language == "ar" else KURMANJI_MODEL_FILENAME
    return root / "models" / file_name


def model_path_for_profile(root: Path, engine_profile: str) -> Path:
    """Return the ONNX model path for a unified engine profile."""
    file_name = {
        "piper_kmr": KURMANJI_MODEL_FILENAME,
        "mms_kmr": MMS_KMR_MODEL_FILENAME,
        "mms_ara": MMS_ARA_MODEL_FILENAME,
    }.get(engine_profile, KURMANJI_MODEL_FILENAME)
    return root / "models" / file_name


def load_speaker_labels(metadata_path: Path) -> Dict[int, str]:
    """Load optional human-friendly speaker labels (M/F/voice + default marker)."""
    labels: Dict[int, str] = {}
    try:
        raw = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return labels
    for entry in raw:
        try:
            sid = int(entry["speaker_id"])
            name = str(entry.get("display_name", f"Speaker {sid}"))
            voice = str(entry.get("perceived_voice", "")).strip()
            label = name if not voice else f"{name} ({voice})"
            if entry.get("is_default"):
                label += " ★"
            labels[sid] = label
        except (KeyError, TypeError, ValueError):
            continue
    return labels


def discover_default_piper(piper_dir: Path) -> Path:
    """Resolve the Piper executable path for Windows or Linux."""
    system = platform.system()
    if system == "Windows":
        candidates = [
            piper_dir / "windows" / "piper.exe",
            piper_dir / "piper.exe",
        ]
    else:
        candidates = [
            piper_dir / "linux" / "piper",
            piper_dir / "piper",
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    system_piper = shutil.which("piper")
    if system_piper:
        return Path(system_piper)

    return candidates[0]


def _safe_settings_version(raw: dict) -> int:
    """Read ``settings_version`` defensively; a corrupted value means "oldest"."""
    try:
        return int(raw.get("settings_version", 1))
    except (TypeError, ValueError):
        return 1


def _migrate_noise_defaults(raw: dict) -> None:
    """v1 -> v2: swap the model's stock noise values for the tuned defaults.

    Only the untouched stock numbers are rewritten, so a user who deliberately
    picked other values keeps them.
    """
    try:
        if abs(float(raw.get("noise_scale", 0.52)) - 0.52) < 1e-9:
            raw["noise_scale"] = 0.35
        if abs(float(raw.get("noise_w", 0.58)) - 0.58) < 1e-9:
            raw["noise_w"] = 0.45
    except (TypeError, ValueError):
        pass
    raw["settings_version"] = 2


def _migrate_length_scale_to_speed(raw: dict) -> None:
    """v2 -> v3: v2 stored Piper's ``length_scale``; the UI now stores speed.

    ``length_scale`` is the inverse of speed (a longer scale is a slower voice),
    so the old value is inverted once here and then dropped for good.
    """
    old_length_scale = raw.pop("length_scale", None)
    if old_length_scale is not None:
        try:
            old_value = float(old_length_scale)
            if old_value > 0:
                raw["speech_speed"] = max(0.5, min(1.5, round(1.0 / old_value, 3)))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    raw["settings_version"] = 3


def _migrate_engine_profile(raw: dict) -> None:
    """Derive ``engine_profile`` for builds that only stored a speech language."""
    if "engine_profile" not in raw:
        raw["engine_profile"] = "mms_ara" if raw.get("tts_language") == "ar" else "piper_kmr"


def _migrate_ui_language(raw: dict) -> None:
    """v3 -> v4: Arabic was the only interface language before v4."""
    raw.setdefault("ui_language", "ar")
    raw["settings_version"] = 4


def migrate_settings(raw: dict) -> dict:
    """Upgrade an on-disk settings dict to the current schema, step by step.

    Each version jump is its own small function so a reviewer can read the file
    format's history in order. The version is read once, before any change, so
    a very old file still passes through every intermediate step.
    """
    version = _safe_settings_version(raw)
    if version < 2:
        _migrate_noise_defaults(raw)
    if version < 3:
        _migrate_length_scale_to_speed(raw)
    _migrate_engine_profile(raw)
    if version < 4:
        _migrate_ui_language(raw)
    return raw


@dataclass
class AppSettings:
    """Persistent user and engine settings for Kurmanji-TTS."""

    model_path: str = ""
    piper_path: str = ""
    default_speaker_id: int = DEFAULT_SPEAKER_ID
    speech_speed: float = 1.0
    noise_scale: float = 0.35
    noise_w: float = 0.45
    theme_mode: str = "dark"
    use_persistent_process: bool = True
    max_text_length: int = 5000
    ui_language: str = "ar"
    tts_language: str = "ku"
    engine_profile: str = "piper_kmr"
    settings_version: int = 4

    @property
    def length_scale(self) -> float:
        """Piper phoneme length (inverse of the UI speed)."""
        return round(1.0 / self.speech_speed, 3)

    def __post_init__(self) -> None:
        root = get_app_root()
        if not self.model_path:
            self.model_path = str(discover_default_model(root / "models"))
        if not self.piper_path:
            self.piper_path = str(discover_default_piper(root / "piper"))
        self.speech_speed = max(0.5, min(1.5, float(self.speech_speed)))
        self.noise_scale = max(0.0, min(1.5, float(self.noise_scale)))
        self.noise_w = max(0.0, min(1.5, float(self.noise_w)))
        if self.theme_mode not in ("dark", "light"):
            self.theme_mode = "dark"
        if self.ui_language not in ("ar", "ku", "en"):
            self.ui_language = "ar"
        if self.tts_language not in ("ku", "ar"):
            self.tts_language = "ku"
        if self.engine_profile not in ENGINE_PROFILES:
            self.engine_profile = "piper_kmr"

    @classmethod
    def load(cls, config_file: Optional[Path] = None) -> "AppSettings":
        """Load settings from disk, or return validated defaults.

        A missing, unreadable or half-written ``settings.json`` must never stop
        the app from starting, so every failure path falls back to ``cls()``.
        Unknown keys written by a newer build are dropped instead of crashing
        the dataclass constructor.
        """
        target = config_file or (get_user_config_dir() / "settings.json")
        if not target.exists():
            return cls()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return cls()
            migrate_settings(raw)
            valid_keys = {field.name for field in cls.__dataclass_fields__.values()}
            return cls(**{key: value for key, value in raw.items() if key in valid_keys})
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return cls()

    def save(self, config_file: Optional[Path] = None) -> Path:
        """Persist current settings to disk in UTF-8 JSON."""
        target = config_file or (get_user_config_dir() / "settings.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return target
