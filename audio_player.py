# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""Temporary WAV lifecycle management, audio metadata and in-process playback.

The player is deliberately implemented with OS primitives that are already part
of Python (``winmm`` via ctypes on Windows, ``aplay`` on Linux). No external
media player window is ever opened, and no PyInstaller plugin is required.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from locales import msg


class PlaybackState(str, Enum):
    """Playback state machine for the UI audio player."""

    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True)
class WavInfo:
    """Technical metadata extracted from a PCM WAV file."""

    path: Path
    channels: int
    sample_width: int
    sample_rate: int
    num_frames: int
    duration_seconds: float
    file_size_bytes: int


def inspect_wav(wav_path: Path) -> WavInfo:
    """Read technical parameters and exact duration from a WAV file."""
    path = Path(wav_path)
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        num_frames = wf.getnframes()
        duration = num_frames / float(sample_rate) if sample_rate > 0 else 0.0

    return WavInfo(
        path=path,
        channels=channels,
        sample_width=sample_width,
        sample_rate=sample_rate,
        num_frames=num_frames,
        duration_seconds=round(duration, 3),
        file_size_bytes=path.stat().st_size,
    )


def format_seconds(seconds: float) -> str:
    """Format seconds as MM:SS for audio player display."""
    total = max(0, int(round(seconds)))
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


class AudioSessionManager:
    """Manages unique per-synthesis WAV paths to avoid Windows WinError 32 file locks."""

    def __init__(self, session_dir: Optional[Path] = None) -> None:
        if session_dir is None:
            base = Path(tempfile.gettempdir()) / "kurmanji_tts_sessions"
            base.mkdir(parents=True, exist_ok=True)
            self.session_dir = base / f"session_{uuid.uuid4().hex[:8]}"
        else:
            self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.current_wav: Optional[Path] = None
        self.current_info: Optional[WavInfo] = None
        self.state: PlaybackState = PlaybackState.IDLE

    def allocate_output_path(self) -> Path:
        """Create a unique WAV path for the next synthesis run and purge older unlocked files."""
        self.cleanup_stale_files(keep_latest=True)
        stamp = int(time.time() * 1000)
        token = uuid.uuid4().hex[:6]
        return self.session_dir / f"kurmanji_{stamp}_{token}.wav"

    def register_generated_wav(self, wav_path: Path) -> WavInfo:
        """Register a newly synthesized WAV file as the active playback asset."""
        info = inspect_wav(wav_path)
        self.current_wav = info.path
        self.current_info = info
        self.state = PlaybackState.STOPPED
        return info

    def set_state(self, new_state: PlaybackState) -> PlaybackState:
        """Transition playback state safely."""
        self.state = new_state
        return self.state

    def export_wav(self, destination_path: Path) -> Path:
        """Copy the active generated WAV file to a user-selected destination."""
        if self.current_wav is None or not self.current_wav.exists():
            raise FileNotFoundError(msg("err_export_no_wav"))

        dest = Path(destination_path)
        if dest.suffix.lower() != ".wav":
            dest = dest.with_suffix(".wav")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.current_wav, dest)
        return dest

    def cleanup_stale_files(self, keep_latest: bool = False) -> int:
        """Remove old temporary WAV files safely, ignoring any file still locked by OS audio."""
        removed = 0
        if not self.session_dir.exists():
            return 0
        for item in self.session_dir.glob("*.wav"):
            if keep_latest and self.current_wav is not None and item == self.current_wav:
                continue
            try:
                item.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def shutdown(self) -> None:
        """Clean up session directory on application exit."""
        self.cleanup_stale_files(keep_latest=False)
        try:
            self.session_dir.rmdir()
        except OSError:
            pass


class _MciBackend:
    """Windows backend using the built-in Multimedia Command Interface (winmm)."""

    def __init__(self) -> None:
        from ctypes import wintypes

        winmm = ctypes.windll.winmm
        winmm.mciSendStringW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HWND
        ]
        winmm.mciSendStringW.restype = wintypes.UINT
        winmm.mciGetErrorStringW.argtypes = [wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        winmm.mciGetErrorStringW.restype = wintypes.BOOL

        self._winmm = winmm
        self._alias = f"ktts{uuid.uuid4().hex[:8]}"
        self._opened = False
        self._pending_seek_ms = 0

    def _cmd(self, command: str) -> str:
        buffer = ctypes.create_unicode_buffer(512)
        code = self._winmm.mciSendStringW(command, buffer, 511, None)
        if code != 0:
            message = ctypes.create_unicode_buffer(256)
            self._winmm.mciGetErrorStringW(code, message, 255)
            raise RuntimeError(f"MCI {code}: {message.value} — {command}")
        return buffer.value

    def _mode(self) -> str:
        if not self._opened:
            return "closed"
        try:
            return self._cmd(f"status {self._alias} mode").lower()
        except RuntimeError:
            return "closed"

    def load(self, wav_path: Path) -> None:
        self.close()
        self._cmd(f'open "{Path(wav_path).resolve()}" type waveaudio alias {self._alias}')
        self._opened = True
        self._pending_seek_ms = 0
        self._cmd(f"set {self._alias} time format milliseconds")

    def play(self) -> None:
        if not self._opened:
            raise RuntimeError("لا يوجد ملف صوتي محمّل.")
        if self._mode() == "paused":
            self._cmd(f"resume {self._alias}")
            return
        self._cmd(f"seek {self._alias} to {int(self._pending_seek_ms)}")
        self._cmd(f"play {self._alias}")

    def pause(self) -> None:
        if self._mode() == "playing":
            self._cmd(f"pause {self._alias}")

    def resume(self) -> None:
        if self._mode() == "paused":
            self._cmd(f"resume {self._alias}")

    def stop(self) -> None:
        if not self._opened:
            return
        try:
            self._cmd(f"stop {self._alias}")
            self._cmd(f"seek {self._alias} to 0")
        except RuntimeError:
            pass
        self._pending_seek_ms = 0

    def seek(self, position_ms: int) -> None:
        if not self._opened:
            return
        length = self.get_length_ms()
        value = max(0, int(position_ms))
        if length > 0:
            # MCI rejects positions beyond the media length.
            value = min(value, max(0, length - 1))
        was_playing = self._mode() == "playing"
        self._pending_seek_ms = value
        if self._mode() in ("playing", "paused"):
            self._cmd(f"seek {self._alias} to {value}")
            # winmm stops the device on seek; keep the UI playing.
            if was_playing:
                self._cmd(f"play {self._alias}")

    def get_position_ms(self) -> int:
        if not self._opened:
            return 0
        try:
            return int(self._cmd(f"status {self._alias} position").strip() or 0)
        except (RuntimeError, ValueError):
            return 0

    def get_length_ms(self) -> int:
        if not self._opened:
            return 0
        try:
            return int(self._cmd(f"status {self._alias} length").strip() or 0)
        except (RuntimeError, ValueError):
            return 0

    def is_playing(self) -> bool:
        return self._mode() == "playing"

    def close(self) -> None:
        if self._opened:
            try:
                self._cmd(f"stop {self._alias}")
            except RuntimeError:
                pass
            try:
                self._cmd(f"close {self._alias}")
            except RuntimeError:
                pass
            self._opened = False
        self._pending_seek_ms = 0


class _AplayBackend:
    """Linux backend: headless ``aplay`` fed with raw PCM over stdin."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._feeder: Optional[threading.Thread] = None
        self._path: Optional[Path] = None
        self._length_ms = 0
        self._offset_ms = 0
        self._started_at = 0.0
        self._paused = False

    @staticmethod
    def _available() -> bool:
        return shutil.which("aplay") is not None

    def load(self, wav_path: Path) -> None:
        self.close()
        if not self._available():
            raise RuntimeError("aplay غير متوفر على هذا النظام.")
        self._path = Path(wav_path).resolve()
        self._length_ms = int(inspect_wav(self._path).duration_seconds * 1000)
        self._offset_ms = 0

    def _spawn(self, offset_ms: int) -> None:
        if self._path is None:
            return
        with wave.open(str(self._path), "rb") as wf:
            rate, channels, width = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
            start = min(wf.getnframes(), int(offset_ms / 1000.0 * rate))
            wf.setpos(start)
            raw = wf.readframes(wf.getnframes() - start)

        fmt = "S16_LE" if width == 2 else ("S24_3LE" if width == 3 else "S32_LE")
        self._proc = subprocess.Popen(
            ["aplay", "-q", "-f", fmt, "-r", str(rate), "-c", str(channels), "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def feed() -> None:
            try:
                self._proc.stdin.write(raw)
                self._proc.stdin.flush()
                self._proc.stdin.close()
            except (OSError, ValueError):
                pass

        self._feeder = threading.Thread(target=feed, daemon=True)
        self._feeder.start()
        self._offset_ms = offset_ms
        self._started_at = time.monotonic()
        self._paused = False

    def play(self) -> None:
        if self._path is None:
            raise RuntimeError("لا يوجد ملف صوتي محمّل.")
        if self._paused and self._proc is not None and self._proc.poll() is None:
            self.resume()
            return
        self.stop()
        self._spawn(self._offset_ms if self._offset_ms else 0)

    def pause(self) -> None:
        if self._proc is not None and self._proc.poll() is None and not self._paused:
            import signal
            self._proc.send_signal(signal.SIGSTOP)
            self._offset_ms += int((time.monotonic() - self._started_at) * 1000)
            self._paused = True

    def resume(self) -> None:
        if self._proc is not None and self._proc.poll() is None and self._paused:
            import signal
            self._proc.send_signal(signal.SIGCONT)
            self._started_at = time.monotonic()
            self._paused = False

    def stop(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.poll() is None and self._paused:
                    import signal
                    self._proc.send_signal(signal.SIGCONT)
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                try:
                    self._proc.kill()
                except OSError:
                    pass
        self._proc = None
        self._feeder = None
        self._paused = False
        self._offset_ms = 0

    def seek(self, position_ms: int) -> None:
        was_playing = self.is_playing()
        self.stop()
        self._offset_ms = max(0, min(self._length_ms, int(position_ms)))
        if was_playing:
            self._spawn(self._offset_ms)

    def get_position_ms(self) -> int:
        if self._proc is None or self._paused:
            return self._offset_ms
        elapsed = int((time.monotonic() - self._started_at) * 1000)
        return min(self._length_ms, self._offset_ms + elapsed)

    def get_length_ms(self) -> int:
        return self._length_ms

    def is_playing(self) -> bool:
        return (
            self._proc is not None
            and self._proc.poll() is None
            and not self._paused
        )

    def close(self) -> None:
        self.stop()
        self._path = None
        self._length_ms = 0


class InAppAudioPlayer:
    """Play WAV data inside the application process, without any external player."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._backend = _MciBackend() if hasattr(ctypes, "windll") else _AplayBackend()
        self._current_path: Optional[Path] = None

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__

    def load(self, wav_path: Path) -> None:
        """Release the previous WAV handle first, then load a new one."""
        with self._lock:
            self._backend.close()
            self._backend.load(wav_path)
            self._current_path = Path(wav_path)

    def play(self) -> None:
        with self._lock:
            self._backend.play()

    def pause(self) -> None:
        with self._lock:
            self._backend.pause()

    def resume(self) -> None:
        with self._lock:
            self._backend.resume()

    def stop(self) -> None:
        with self._lock:
            self._backend.stop()

    def seek(self, position_ms: int) -> None:
        with self._lock:
            self._backend.seek(position_ms)

    def get_position_ms(self) -> int:
        with self._lock:
            return self._backend.get_position_ms()

    def get_length_ms(self) -> int:
        with self._lock:
            return self._backend.get_length_ms()

    def is_playing(self) -> bool:
        with self._lock:
            return self._backend.is_playing()

    def close(self) -> None:
        with self._lock:
            self._backend.close()
            self._current_path = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
