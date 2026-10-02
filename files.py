"""Local file listing and track matching for Media Picker."""

import os
import re
from pathlib import Path

VIDEO = {".mkv", ".mp4", ".webm", ".avi"}
AUDIO = {".mka", ".mp3", ".flac", ".aac", ".ac3", ".eac3", ".ogg"}
SUBS = {".ass", ".ssa", ".srt", ".vtt", ".sub"}
DEFAULT_EXTENSIONS = {"video": VIDEO, "audio": AUDIO, "subtitle": SUBS}


def natural_key(value: str | Path):
    return [(1, int(part)) if part.isdigit() else (0, part.casefold())
            for part in re.split(r"(\d+)", str(value))]


def is_next_episode(current: Path, candidate: Path) -> bool:
    before = re.split(r"(\d+)", current.name.casefold())
    after = re.split(r"(\d+)", candidate.name.casefold())
    if len(before) != len(after):
        return False
    changed = 0
    for old, new in zip(before, after):
        if old == new:
            continue
        if not (old.isdecimal() and new.isdecimal() and int(new) == int(old) + 1):
            return False
        changed += 1
    return changed == 1


def parse_extensions(value: str) -> set[str]:
    return {"." + part.strip().lower().lstrip(".")
            for part in value.split(",") if part.strip().lstrip(".")}


def list_directory(directory: Path, extensions: set[str]) -> list[Path]:
    """Return folders first, then allowed files from one directory."""
    entries = [path for path in directory.iterdir()
               if path.is_dir() or (path.is_file() and path.suffix.lower() in extensions)]
    return sorted(entries, key=lambda path: (not path.is_dir(), natural_key(path.name)))


def matching(video: Path, tracks: list[Path]) -> list[Path]:
    stem = video.stem.casefold()
    return [path for path in tracks
            if path.stem.casefold() == stem
            or path.stem.casefold().startswith(stem + ".")]


def source_folder(video: Path, track: Path) -> Path:
    """Keep a track's folder relative to its video, or absolute if external."""
    try:
        return track.parent.relative_to(video.parent)
    except ValueError:
        return track.parent


def source_matches(video: Path, source: Path, extensions: set[str]) -> list[Path]:
    folder = source if source.is_absolute() else video.parent / source
    return matching(video, [path for path in list_directory(folder, extensions)
                            if path.is_file()])


def scan_tracks(root: Path, audio_ext: set[str], subtitle_ext: set[str]
                ) -> tuple[list[Path], list[Path], list[Path]]:
    """Collect tracks below root; unreadable folders do not stop the walk."""
    audio, subtitles, errors = [], [], []

    def on_error(error: OSError):
        errors.append(Path(error.filename) if error.filename else root)

    for folder, _subfolders, names in os.walk(root, onerror=on_error, followlinks=False):
        for name in names:
            path = Path(folder) / name
            extension = path.suffix.lower()
            if extension in audio_ext:
                audio.append(path)
            if extension in subtitle_ext:
                subtitles.append(path)
    key = lambda path: natural_key(path.relative_to(root))
    return sorted(audio, key=key), sorted(subtitles, key=key), errors
