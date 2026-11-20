# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""TTS engines behind one contract: Piper Kurmanji and the two Meta MMS voices.

The file has three parts, in this order:

1. the shared vocabulary (errors, dataclasses, WAV validation, helpers);
2. one class per engine — ``KurmanjiTTSEngine`` (Piper CLI) and
   ``SherpaMMSEngine`` (sherpa-onnx) — each exposing exactly
   ``check_status()``, ``synthesize()`` and ``close()``;
3. ``UnifiedTTSEngine``, the router that picks one of them by profile name.

Because both engines answer the same three calls, the UI never needed to change
when the MMS voices were added, and a new voice only has to be registered in
``UnifiedTTSEngine``. Every output passes through ``verify_wav_file`` before it
is reported as a success.
"""

from __future__ import annotations

import array
import json
import os
import platform
import stat
import subprocess
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import DEFAULT_SPEAKER_ID, get_app_root
from locales import msg

# Piper is a console program; on Windows it must not flash a black window each
# time the one-shot fallback starts.
_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
)


# --------------------------------------------------------------- vocabulary
class TTSEngineError(Exception):
    """Raised when model validation, Piper execution, or WAV output fails."""


@dataclass(frozen=True)
class ModelMetadata:
    """Parsed metadata from a Piper .onnx.json configuration file."""

    model_path: Path
    config_path: Path
    sample_rate: int
    espeak_voice: str
    num_speakers: int
    speakers: List[Tuple[int, str]]
    default_speaker_id: int
    model_size_mb: float
    inference_length_scale: float = 1.0
    inference_noise_scale: float = 0.667
    inference_noise_w: float = 0.8


@dataclass(frozen=True)
class SynthesisResult:
    """Result metrics and file location produced by a single TTS synthesis call."""

    wav_path: Path
    duration_seconds: float
    generation_time_seconds: float
    real_time_factor: float
    sample_rate: int
    speaker_id: int
    text_length: int
    mode_used: str


@dataclass(frozen=True)
class EngineStatus:
    """Readiness status of an engine and its model files."""

    ready: bool
    piper_exists: bool
    model_exists: bool
    config_exists: bool
    message: str
    metadata: Optional[ModelMetadata] = None


# ------------------------------------------------------------ shared helpers
def _status(
    ready: bool,
    piper_exists: bool,
    model_exists: bool,
    config_exists: bool,
    message: str,
    metadata: Optional[ModelMetadata] = None,
) -> EngineStatus:
    """Build a status in one place, so both engines report the same fields."""
    return EngineStatus(
        ready=ready,
        piper_exists=piper_exists,
        model_exists=model_exists,
        config_exists=config_exists,
        message=message,
        metadata=metadata,
    )


def _prepare_output(output_wav: Path) -> Path:
    """Create the folder and delete a stale file, so a crash cannot look like success."""
    output_wav = Path(output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    if output_wav.exists():
        output_wav.unlink()
    return output_wav


def _finish_result(
    output_wav: Path, started: float, speaker_id: int, text: str, mode_used: str
) -> SynthesisResult:
    """Measure, validate the WAV, then build the result both engines return.

    Timing includes writing the file, not just inference, because that is what
    the user actually waits for. RTF is generation time over audio duration.
    """
    generation_time = max(1e-6, time.perf_counter() - started)
    sample_rate, duration = verify_wav_file(output_wav)
    return SynthesisResult(
        wav_path=output_wav,
        duration_seconds=round(duration, 3),
        generation_time_seconds=round(generation_time, 3),
        real_time_factor=round(generation_time / max(duration, 1e-6), 4),
        sample_rate=sample_rate,
        speaker_id=speaker_id,
        text_length=len(text),
        mode_used=mode_used,
    )


def verify_wav_file(wav_path: Path) -> Tuple[int, float]:
    """Validate that a WAV file exists with valid RIFF/PCM headers; return (rate, duration)."""
    if not wav_path.exists():
        raise TTSEngineError(msg("err_wav_missing", path=wav_path))

    file_size = wav_path.stat().st_size
    if file_size <= 44:
        raise TTSEngineError(msg("err_wav_empty", size=file_size))

    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if frames <= 0 or rate <= 0:
                raise TTSEngineError(msg("err_wav_frames"))
            return rate, frames / float(rate)
    except wave.Error as exc:
        raise TTSEngineError(msg("err_wav_header", error=exc)) from exc


class BaseTTSEngine:
    """The three-call contract every engine in this file honours."""

    def check_status(self) -> EngineStatus:
        """Report whether the model files are present and loadable."""
        raise NotImplementedError

    def synthesize(
        self,
        text: str,
        output_wav: Path,
        speaker_id: Optional[int] = None,
        length_scale: Optional[float] = None,
        noise_scale: Optional[float] = None,
        noise_w: Optional[float] = None,
        timeout: float = 60.0,
    ) -> SynthesisResult:
        """Convert text to a validated WAV file and return its measurements."""
        raise NotImplementedError

    def close(self) -> None:
        """Release whatever the engine keeps in memory."""


# ------------------------------------------------------------ Piper metadata
def _load_speaker_display_labels(model_dir: Path) -> Dict[int, str]:
    """Build short one-line speaker labels from an optional speaker_metadata.json."""
    metadata_path = Path(model_dir) / "speaker_metadata.json"
    labels: Dict[int, str] = {}
    if not metadata_path.exists():
        return labels
    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return labels
    if not isinstance(raw, list):
        return labels

    for entry in raw:
        try:
            sid = int(entry["speaker_id"])
            voice = str(entry.get("perceived_voice", "")).strip()
            label = f"Speaker {sid}"
            if voice:
                label += f" ({voice})"
            if entry.get("is_default"):
                label += " ★"
            labels[sid] = label
        except (KeyError, TypeError, ValueError):
            continue
    return labels


def _resolve_config_path(model_path: Path) -> Path:
    """Find the ``<model>.onnx.json`` sidecar Piper needs next to the weights."""
    config_path = Path(f"{model_path}.json")
    if config_path.exists():
        return config_path
    alternative = model_path.with_suffix(".json")
    if alternative.exists():
        return alternative
    raise TTSEngineError(msg("err_config_missing", path=config_path))


def _load_model_config(config_path: Path) -> dict:
    """Read the model JSON, turning I/O and syntax errors into one clear message."""
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TTSEngineError(msg("err_config_read", error=exc)) from exc


def _build_speaker_table(
    speaker_id_map: Dict[str, int],
    num_speakers: int,
    display_labels: Dict[int, str],
) -> List[Tuple[int, str]]:
    """Build the ``(id, label)`` list the speaker dropdown shows.

    Models that ship no name map still need a usable list, so we fall back to
    plain ids; when a human label exists it always wins over a hash such as
    ``spk_54``.
    """
    if not speaker_id_map:
        return [
            (sid, display_labels.get(sid, f"Speaker {sid}"))
            for sid in range(max(1, num_speakers))
        ]

    speakers: List[Tuple[int, str]] = []
    for name, sid in sorted(speaker_id_map.items(), key=lambda item: int(item[1])):
        sid_int = int(sid)
        label = display_labels.get(sid_int)
        if label is None:
            label = (
                f"Speaker {sid_int} ({name})"
                if str(name) != str(sid_int)
                else f"Speaker {sid_int}"
            )
        speakers.append((sid_int, label))
    return speakers


def _resolve_default_speaker(speakers: List[Tuple[int, str]], preferred: int) -> int:
    """Honour the configured speaker when the model has it, else take the first."""
    if preferred in {sid for sid, _ in speakers}:
        return preferred
    return speakers[0][0] if speakers else 0


def _read_inference_defaults(data: dict) -> Tuple[float, float, float]:
    """Read the model's own recommended (length_scale, noise_scale, noise_w)."""
    inference_cfg = data.get("inference", {})

    def read_float(key: str, fallback: float) -> float:
        try:
            return float(inference_cfg.get(key, fallback))
        except (TypeError, ValueError):
            return fallback

    return (
        read_float("length_scale", 1.0),
        read_float("noise_scale", 0.667),
        read_float("noise_w", 0.8),
    )


def parse_model_metadata(model_path: Path, preferred_speaker: int = 54) -> ModelMetadata:
    """Read and validate a Piper ``.onnx`` + ``.onnx.json`` pair.

    Raises ``TTSEngineError`` with a translated message for each failure mode, so
    the UI can show the real reason instead of a generic "model not ready".
    """
    if not model_path.exists():
        raise TTSEngineError(msg("err_model_missing", path=model_path))

    config_path = _resolve_config_path(model_path)
    data = _load_model_config(config_path)

    sample_rate = int(data.get("audio", {}).get("sample_rate", 22050))
    espeak_voice = str(data.get("espeak", {}).get("voice", "ku"))
    num_speakers = int(data.get("num_speakers", 1))
    speakers = _build_speaker_table(
        data.get("speaker_id_map", {}),
        num_speakers,
        _load_speaker_display_labels(model_path.parent),
    )
    length_scale, noise_scale, noise_w = _read_inference_defaults(data)

    return ModelMetadata(
        model_path=model_path,
        config_path=config_path,
        sample_rate=sample_rate,
        espeak_voice=espeak_voice,
        num_speakers=max(num_speakers, len(speakers)),
        speakers=speakers,
        default_speaker_id=_resolve_default_speaker(speakers, preferred_speaker),
        model_size_mb=round(model_path.stat().st_size / (1024 * 1024), 2),
        inference_length_scale=length_scale,
        inference_noise_scale=noise_scale,
        inference_noise_w=noise_w,
    )


def _wait_for_stable_wav(proc: subprocess.Popen, output_wav: Path, timeout: float) -> bool:
    """Wait until Piper finishes writing, i.e. the WAV stops growing.

    In ``--json-input`` mode Piper prints no per-request acknowledgement, so the
    only reliable signal that a line was processed is the output file appearing
    and its size staying identical across two consecutive polls.
    """
    deadline = time.monotonic() + timeout
    last_size = -1
    stable_ticks = 0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if output_wav.exists():
            size = output_wav.stat().st_size
            if size > 44 and size == last_size:
                stable_ticks += 1
                if stable_ticks >= 2:
                    return True
            else:
                stable_ticks = 0
            last_size = size
        time.sleep(0.025)
    return False


# ------------------------------------------------------------- Piper engine
class KurmanjiTTSEngine(BaseTTSEngine):
    """Thread-safe Piper CLI wrapper supporting persistent warm-model synthesis."""

    def __init__(
        self,
        piper_path: Path,
        model_path: Path,
        preferred_speaker: int = 54,
        use_persistent_process: bool = True,
    ) -> None:
        self.piper_path = Path(piper_path)
        self.model_path = Path(model_path)
        self.preferred_speaker = preferred_speaker
        self.use_persistent_process = use_persistent_process
        self._lock = threading.RLock()
        self._proc: Optional[subprocess.Popen] = None
        self._loaded_model_key: Optional[str] = None
        self._metadata: Optional[ModelMetadata] = None

    def update_paths(
        self,
        piper_path: Path,
        model_path: Path,
        preferred_speaker: int = 54,
        use_persistent_process: bool = True,
    ) -> EngineStatus:
        """Reconfigure engine paths and reset any warm background process."""
        with self._lock:
            self.close()
            self.piper_path = Path(piper_path)
            self.model_path = Path(model_path)
            self.preferred_speaker = preferred_speaker
            self.use_persistent_process = use_persistent_process
            self._metadata = None
            return self.check_status()

    def _ensure_executable_permission(self) -> None:
        """Ensure executable bit is set on Linux/macOS if owned by current user."""
        if platform.system() != "Windows" and self.piper_path.exists():
            if not os.access(self.piper_path, os.X_OK):
                try:
                    current_mode = self.piper_path.stat().st_mode
                    self.piper_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP)
                except OSError as exc:
                    raise TTSEngineError(
                        msg("err_piper_permission", path=self.piper_path)
                    ) from exc

    def check_status(self) -> EngineStatus:
        """Verify Piper binary and model files without synthesizing audio."""
        piper_exists = self.piper_path.is_file()
        model_exists = self.model_path.is_file()
        config_exists = (
            Path(f"{self.model_path}.json").exists()
            or self.model_path.with_suffix(".json").exists()
        )
        if not piper_exists:
            return _status(
                False, False, model_exists, config_exists,
                msg("status_piper_missing", path=self.piper_path),
            )
        if not model_exists or not config_exists:
            return _status(
                False, True, model_exists, config_exists,
                msg("status_files_incomplete", path=self.model_path.parent),
            )
        try:
            self._ensure_executable_permission()
            meta = parse_model_metadata(self.model_path, self.preferred_speaker)
            self._metadata = meta
            return _status(
                True, True, True, True,
                msg("status_ready_detail", rate=meta.sample_rate,
                    speakers=meta.num_speakers),
                meta,
            )
        except TTSEngineError as exc:
            return _status(False, True, True, config_exists, str(exc))

    # ---------------------------------------------------------- piper process
    def _base_command(self) -> List[str]:
        """The two arguments every Piper invocation shares."""
        return [str(self.piper_path), "--model", str(self.model_path)]

    def _voice_flags(
        self, length_scale: float, noise_scale: float, noise_w: float
    ) -> List[str]:
        """Voice parameters are CLI flags: Piper ignores them in JSON input."""
        return [
            "--length_scale", str(float(length_scale)),
            "--noise_scale", str(float(noise_scale)),
            "--noise_w", str(float(noise_w)),
        ]

    def _start_persistent_process(
        self,
        length_scale: float,
        noise_scale: float,
        noise_w: float,
    ) -> subprocess.Popen:
        """Start Piper in --json-input mode so ONNX weights remain cached in RAM.

        Real Piper only reads ``text``, ``output_file`` and (for multi-speaker
        voices) ``speaker_id`` from a JSON input line, so the voice parameters
        are CLI flags here. The warm process is recycled whenever one changes.
        """
        model_key = (
            f"{self.piper_path.resolve()}::{self.model_path.resolve()}::"
            f"{float(length_scale)}::{float(noise_scale)}::{float(noise_w)}"
        )
        if (
            self._proc is not None
            and self._proc.poll() is None
            and self._loaded_model_key == model_key
        ):
            return self._proc

        self.close()
        cmd = self._base_command() + ["--json-input"] + self._voice_flags(
            length_scale, noise_scale, noise_w
        )
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # Piper logs one line per synthesis; an unread pipe would eventually
            # fill up and block the worker. Crash details surface via the
            # one-shot fallback, which captures stderr.
            stderr=subprocess.DEVNULL,
            cwd=str(self.piper_path.parent),
            creationflags=_NO_WINDOW,
        )
        self._proc = proc
        self._loaded_model_key = model_key
        return proc

    def _synthesize_warm(
        self,
        text: str,
        output_wav: Path,
        speaker_id: int,
        length_scale: float,
        noise_scale: float,
        noise_w: float,
        timeout: float,
    ) -> bool:
        """Try the warm process; return False when the caller must fall back."""
        try:
            proc = self._start_persistent_process(length_scale, noise_scale, noise_w)
            if proc.stdin is None:
                return False
            # Only these keys are part of Piper's JSON input schema. Single-speaker
            # voices (e.g. the Arabic Kareem model) crash when speaker_id is sent.
            payload = {"text": text, "output_file": str(output_wav.resolve())}
            if self._metadata is None or self._metadata.num_speakers > 1:
                payload["speaker_id"] = int(speaker_id)
            proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            proc.stdin.flush()

            if _wait_for_stable_wav(proc, output_wav, timeout):
                return True
            self.close()
            return False
        except (OSError, BrokenPipeError, ValueError):
            self.close()
            return False

    def _synthesize_oneshot(
        self,
        text: str,
        output_wav: Path,
        speaker_id: int,
        length_scale: float,
        noise_scale: float,
        noise_w: float,
        timeout: float,
    ) -> None:
        """Run Piper CLI as a single-shot subprocess with UTF-8 stdin."""
        cmd = self._base_command() + [
            "--speaker", str(int(speaker_id)),
            "--output_file", str(output_wav.resolve()),
        ] + self._voice_flags(length_scale, noise_scale, noise_w)
        try:
            completed = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.piper_path.parent),
                timeout=timeout,
                creationflags=_NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TTSEngineError(
                msg("err_timeout", seconds=f"{timeout:.0f}")
            ) from exc
        except OSError as exc:
            raise TTSEngineError(msg("err_piper_run", error=exc)) from exc

        if completed.returncode != 0:
            stderr_msg = completed.stderr.decode("utf-8", errors="replace").strip()
            raise TTSEngineError(
                msg(
                    "err_piper_failed",
                    code=completed.returncode,
                    error=stderr_msg or msg("err_unknown"),
                )
            )

    def _render_wav(
        self,
        text: str,
        output_wav: Path,
        sid: int,
        ls: float,
        ns: float,
        nw: float,
        timeout: float,
    ) -> str:
        """Run Piper and report which mode produced the file.

        The warm process is tried first. Any failure there (crash, broken pipe,
        timeout) silently falls back to a one-shot run, so the user still gets
        audio instead of an error they cannot act on.
        """
        params = (text, output_wav, sid, ls, ns, nw, timeout)
        if self.use_persistent_process and self._synthesize_warm(*params):
            return "persistent-json-cli"
        self._synthesize_oneshot(*params)
        return "oneshot-cli"

    def _resolve_synthesis_params(
        self,
        meta: ModelMetadata,
        speaker_id: Optional[int],
        length_scale: Optional[float],
        noise_scale: Optional[float],
        noise_w: Optional[float],
    ) -> Tuple[float, float, float, int]:
        """Fill every missing voice parameter from the model's own defaults."""
        ls = meta.inference_length_scale if length_scale is None else float(length_scale)
        ns = meta.inference_noise_scale if noise_scale is None else float(noise_scale)
        nw = meta.inference_noise_w if noise_w is None else float(noise_w)
        sid = meta.default_speaker_id if speaker_id is None else int(speaker_id)
        if sid < 0 or sid >= meta.num_speakers:
            raise TTSEngineError(
                msg("err_speaker_range", sid=sid, maximum=meta.num_speakers - 1)
            )
        return ls, ns, nw, sid

    def synthesize(
        self,
        text: str,
        output_wav: Path,
        speaker_id: Optional[int] = None,
        length_scale: Optional[float] = None,
        noise_scale: Optional[float] = None,
        noise_w: Optional[float] = None,
        timeout: float = 60.0,
    ) -> SynthesisResult:
        """Convert normalized Kurmanji text to a validated WAV file on CPU.

        The whole call is held under a re-entrant lock so two quick clicks cannot
        feed the same warm Piper process at once. The caller is expected to run
        it on a worker thread ('asyncio.to_thread'), never on the UI thread.
        """
        with self._lock:
            status = self.check_status()
            if not status.ready or status.metadata is None:
                raise TTSEngineError(status.message)

            ls, ns, nw, sid = self._resolve_synthesis_params(
                status.metadata, speaker_id, length_scale, noise_scale, noise_w
            )
            output_wav = _prepare_output(output_wav)
            started = time.perf_counter()
            mode_used = self._render_wav(text, output_wav, sid, ls, ns, nw, timeout)
            return _finish_result(output_wav, started, sid, text, mode_used)

    def close(self) -> None:
        """Terminate warm Piper subprocess cleanly and free system RAM."""
        with self._lock:
            if self._proc is None:
                return
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=2.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            finally:
                self._proc = None
                self._loaded_model_key = None

    def __del__(self) -> None:
        self.close()


# -------------------------------------------------------------- MMS engine
class SherpaMMSEngine(BaseTTSEngine):
    """Meta MMS-TTS voice run through sherpa-onnx, kept warm in RAM.

    MMS models use a single-character vocabulary instead of phonemes, which is why
    ``text_utils.prepare_text_for_mms`` filters the input first. One model covers
    one speaker only, so ``speaker_id`` is always 0 here.
    """

    VOICE_LANGS = ("kmr", "ar")
    SPEAKER_LABELS = {"kmr": "MMS Speaker 0", "ar": "MMS Arabic"}

    def __init__(self, model_dir: Path, voice_lang: str = "kmr") -> None:
        self.model_dir = Path(model_dir)
        self.voice_lang = voice_lang if voice_lang in self.VOICE_LANGS else "kmr"
        self._lock = threading.RLock()
        self._tts = None
        self._metadata: Optional[ModelMetadata] = None

    def _paths(self) -> Tuple[Path, Path]:
        return self.model_dir / "model.onnx", self.model_dir / "tokens.txt"

    def _load_sherpa_tts(self, onnx_path: Path, tokens_path: Path):
        """Import sherpa-onnx and build the VITS pipeline once per process.

        Returns ``(tts, error)``. The model stays in RAM until ``close()``, so a
        second generation does not pay the ONNX load cost again. Import failures
        are reported separately from runtime failures: only the first one means
        the user has to install something.
        """
        try:
            import sherpa_onnx  # type: ignore
        except ImportError as exc:
            return None, msg("err_sherpa_missing", error=exc)
        try:
            vits = sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(onnx_path),
                tokens=str(tokens_path),
                noise_scale=0.667,
                noise_scale_w=0.8,
                length_scale=1.0,
            )
            model_config = sherpa_onnx.OfflineTtsModelConfig(
                vits=vits, num_threads=2, provider="cpu", debug=False
            )
            return (
                sherpa_onnx.OfflineTts(
                    sherpa_onnx.OfflineTtsConfig(model=model_config, max_num_sentences=1)
                ),
                None,
            )
        except Exception as exc:
            return None, msg("err_sherpa_init", error=exc)

    def check_status(self) -> EngineStatus:
        """Report whether the MMS ONNX pair is present and can be loaded."""
        with self._lock:
            onnx_path, tokens_path = self._paths()
            model_exists = onnx_path.is_file()
            tokens_exist = tokens_path.is_file()
            if not model_exists or not tokens_exist:
                return _status(
                    False, True, model_exists, tokens_exist,
                    msg("status_files_incomplete", path=self.model_dir),
                )

            if self._tts is None:
                self._tts, error = self._load_sherpa_tts(onnx_path, tokens_path)
                if self._tts is None:
                    return _status(
                        False, True, True, True, error or msg("err_unknown")
                    )

            sample_rate = int(self._tts.sample_rate)
            self._metadata = ModelMetadata(
                model_path=onnx_path,
                config_path=tokens_path,
                sample_rate=sample_rate,
                espeak_voice=self.voice_lang,
                num_speakers=1,
                speakers=[(0, self.SPEAKER_LABELS[self.voice_lang])],
                default_speaker_id=0,
                model_size_mb=round(onnx_path.stat().st_size / (1024 * 1024), 2),
                inference_length_scale=1.0,
                inference_noise_scale=0.667,
                inference_noise_w=0.8,
            )
            return _status(
                True, True, True, True,
                msg("status_ready_detail", rate=sample_rate, speakers=1),
                self._metadata,
            )

    @staticmethod
    def _write_pcm_wav(output_wav: Path, samples, sample_rate: int) -> None:
        """Write float samples in [-1, 1] as a 16-bit mono PCM WAV file.

        sherpa-onnx returns floats while ``wave`` wants bytes, so the clamp and
        the 32767 scaling are what stop loud passages from wrapping into
        distortion. An empty array means the model produced silence, which we
        treat as a failure rather than saving an unusable file.
        """
        pcm = array.array(
            "h",
            (
                int(max(-1.0, min(1.0, float(sample))) * 32767)
                for sample in samples
            ),
        )
        if not pcm:
            raise TTSEngineError(msg("err_wav_frames"))
        with wave.open(str(output_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())

    def synthesize(
        self,
        text: str,
        output_wav: Path,
        speaker_id: Optional[int] = None,
        length_scale: Optional[float] = None,
        noise_scale: Optional[float] = None,
        noise_w: Optional[float] = None,
        timeout: float = 60.0,
    ) -> SynthesisResult:
        """Generate speech with the in-RAM MMS model and save it as WAV."""
        with self._lock:
            status = self.check_status()
            if not status.ready or self._tts is None:
                raise TTSEngineError(status.message)
            sid = 0 if speaker_id is None else int(speaker_id)
            if sid != 0:
                raise TTSEngineError(msg("err_speaker_range", sid=sid, maximum=0))
            speed = 1.0 / float(length_scale) if length_scale else 1.0
            speed = max(0.1, min(10.0, speed))

            output_wav = _prepare_output(output_wav)
            started = time.perf_counter()
            audio = self._tts.generate(text, sid=0, speed=speed)
            self._write_pcm_wav(output_wav, audio.samples, int(self._tts.sample_rate))
            return _finish_result(
                output_wav, started, 0, text, "sherpa-onnx-cpu"
            )

    def close(self) -> None:
        with self._lock:
            self._tts = None
            self._metadata = None


# ------------------------------------------------------------------ router
class UnifiedTTSEngine:
    """Route synthesis to Piper Kurmanji or one of the two Meta MMS voices."""

    PROFILES = ("piper_kmr", "mms_kmr", "mms_ara")
    PROFILE_DIRS = {"mms_kmr": "mms_kmr", "mms_ara": "mms_ara"}
    PROFILE_LANGS = {"mms_kmr": "kmr", "mms_ara": "ar"}

    def __init__(
        self,
        piper_path: Path,
        model_path: Path,
        preferred_speaker: int = DEFAULT_SPEAKER_ID,
        use_persistent_process: bool = True,
        root: Optional[Path] = None,
        engine_profile: str = "piper_kmr",
    ) -> None:
        self.root = Path(root) if root is not None else get_app_root()
        self.piper = KurmanjiTTSEngine(
            piper_path=piper_path,
            model_path=model_path,
            preferred_speaker=preferred_speaker,
            use_persistent_process=use_persistent_process,
        )
        self.mms: Dict[str, SherpaMMSEngine] = {
            profile: SherpaMMSEngine(
                self.root / "models" / subdir,
                voice_lang=self.PROFILE_LANGS[profile],
            )
            for profile, subdir in self.PROFILE_DIRS.items()
        }
        self.profile = engine_profile if engine_profile in self.PROFILES else "piper_kmr"

    @property
    def engine(self) -> BaseTTSEngine:
        """The engine behind the active profile."""
        if self.profile == "piper_kmr":
            return self.piper
        return self.mms[self.profile]

    def set_profile(self, profile: str) -> str:
        """Activate one profile and free the RAM of the others."""
        chosen = profile if profile in self.PROFILES else "piper_kmr"
        for name, engine in self.mms.items():
            if name != chosen:
                engine.close()
        if chosen != "piper_kmr":
            self.piper.close()
        self.profile = chosen
        return self.profile

    def check_status(self) -> EngineStatus:
        return self.engine.check_status()

    def update_paths(
        self,
        piper_path: Path,
        model_path: Path,
        preferred_speaker: int = DEFAULT_SPEAKER_ID,
        use_persistent_process: bool = True,
    ) -> EngineStatus:
        self.piper.update_paths(
            piper_path=piper_path,
            model_path=model_path,
            preferred_speaker=preferred_speaker,
            use_persistent_process=use_persistent_process,
        )
        return self.check_status()

    def synthesize(
        self,
        text: str,
        output_wav: Path,
        speaker_id: Optional[int] = None,
        length_scale: Optional[float] = None,
        noise_scale: Optional[float] = None,
        noise_w: Optional[float] = None,
        timeout: float = 60.0,
    ) -> SynthesisResult:
        return self.engine.synthesize(
            text=text,
            output_wav=output_wav,
            speaker_id=speaker_id,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w=noise_w,
            timeout=timeout,
        )

    def close(self) -> None:
        self.piper.close()
        for engine in self.mms.values():
            engine.close()
