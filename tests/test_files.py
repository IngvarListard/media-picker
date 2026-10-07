import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from files import (build_mpv_command, find_mpv, is_next_episode, list_directory,
                   matching, parse_extensions, scan_tracks, source_folder,
                   source_matches)


class FileSelectionTests(unittest.TestCase):
    def test_next_episode_changes_exactly_one_number_by_one(self):
        video = Path("S4 - 02 [1080p].mkv")
        self.assertTrue(is_next_episode(video, Path("S4 - 03 [1080p].mkv")))
        for name in ("S4 - 04 [1080p].mkv", "S5 - 03 [1080p].mkv",
                     "S4 - 02 [1080p].mkv", "S4 - 03 [720p].mkv"):
            with self.subTest(name=name):
                self.assertFalse(is_next_episode(video, Path(name)))

    def test_source_folder_follows_relative_or_external_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / "Season A", root / "Season B"
            for folder in (old / "Sound" / "AniStar", new / "Sound" / "AniStar",
                           root / "External"):
                folder.mkdir(parents=True)
            first, second = old / "Show 05.mkv", new / "Show 06.mkv"
            track = old / "Sound" / "AniStar" / "Show 05.mka"
            target = new / "Sound" / "AniStar" / "Show 06.mka"
            track.touch()
            target.touch()
            source = source_folder(first, track)
            self.assertEqual(source, Path("Sound/AniStar"))
            self.assertEqual(source_matches(second, source, {".mka"}), [target])
            target.unlink()
            self.assertEqual(source_matches(second, source, {".mka"}), [])
            target.touch()
            (target.parent / "Show 06.AL.mka").touch()
            self.assertEqual(len(source_matches(second, source, {".mka"})), 2)

            external = root / "External"
            (external / "Show 06.mka").touch()
            self.assertEqual(source_folder(first, external / "Show 05.mka"), external)
            self.assertEqual(source_matches(second, external, {".mka"}),
                             [external / "Show 06.mka"])

    def test_directory_lists_folders_then_allowed_files_naturally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "folder 10").mkdir()
            (root / "folder 2").mkdir()
            for name in ("video 10.MKV", "video 2.mkv", "ignored.txt"):
                (root / name).touch()
            self.assertEqual(
                [path.name for path in list_directory(root, parse_extensions("MKV, .mp4"))],
                ["folder 2", "folder 10", "video 2.mkv", "video 10.MKV"],
            )
            self.assertEqual(list_directory(root, set())[:2],
                             [root / "folder 2", root / "folder 10"])
            with self.assertRaises(OSError):
                list_directory(root / "missing", {".mkv"})

    def test_matching_requires_full_stem_or_dot_suffix(self):
        video = Path("Шоу - 02.mkv")
        tracks = [Path(name) for name in
                  ("Шоу - 02.mka", "Шоу - 02.AL.mka", "Шоу - 03.mka",
                   "Шоу - 02 extra.mka")]
        self.assertEqual(matching(video, tracks), tracks[:2])
        self.assertEqual(len(matching(video, tracks[:1])), 1)
        self.assertEqual(matching(video, tracks[2:]), [])

    def test_recursive_tracks_keep_paths_and_continue_after_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "AniStar", root / "Other"
            first.mkdir()
            second.mkdir()
            for path in (first / "Фильм 02.mka", second / "Фильм 02.mka",
                         second / "Фильм 02.ass", second / "unrelated.mka"):
                path.touch()
            audio, subtitles, errors = scan_tracks(root, {".mka"}, {".ass"})
            self.assertEqual(len(matching(root / "Фильм 02.mkv", audio)), 2)
            self.assertEqual(subtitles, [second / "Фильм 02.ass"])
            self.assertEqual(errors, [])

            def broken_walk(_root, onerror, followlinks):
                self.assertFalse(followlinks)
                onerror(PermissionError(13, "denied", str(first)))
                yield str(second), [], ["Фильм 02.ass"]

            with patch("files.os.walk", broken_walk):
                audio, subtitles, errors = scan_tracks(root, {".mka"}, {".ass"})
            self.assertEqual(subtitles, [second / "Фильм 02.ass"])
            self.assertEqual(errors, [first])


class MpvLaunchTests(unittest.TestCase):
    def test_find_mpv_prefers_explicit_existing_path_then_path_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = root / "my mpv"
            explicit.touch()
            self.assertEqual(find_mpv(str(explicit), path=str(root)), str(explicit))
            self.assertEqual(find_mpv("~nonexistent", path=str(root)), None)

            lookup = root / "bin"
            lookup.mkdir()
            found = lookup / "mpv"
            found.touch()
            found.chmod(0o755)
            self.assertEqual(find_mpv("", path=str(lookup)), str(found))
            self.assertEqual(find_mpv(""), find_mpv("", path=None))
            self.assertEqual(find_mpv(str(root / "missing"), path=str(lookup)), str(found))
            self.assertEqual(find_mpv(str(root / "missing"), path=str(root)), None)

    def test_build_mpv_command_keeps_track_keys_separator_and_video_order(self):
        video = Path("/shows/Show 02.mkv")
        self.assertEqual(build_mpv_command("mpv", video),
                         ["mpv", "--", str(video)])
        self.assertEqual(
            build_mpv_command("mpv", video, Path("/tracks/Show 02.mka"),
                              Path("/subs/Show 02.ass"),
                              ["--fullscreen", "--volume=80", "--volume=20"]),
            ["mpv", "--audio-file=/tracks/Show 02.mka",
             "--sub-file=/subs/Show 02.ass",
             "--fullscreen", "--volume=80", "--volume=20",
             "--", str(video)],
        )
        self.assertEqual(build_mpv_command("mpv", video, None, Path("/s/Show 02.ass")),
                         ["mpv", "--sub-file=/s/Show 02.ass", "--", str(video)])


if __name__ == "__main__":
    unittest.main()
