import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from media_picker import MediaPicker, PATH_ROLE

APP = QApplication.instance() or QApplication([])


class WindowTests(unittest.TestCase):
    def select_file(self, window, kind, path):
        for row in range(window.lists[kind].count()):
            if window.lists[kind].item(row).data(PATH_ROLE) == str(path):
                window.lists[kind].setCurrentRow(row)
                return
        self.fail(f"File not shown in {kind}: {path}")

    def window_for(self, root):
        settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
        for kind in ("video", "audio", "subtitle"):
            settings.setValue(f"paths/{kind}", str(root))
        return MediaPicker(settings)

    def test_next_episode_launches_same_sources_or_video_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            videos = [root / f"Show S4 - {number} [1080p].mkv" for number in ("02", "03")]
            audio_dir, sub_dir = root / "Sound" / "AniStar", root / "Subs" / "Crunchyroll"
            for folder in (audio_dir, sub_dir):
                folder.mkdir(parents=True)
            for video in videos:
                video.touch()
                (audio_dir / f"{video.stem}.mka").touch()
                (sub_dir / f"{video.stem}.ass").touch()

            window = self.window_for(root)
            try:
                self.select_file(window, "video", videos[0])
                window.open_directory("audio", audio_dir)
                window.open_directory("subtitle", sub_dir)
                self.select_file(window, "audio", audio_dir / f"{videos[0].stem}.mka")
                self.select_file(window, "subtitle", sub_dir / f"{videos[0].stem}.ass")
                with patch("media_picker.subprocess.Popen") as popen:
                    window.next.click()
                self.assertEqual(window.selected["video"], videos[1])
                self.assertEqual(popen.call_args.args[0], [
                    "mpv", str(videos[1]),
                    "--audio-file=" + str(audio_dir / f"{videos[1].stem}.mka"),
                    "--sub-file=" + str(sub_dir / f"{videos[1].stem}.ass"),
                ])
            finally:
                window.close()

            bare = self.window_for(root)
            try:
                self.select_file(bare, "video", videos[0])
                self.assertTrue(bare.next.isEnabled())
                with patch("media_picker.subprocess.Popen") as popen:
                    bare.next.click()
                self.assertEqual(popen.call_args.args[0], ["mpv", str(videos[1])])
            finally:
                bare.close()

    def test_next_episode_stops_on_gap_or_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, last = root / "Show 02.mkv", root / "Show 04.mkv"
            first.touch()
            last.touch()
            window = self.window_for(root)
            try:
                self.select_file(window, "video", first)
                with patch("media_picker.subprocess.Popen") as popen:
                    window.next.click()
                popen.assert_not_called()
                self.assertEqual(window.selected["video"], first)
                self.assertTrue(window.status_labels["video"].text())
            finally:
                window.close()

            second = root / "Show 03.mkv"
            second.touch()
            sound = root / "Sound"
            sound.mkdir()
            (sound / "Show 02.mka").touch()
            for extra in ((), ("Show 03.mka", "Show 03.AL.mka")):
                for name in extra:
                    (sound / name).touch()
                window = self.window_for(root)
                try:
                    self.select_file(window, "video", first)
                    window.open_directory("audio", sound)
                    self.select_file(window, "audio", sound / "Show 02.mka")
                    with patch("media_picker.subprocess.Popen") as popen:
                        window.next.click()
                    popen.assert_not_called()
                    self.assertEqual(window.selected["video"], second)
                    self.assertIsNone(window.selected["audio"])
                    self.assertIn("Sound", window.status_labels["audio"].text())
                finally:
                    window.close()

    def test_next_episode_skips_unrelated_file_but_rejects_two_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "Show 11.mkv", root / "Show 12.mkv"
            extra = root / "Show 12-[clip]-audio.webm"
            for path in (first, second, extra):
                path.touch()
            window = self.window_for(root)
            try:
                self.select_file(window, "video", first)
                with patch("media_picker.subprocess.Popen") as popen:
                    window.next.click()
                self.assertEqual(window.selected["video"], second)
                self.assertEqual(popen.call_args.args[0], ["mpv", str(second)])
            finally:
                window.close()

            current = root / "Show S4 - 02.mkv"
            for path in (current, root / "Show S4 - 03.mkv", root / "Show S5 - 02.mkv"):
                path.touch()
            window = self.window_for(root)
            try:
                self.select_file(window, "video", current)
                with patch("media_picker.subprocess.Popen") as popen:
                    window.next.click()
                popen.assert_not_called()
                self.assertEqual(window.selected["video"], current)
                self.assertIn("Несколько", window.status_labels["video"].text())
            finally:
                window.close()

    def test_manual_video_change_keeps_sources_across_modes_and_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            videos = [root / f"Show {number}.mkv" for number in ("05", "06")]
            for video in videos:
                video.touch()
            audio_dir = root / "Sound" / "AniStar"
            sub_dir = root / "Subs" / "Crunchyroll"
            for folder, extension in ((audio_dir, ".mka"), (sub_dir, ".ass"),
                                      (root / "Sound" / "Other", ".mka"),
                                      (root / "Subs" / "Signs", ".ass")):
                folder.mkdir(parents=True)
                for video in videos:
                    (folder / f"{video.stem}{extension}").touch()

            for search, follow, auto in ((False, False, False), (False, True, True),
                                         (True, False, True), (True, True, False)):
                with self.subTest(search=search, follow=follow, auto=auto):
                    window = self.window_for(root)
                    try:
                        window.follow.setChecked(follow)
                        window.auto.setChecked(auto)
                        self.select_file(window, "video", videos[0])
                        if search:
                            window.mode_boxes["audio"].setChecked(True)
                            window.mode_boxes["subtitle"].setChecked(True)
                        else:
                            window.open_directory("audio", audio_dir)
                            window.open_directory("subtitle", sub_dir)
                        self.select_file(window, "audio", audio_dir / "Show 05.mka")
                        self.select_file(window, "subtitle", sub_dir / "Show 05.ass")
                        with patch("media_picker.subprocess.Popen") as popen:
                            self.select_file(window, "video", videos[1])
                        popen.assert_not_called()
                        self.assertEqual(window.selected["audio"], audio_dir / "Show 06.mka")
                        self.assertEqual(window.selected["subtitle"], sub_dir / "Show 06.ass")
                        self.assertEqual(window.mode_boxes["audio"].isChecked(), search)
                        if not search:
                            self.assertEqual(window.directories["audio"], audio_dir)
                            self.assertEqual(window.lists["audio"].currentItem().data(PATH_ROLE),
                                             str(audio_dir / "Show 06.mka"))
                    finally:
                        window.close()

    def test_manual_video_change_keeps_source_through_video_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / "Season A", root / "Season B"
            for folder, number in ((old, "05"), (new, "06")):
                folder.mkdir()
                (folder / f"Show {number}.mkv").touch()
                sound = folder / "Sound" / "AniStar"
                sound.mkdir(parents=True)
                (sound / f"Show {number}.mka").touch()
            window = self.window_for(old)
            try:
                self.select_file(window, "video", old / "Show 05.mkv")
                window.open_directory("audio", old / "Sound" / "AniStar")
                self.select_file(window, "audio", old / "Sound" / "AniStar" / "Show 05.mka")
                window.open_directory("video", new)
                self.assertIsNone(window.selected["audio"])
                with patch("media_picker.subprocess.Popen") as popen:
                    self.select_file(window, "video", new / "Show 06.mkv")
                popen.assert_not_called()
                self.assertEqual(window.selected["audio"],
                                 new / "Sound" / "AniStar" / "Show 06.mka")
            finally:
                window.close()

    def test_missing_source_does_not_fall_back_to_other_auto_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for number in ("05", "06"):
                (root / f"Show {number}.mkv").touch()
            first, other = root / "AniStar", root / "Other"
            first.mkdir()
            other.mkdir()
            (first / "Show 05.mka").touch()
            (other / "Show 06.mka").touch()
            window = self.window_for(root)
            try:
                window.auto.setChecked(True)
                window.mode_boxes["audio"].setChecked(True)
                self.select_file(window, "video", root / "Show 05.mkv")
                self.assertEqual(window.selected["audio"], first / "Show 05.mka")
                self.select_file(window, "video", root / "Show 06.mkv")
                self.assertIsNone(window.selected["audio"])
                self.assertFalse(window.watch.isEnabled())
                self.assertIn("AniStar", window.status_labels["audio"].text())
                window.lists["audio"].setCurrentRow(0)
                self.assertTrue(window.watch.isEnabled())
            finally:
                window.close()

    def test_video_only_launch_and_ambiguous_auto_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "Фильм 02.mkv"
            audio = root / "Фильм 02.mka"
            video.touch()
            audio.touch()
            settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            for kind in ("video", "audio", "subtitle"):
                settings.setValue(f"paths/{kind}", str(root))
            settings.setValue("options/auto_select", True)
            window = MediaPicker(settings)
            try:
                for row in range(window.lists["video"].count()):
                    if window.lists["video"].item(row).text() == video.name:
                        window.lists["video"].setCurrentRow(row)
                        break
                self.assertTrue(window.watch.isEnabled())
                self.assertEqual(window.selected["audio"], audio)
                (root / "Фильм 02.AL.mka").touch()
                window.video_changed()
                self.assertIsNone(window.selected["audio"])
                with patch("media_picker.subprocess.Popen") as popen:
                    window.launch()
                    popen.assert_not_called()
                    window.lists["audio"].setCurrentRow(0)
                    window.launch()
                    self.assertEqual(popen.call_args.args[0], ["mpv", str(video)])
            finally:
                window.close()

    def test_parent_navigation_and_saved_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "child"
            child.mkdir()
            settings_path = str(root / "settings.ini")
            settings = QSettings(settings_path, QSettings.Format.IniFormat)
            settings.setValue("paths/video", str(child))
            window = MediaPicker(settings)
            try:
                self.assertEqual(window.lists["video"].item(0).text(), "..")
                window.activate("video", window.lists["video"].item(0))
                self.assertEqual(window.directories["video"], root)
            finally:
                window.close()
            reopened = MediaPicker(QSettings(settings_path, QSettings.Format.IniFormat))
            try:
                self.assertEqual(reopened.directories["video"], root)
            finally:
                reopened.close()

    def test_search_modes_are_independent_and_auto_choice_is_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Фильм 02.mkv").touch()
            for folder, extension in (("Sound A", ".mka"), ("Sound B", ".mka"),
                                      ("Subs", ".ass")):
                target = root / folder
                target.mkdir()
                (target / f"Фильм 02{extension}").touch()
            settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            for kind in ("video", "audio", "subtitle"):
                settings.setValue(f"paths/{kind}", str(root))
            settings.setValue("options/auto_select", True)
            window = MediaPicker(settings)
            try:
                for row in range(window.lists["video"].count()):
                    if window.lists["video"].item(row).text() == "Фильм 02.mkv":
                        window.lists["video"].setCurrentRow(row)
                        break
                window.mode_boxes["audio"].setChecked(True)
                self.assertFalse(window.mode_boxes["subtitle"].isChecked())
                self.assertEqual(window.lists["audio"].count(), 3)
                self.assertIsNone(window.selected["audio"])
                window.mode_boxes["subtitle"].setChecked(True)
                self.assertEqual(window.selected["subtitle"], root / "Subs" / "Фильм 02.ass")
                window.lists["audio"].setCurrentRow(1)
                with patch("media_picker.subprocess.Popen") as popen:
                    window.launch()
                    self.assertEqual(popen.call_args.args[0], [
                        "mpv", str(root / "Фильм 02.mkv"),
                        "--audio-file=" + str(window.selected["audio"]),
                        "--sub-file=" + str(root / "Subs" / "Фильм 02.ass"),
                    ])
                window.lists["subtitle"].setCurrentRow(0)
                self.assertIsNone(window.selected["subtitle"])
                window.mode_boxes["subtitle"].setChecked(False)
                self.assertIsNone(window.selected["subtitle"])
                self.assertEqual(window.directories["subtitle"], root)
            finally:
                window.close()
