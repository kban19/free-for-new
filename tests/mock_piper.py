#!/usr/bin/env python3
"""Realistic Piper CLI test double supporting both single-shot and --json-input modes."""

import argparse
import json
import math
import struct
import sys
import wave
from pathlib import Path


def write_test_wav(output_path: Path, text: str, speaker_id: int, sample_rate: int, length_scale: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.25, min(15.0, len(text) * 0.04 * length_scale))
    num_frames = int(sample_rate * duration)
    freq = 140.0 + (speaker_id % 40) * 6.5
    amplitude = 12000

    frames = bytearray()
    for i in range(num_frames):
        sample = int(amplitude * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
        frames.extend(struct.pack("<h", sample))

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--speaker", type=int, default=0)
    parser.add_argument("--output_file", default="")
    parser.add_argument("--length_scale", type=float, default=1.0)
    parser.add_argument("--noise_scale", type=float, default=0.667)
    parser.add_argument("--noise_w", type=float, default=0.8)
    parser.add_argument("--json-input", action="store_true")
    args = parser.parse_args()

    model_path = Path(args.model)
    cfg_path = Path(f"{model_path}.json")
    if not model_path.exists() or not cfg_path.exists():
        sys.stderr.write("Model or config not found\n")
        return 1

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    sample_rate = int(cfg.get("audio", {}).get("sample_rate", 22050))
    num_speakers = int(cfg.get("num_speakers", 1))

    if args.json_input:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            sid = int(payload.get("speaker_id", 0))
            if sid < 0 or sid >= num_speakers:
                sys.stderr.write(f"Invalid speaker_id: {sid}\n")
                return 2
            write_test_wav(
                output_path=Path(payload["output_file"]),
                text=str(payload.get("text", "")),
                speaker_id=sid,
                sample_rate=sample_rate,
                length_scale=float(payload.get("length_scale", 1.0)),
            )
        return 0

    text = sys.stdin.read()
    if args.speaker < 0 or args.speaker >= num_speakers:
        sys.stderr.write(f"Invalid speaker: {args.speaker}\n")
        return 2
    write_test_wav(
        output_path=Path(args.output_file),
        text=text,
        speaker_id=args.speaker,
        sample_rate=sample_rate,
        length_scale=args.length_scale,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
