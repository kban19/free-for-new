# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""Application configuration, cross-platform path resolution, and settings persistence."""

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
    """Return the root directory of the application (supports frozen PyInstaller builds)."""
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
        """Load settings from disk or return validated defaults."""
        target = config_file or (get_user_config_dir() / "settings.json")
        if target.exists():
            try:
                raw = json.loads(target.read_text(encoding="utf-8"))
                try:
                    version = int(raw.get("settings_version", 1))
                except (TypeError, ValueError):
                    version = 1
                if version < 2:
                    # v1 stored the model's generic voice settings. Upgrade only
                    # those exact values; preserve any user-customised tweaks.
                    try:
                        if abs(float(raw.get("noise_scale", 0.52)) - 0.52) < 1e-9:
                            raw["noise_scale"] = 0.35
                        if abs(float(raw.get("noise_w", 0.58)) - 0.58) < 1e-9:
                            raw["noise_w"] = 0.45
                    except (TypeError, ValueError):
                        pass
                    raw["settings_version"] = 2
                if version < 3:
                    # v2 stored Piper's length_scale directly as the "speed".
                    # Convert it to the inverse speech speed used by the UI.
                    old_length_scale = raw.get("length_scale")
                    if old_length_scale is not None:
                        try:
                            old_value = float(old_length_scale)
                            if old_value > 0:
                                raw["speech_speed"] = max(
                                    0.5, min(1.5, round(1.0 / old_value, 3))
                                )
                        except (TypeError, ValueError, ZeroDivisionError):
                            pass
                    raw.pop("length_scale", None)
                    raw["settings_version"] = 3
                if "engine_profile" not in raw:
                    # Earlier builds stored only the speech language.
                    raw["engine_profile"] = (
                        "mms_ara" if raw.get("tts_language") == "ar" else "piper_kmr"
                    )
                if version < 4:
                    # v3 had no explicit UI language; Arabic was the only UI.
                    raw.setdefault("ui_language", "ar")
                    raw["settings_version"] = 4
                valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
                filtered = {k: v for k, v in raw.items() if k in valid_keys}
                return cls(**filtered)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
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
