# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""One-time runtime fetcher for the Piper binary and the three speech models.

This script is the only part of the project that touches the network, and it
runs once per machine. Afterwards the app is fully offline: ``models/`` and
``piper/`` hold everything the engines need, which is why the packaged ``.exe``
never asks for a connection again.
"""

from __future__ import annotations

import json
import platform
import shutil
import ssl
import stat
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from config import get_app_root
from tts_engine import parse_model_metadata

# Some Python distributions (e.g. MSYS2 on Windows) ship without a configured
# CA bundle, which makes urllib fail with CERTIFICATE_VERIFY_FAILED. pip brings
# certifi along, so prefer its bundle when available.
try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover - fall back to OS trust store
    _SSL_CONTEXT = None


def _urlopen(request: urllib.request.Request, timeout: int = 120):
    """Open an HTTPS URL using a reliable CA bundle when one is available."""
    if _SSL_CONTEXT is not None:
        return urllib.request.urlopen(request, timeout=timeout, context=_SSL_CONTEXT)
    return urllib.request.urlopen(request, timeout=timeout)

PIPER_RELEASE_TAG = "2023.11.14-2"
PIPER_URLS = {
    "Windows": f"https://github.com/rhasspy/piper/releases/download/{PIPER_RELEASE_TAG}/piper_windows_amd64.zip",
    "Linux": f"https://github.com/rhasspy/piper/releases/download/{PIPER_RELEASE_TAG}/piper_linux_x86_64.tar.gz",
}

HF_REPO = "atenax/kurmanci-tts-piper"
HF_API_URL = f"https://huggingface.co/api/models/{HF_REPO}"

# sherpa-onnx compatible Meta MMS-TTS exports (CPU friendly, 16 kHz).
MMS_KMR_REPO = "Phoonnx/vits-kmr_latn-mms-graphemes"
MMS_ARA_REPO = "Phoonnx/vits-ar-mms-graphemes"
MMS_MODELS = (
    ("mms_kmr", MMS_KMR_REPO),
    ("mms_ara", MMS_ARA_REPO),
)


def _download_file(url: str, dest: Path) -> None:
    print(f"Downloading: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Kurmanji-TTS-Setup/1.0"})
    with _urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
    print(f"Saved ({dest.stat().st_size / (1024 * 1024):.2f} MB): {dest}")


def _extract_archive(archive_path: Path, target_dir: Path) -> None:
    """Unpack the official Piper release (``.zip`` on Windows, ``.tar.gz`` elsewhere)."""
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(target_dir)
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(target_dir)


def _flatten_release_folder(target_dir: Path) -> None:
    """Move an archive's inner ``piper/`` folder up one level.

    The release archives contain a single nested ``piper`` directory. Keeping it
    would leave the executable at ``piper/windows/piper/piper.exe``, a path that
    ``config.discover_default_piper`` never looks at.
    """
    nested = target_dir / "piper"
    if not nested.is_dir():
        return
    for item in nested.iterdir():
        dest = target_dir / item.name
        if dest.exists():
            shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
        shutil.move(str(item), str(dest))
    nested.rmdir()


def _select_model_files(siblings: list[str]) -> "tuple[str, str]":
    """Pick one ``.onnx`` file and its matching ``.onnx.json`` from a HF repo listing."""
    onnx_files = [name for name in siblings if name.endswith(".onnx")]
    json_files = [name for name in siblings if name.endswith(".onnx.json")]
    if not onnx_files or not json_files:
        raise RuntimeError(
            f"Could not locate .onnx and .onnx.json files in {HF_REPO}: {siblings}"
        )
    onnx_name = onnx_files[0]
    config_name = f"{onnx_name}.json" if f"{onnx_name}.json" in json_files else json_files[0]
    return onnx_name, config_name


def install_piper(piper_dir: Path) -> Path:
    """Download and extract the official Piper CLI archive for the current OS."""
    system = platform.system()
    if system not in PIPER_URLS:
        raise RuntimeError(f"Unsupported OS for automated Piper fetch: {system}")

    target_subdir = piper_dir / system.lower()
    exe_name = "piper.exe" if system == "Windows" else "piper"
    exe_path = target_subdir / exe_name
    if exe_path.exists():
        print(f"Piper already present: {exe_path}")
        return exe_path

    archive_url = PIPER_URLS[system]
    archive_path = piper_dir / Path(archive_url).name
    _download_file(archive_url, archive_path)

    target_subdir.mkdir(parents=True, exist_ok=True)
    _extract_archive(archive_path, target_subdir)
    _flatten_release_folder(target_subdir)

    if system != "Windows" and exe_path.exists():
        exe_path.chmod(exe_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    archive_path.unlink(missing_ok=True)
    print(f"Piper installed at: {exe_path}")
    return exe_path


def install_kurmanji_model(models_dir: Path) -> Path:
    """Discover and download .onnx and .onnx.json files from atenax/kurmanci-tts-piper."""
    models_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(HF_API_URL, headers={"User-Agent": "Kurmanji-TTS-Setup/1.0"})
    with _urlopen(req, timeout=30) as resp:
        repo_info = json.loads(resp.read().decode("utf-8"))

    siblings = [entry.get("rfilename", "") for entry in repo_info.get("siblings", [])]
    onnx_name, config_name = _select_model_files(siblings)

    local_onnx = models_dir / Path(onnx_name).name
    local_json = models_dir / Path(config_name).name

    if not local_onnx.exists():
        _download_file(f"https://huggingface.co/{HF_REPO}/resolve/main/{onnx_name}", local_onnx)
    if not local_json.exists():
        _download_file(f"https://huggingface.co/{HF_REPO}/resolve/main/{config_name}", local_json)

    meta = parse_model_metadata(local_onnx, preferred_speaker=54)
    print(
        f"Verified model: {meta.model_path.name} | Size: {meta.model_size_mb} MB | "
        f"Sample Rate: {meta.sample_rate} Hz | Speakers: {meta.num_speakers} | "
        f"Default Speaker: {meta.default_speaker_id}"
    )
    return local_onnx


def _write_mms_tokens(config_path: Path, tokens_path: Path) -> None:
    """Convert a Phoonnx MMS phoneme map into sherpa-onnx tokens.txt format."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    phoneme_map = config["phoneme_id_map"]
    lines = [
        f"{token} {int(idx)}"
        for token, idx in sorted(phoneme_map.items(), key=lambda item: int(item[1]))
    ]
    tokens_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_mms_model(models_dir: Path, subdir: str, repo: str) -> Path:
    """Download a sherpa-onnx compatible Meta MMS-TTS ONNX voice."""
    target = models_dir / subdir
    target.mkdir(parents=True, exist_ok=True)
    onnx_path = target / "model.onnx"
    config_path = target / "config.json"
    tokens_path = target / "tokens.txt"

    if not (onnx_path.exists() and onnx_path.stat().st_size > 1024 * 1024):
        _download_file(f"https://huggingface.co/{repo}/resolve/main/model.onnx", onnx_path)
    else:
        print(f"MMS model already present: {onnx_path}")
    if not config_path.exists():
        _download_file(f"https://huggingface.co/{repo}/resolve/main/config.json", config_path)

    _write_mms_tokens(config_path, tokens_path)
    sample_rate = int(json.loads(config_path.read_text(encoding="utf-8"))["audio"]["sample_rate"])
    print(
        f"Verified {subdir}: {onnx_path.name} | "
        f"Size: {onnx_path.stat().st_size / (1024 * 1024):.2f} MB | "
        f"Rate: {sample_rate} Hz | Tokens: {tokens_path.name}"
    )
    return onnx_path


def copy_models_to_dist(models_dir: Path) -> None:
    """Keep an already-built dist/models folder in sync after a runtime fetch."""
    dist_models = get_app_root() / "dist" / "models"
    if not dist_models.parent.exists():
        print(f"No existing dist folder; skipping copy to {dist_models}")
        return
    dist_models.mkdir(parents=True, exist_ok=True)
    for item in models_dir.iterdir():
        target = dist_models / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        elif item.is_file():
            shutil.copy2(item, target)
        print(f"Copied to dist: {target}")


def main() -> None:
    root = get_app_root()
    print(f"=== Kurmanji-TTS Offline Runtime Setup ({root}) ===")
    install_piper(root / "piper")
    install_kurmanji_model(root / "models")
    for subdir, repo in MMS_MODELS:
        install_mms_model(root / "models", subdir, repo)
    copy_models_to_dist(root / "models")
    print("Setup completed successfully. You may now run: python main.py")


if __name__ == "__main__":
    main()
