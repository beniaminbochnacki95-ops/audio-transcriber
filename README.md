# audio-transcriber

Turn multi-track call recordings into readable, speaker-labelled transcripts. Runs entirely on your own machine.

Recording software such as OBS captures each participant to a separate audio track, which is great for editing and useless for reading. This tool splits the tracks, transcribes each one locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), and merges the result back into a single chronological transcript with speaker labels.

```
[00:04:27] caller1: Thanks for jumping on. Before we start, how much context do you have?
[00:04:34] caller2: Some. I read the brief and looked at the last two quarters.
[00:04:41] caller1: Good. Then let's begin with the part that isn't in the brief.
```

## Why local

The recordings this was built for contain client and candidate conversations. Nothing is uploaded, no API key is needed, and the transcript never leaves the machine that made it. On a mid-range GPU the `large-v3-turbo` model transcribes roughly an hour of two-track audio in a few minutes.

## Requirements

- Python 3.10 or newer
- [ffmpeg](https://ffmpeg.org/download.html) on `PATH` (only needed for multi-track files)
- A GPU is optional. CPU works, it is just slower.

## Setup

```bash
git clone https://github.com/beniaminbochnacki95-ops/audio-transcriber.git
cd audio-transcriber
pip install -r requirements.txt
cp config.example.json config.json
```

On Windows you can skip all of that and double-click `transcribe.bat`. It creates the virtual environment and installs dependencies on first run.

## Usage

Transcribe a single recording:

```bash
python audio_transcriber.py recording.mkv
```

Transcribe a whole folder:

```bash
python audio_transcriber.py ./recordings -o ./transcripts
```

Name the speakers in track order:

```bash
python audio_transcriber.py interview.mkv --speakers interviewer candidate
```

Force a language and output subtitles instead of plain text:

```bash
python audio_transcriber.py recording.mkv --language pl --format srt
```

### Windows one-click

Drag one or more recordings onto `transcribe.bat`, or double-click it to process everything in the `recordings/` folder. Output lands in `transcripts/`.

## Options

| Flag | Description |
| --- | --- |
| `-o, --outdir` | Where transcripts are written. Default `transcripts/` |
| `-c, --config` | Path to a config file. Default `config.json` |
| `-m, --model` | Override the Whisper model, e.g. `medium`, `large-v3` |
| `-l, --language` | Force a language code such as `pl` or `en`. Omit to autodetect |
| `-f, --format` | `txt`, `srt` or `json` |
| `--speakers` | Speaker labels in track order |
| `--keep-audio` | Keep the extracted WAV files instead of cleaning up |

## Configuration

`config.json` holds the defaults so you do not have to repeat flags:

```json
{
  "model": "large-v3-turbo",
  "device": "auto",
  "compute_type": "auto",
  "language": null,
  "beam_size": 5,
  "vad_filter": true,
  "speakers": ["caller1", "caller2"],
  "output_format": "txt"
}
```

`vad_filter` runs voice activity detection before transcription, which removes most of the silence and stray keyboard noise that otherwise turns into hallucinated text.

`config.json` is gitignored, so real participant names stay out of version control.

## Output formats

**txt** — timestamped, one line per utterance. Good for reading and searching.

**srt** — standard subtitles with the speaker label prefixed to each cue.

**json** — start, end, speaker and text per segment, for feeding into something else.

## Notes on quality

- `large-v3-turbo` is the sweet spot for speed against accuracy. Drop to `medium` on a CPU-only machine.
- Polish and other inflected languages transcribe noticeably better with the language forced rather than autodetected, especially on short recordings.
- One speaker per track is what makes the labels reliable. Two people on a single track will be merged under one label, because this tool does not do diarisation.

## Licence

MIT. See [LICENSE](LICENSE).
