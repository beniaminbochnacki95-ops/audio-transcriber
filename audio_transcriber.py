#!/usr/bin/env python3
"""
audio_transcriber - turn multi-track call recordings into readable, speaker-labelled transcripts.

Built for a practical problem: recording software such as OBS captures each
participant on a separate audio track, but the resulting file is unusable as a
record of what was said. This
script extracts the tracks, transcribes them locally with faster-whisper, and
merges everything back into one chronological transcript with speaker labels.

Everything runs on the local machine. No audio leaves the computer, which
matters when the recording contains client or candidate conversations.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover - dependency check only
    sys.exit(
        "faster-whisper is not installed.\n"
        "Run: pip install -r requirements.txt"
    )


DEFAULT_CONFIG = {
    "model": "large-v3-turbo",
    "device": "auto",
    "compute_type": "auto",
    "language": None,          # None = autodetect
    "beam_size": 5,
    "vad_filter": True,
    "speakers": ["caller1", "caller2"],
    "output_format": "txt",    # txt | srt | json
}

AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}
VIDEO_SUFFIXES = {".mkv", ".mp4", ".mov", ".flv", ".avi"}


# --------------------------------------------------------------------------- #
# data model
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Line:
    """A single transcribed utterance."""

    start: float
    end: float
    speaker: str
    text: str

    def timestamp(self) -> str:
        return f"{_hhmmss(self.start)}"

    def srt_range(self) -> str:
        return f"{_srt_time(self.start)} --> {_srt_time(self.end)}"


def _hhmmss(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _srt_time(seconds: float) -> str:
    millis = int((seconds - int(seconds)) * 1000)
    return f"{_hhmmss(seconds)},{millis:03d}"


# --------------------------------------------------------------------------- #
# audio handling
# --------------------------------------------------------------------------- #

def ffprobe_track_count(source: Path) -> int:
    """Return how many audio streams a container holds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {source.name}: {result.stderr.strip()}")
    return len([line for line in result.stdout.splitlines() if line.strip()])


def extract_track(source: Path, track_index: int, target: Path) -> Path:
    """Pull one audio stream out of the container as 16 kHz mono WAV."""
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(source),
            "-map", f"0:a:{track_index}",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(target),
        ],
        check=True,
    )
    return target


def prepare_tracks(source: Path, workdir: Path, speakers: Sequence[str]) -> list[tuple[str, Path]]:
    """
    Return a list of (speaker_label, wav_path).

    A multi-track container is split into one file per speaker. A plain audio
    file is treated as a single track and gets the first speaker label.
    """
    if source.suffix.lower() in AUDIO_SUFFIXES:
        return [(speakers[0], source)]

    count = ffprobe_track_count(source)
    if count == 0:
        raise RuntimeError(f"No audio streams found in {source.name}")

    if count > len(speakers):
        print(
            f"  note: {count} audio tracks but only {len(speakers)} speaker labels "
            f"configured; extra tracks will be labelled generically"
        )

    tracks: list[tuple[str, Path]] = []
    for index in range(count):
        label = speakers[index] if index < len(speakers) else f"caller{index + 1}"
        wav = workdir / f"{source.stem}_{label}.wav"
        print(f"  extracting track {index + 1}/{count} -> {label}")
        tracks.append((label, extract_track(source, index, wav)))
    return tracks


# --------------------------------------------------------------------------- #
# transcription
# --------------------------------------------------------------------------- #

def load_model(config: dict) -> WhisperModel:
    print(f"loading model '{config['model']}' on {config['device']}")
    return WhisperModel(
        config["model"],
        device=config["device"],
        compute_type=config["compute_type"],
    )


def transcribe_track(model: WhisperModel, wav: Path, speaker: str, config: dict) -> list[Line]:
    segments, info = model.transcribe(
        str(wav),
        language=config["language"],
        beam_size=config["beam_size"],
        vad_filter=config["vad_filter"],
    )
    print(f"  {speaker}: detected language '{info.language}' "
          f"(confidence {info.language_probability:.2f})")

    lines: list[Line] = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            lines.append(Line(segment.start, segment.end, speaker, text))
    return lines


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #

def render_txt(lines: Iterable[Line]) -> str:
    return "\n".join(f"[{line.timestamp()}] {line.speaker}: {line.text}" for line in lines)


def render_srt(lines: Iterable[Line]) -> str:
    blocks = []
    for number, line in enumerate(lines, start=1):
        blocks.append(f"{number}\n{line.srt_range()}\n{line.speaker}: {line.text}\n")
    return "\n".join(blocks)


def render_json(lines: Iterable[Line]) -> str:
    payload = [
        {"start": line.start, "end": line.end, "speaker": line.speaker, "text": line.text}
        for line in lines
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


RENDERERS = {"txt": render_txt, "srt": render_srt, "json": render_json}


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #

def load_config(path: Path | None) -> dict:
    config = dict(DEFAULT_CONFIG)
    if path and path.exists():
        config.update(json.loads(path.read_text(encoding="utf-8")))
    return config


def collect_sources(inputs: Sequence[str]) -> list[Path]:
    sources: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            sources.extend(
                child for child in sorted(path.iterdir())
                if child.suffix.lower() in VIDEO_SUFFIXES | AUDIO_SUFFIXES
            )
        elif path.exists():
            sources.append(path)
        else:
            print(f"skipping missing path: {path}")
    return sources


def process(source: Path, model: WhisperModel, config: dict, outdir: Path, workdir: Path) -> Path:
    print(f"\n{source.name}")
    tracks = prepare_tracks(source, workdir, config["speakers"])

    lines: list[Line] = []
    for speaker, wav in tracks:
        lines.extend(transcribe_track(model, wav, speaker, config))

    lines.sort(key=lambda line: line.start)

    suffix = config["output_format"]
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / f"{source.stem}.{suffix}"
    target.write_text(RENDERERS[suffix](lines), encoding="utf-8")

    print(f"  {len(lines)} lines -> {target}")
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audio_transcriber",
        description="Transcribe multi-track call recordings into speaker-labelled transcripts.",
    )
    parser.add_argument("inputs", nargs="+", help="recording files or a directory of recordings")
    parser.add_argument("-o", "--outdir", default="transcripts", help="where to write transcripts")
    parser.add_argument("-c", "--config", default="config.json", help="path to config file")
    parser.add_argument("-m", "--model", help="override the model from config")
    parser.add_argument("-l", "--language", help="force a language code, e.g. pl or en")
    parser.add_argument(
        "-f", "--format",
        choices=sorted(RENDERERS),
        help="override the output format from config",
    )
    parser.add_argument(
        "--speakers",
        nargs="+",
        metavar="LABEL",
        help="speaker labels in track order, e.g. --speakers caller1 caller2",
    )
    parser.add_argument("--keep-audio", action="store_true", help="keep extracted WAV files")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = load_config(Path(args.config))
    if args.model:
        config["model"] = args.model
    if args.language:
        config["language"] = args.language
    if args.format:
        config["output_format"] = args.format
    if args.speakers:
        config["speakers"] = args.speakers

    sources = collect_sources(args.inputs)
    if not sources:
        print("nothing to transcribe")
        return 1

    workdir = Path(args.outdir) / "_audio"
    model = load_model(config)

    failures = 0
    for source in sources:
        try:
            process(source, model, config, Path(args.outdir), workdir)
        except Exception as error:  # keep going through a batch
            failures += 1
            print(f"  failed: {error}")

    if not args.keep_audio and workdir.exists():
        for wav in workdir.glob("*.wav"):
            wav.unlink()
        workdir.rmdir()

    print(f"\ndone: {len(sources) - failures}/{len(sources)} transcribed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
