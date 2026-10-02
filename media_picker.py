"""Browse local media and launch mpv with optional external tracks."""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from files import (DEFAULT_EXTENSIONS, is_next_episode, list_directory, matching,
                   parse_extensions, source_folder, source_matches)

PATH_ROLE = Qt.ItemDataRole.UserRole
TYPE_ROLE = Qt.ItemDataRole.UserRole + 1
KINDS = ("video", "audio", "subtitle")
NAMES = {"video": "Видео", "audio": "Аудио", "subtitle": "Субтитры"}


def file_item(path: Path, label: str, kind: str) -> QListWidgetItem:
    entry = QListWidgetItem(label)
    entry.setData(PATH_ROLE, str(path))
    entry.setData(TYPE_ROLE, kind)
    entry.setToolTip(str(path))
    return entry


class MediaPicker(QWidget):
    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings or QSettings(
            QSettings.Format.IniFormat, QSettings.Scope.UserScope, "MediaPicker", "MediaPicker"
        )
        default_dir = Path.home() / "Downloads"
        if not default_dir.is_dir():
            default_dir = Path.home()
        self.directories = {}
        self.extensions = {}
        self.selected: dict[str, Path | None] = dict.fromkeys(KINDS)
        self.sources: dict[str, Path | None] = {"audio": None, "subtitle": None}
        self.issues: dict[str, str] = {"audio": "", "subtitle": ""}
        self.lists: dict[str, QListWidget] = {}
        self.folder_fields: dict[str, QLineEdit] = {}
        self.path_fields: dict[str, QLineEdit] = {}
        self.mode_boxes: dict[str, QCheckBox] = {}
        self.status_labels: dict[str, QLabel] = {}
        self.snapshot_root: Path | None = None
        self.snapshot: tuple[list[Path], list[Path], list[Path]] = ([], [], [])

        for kind in KINDS:
            key = f"extensions/{kind}"
            default = ",".join(sorted(DEFAULT_EXTENSIONS[kind]))
            raw = self.settings.value(key, default)
            self.extensions[kind] = parse_extensions(str(raw))
            if not self.settings.contains(key):
                self.settings.setValue(key, default)
            last = Path(str(self.settings.value(f"paths/{kind}", str(default_dir)))).expanduser()
            self.directories[kind] = last if last.is_dir() else default_dir
        self.settings.sync()

        self.setWindowTitle("Media Picker")
        self.resize(1200, 640)
        layout = QVBoxLayout(self)
        columns = QHBoxLayout()
        layout.addLayout(columns)
        for kind in KINDS:
            columns.addWidget(self.make_panel(kind), 1)

        controls = QHBoxLayout()
        self.follow = QCheckBox("Панели следуют за видео")
        self.follow.setChecked(self.settings.value("options/follow_video", True, type=bool))
        self.auto = QCheckBox("Автовыбор совпадения")
        self.auto.setChecked(self.settings.value("options/auto_select", False, type=bool))
        controls.addWidget(self.follow)
        controls.addWidget(self.auto)
        controls.addStretch()
        layout.addLayout(controls)
        self.watch = QPushButton("▶ Смотреть")
        self.watch.setEnabled(False)
        self.next = QPushButton("Следующая серия")
        self.next.setEnabled(False)
        actions = QHBoxLayout()
        actions.addWidget(self.watch)
        actions.addWidget(self.next)
        layout.addLayout(actions)

        self.follow.toggled.connect(lambda value: self.settings.setValue("options/follow_video", value))
        self.auto.toggled.connect(self.auto_changed)
        self.watch.clicked.connect(self.launch)
        self.next.clicked.connect(self.next_episode)
        for kind in KINDS:
            self.fill(kind)

    def make_panel(self, kind: str) -> QGroupBox:
        box = QGroupBox(NAMES[kind])
        layout = QVBoxLayout(box)
        folder = QLineEdit()
        folder.setReadOnly(True)
        folder.setAccessibleName(f"Текущая папка: {NAMES[kind]}")
        choices = QListWidget()
        choices.setAccessibleName(f"Файлы: {NAMES[kind]}")
        selected = QLineEdit()
        selected.setReadOnly(True)
        selected.setPlaceholderText("Файл не выбран")
        selected.setAccessibleName(f"Выбранный файл: {NAMES[kind]}")
        status = QLabel()
        status.setWordWrap(True)
        self.folder_fields[kind] = folder
        self.lists[kind] = choices
        self.path_fields[kind] = selected
        self.status_labels[kind] = status
        layout.addWidget(folder)
        if kind != "video":
            mode = QCheckBox("Поиск во вложенных папках")
            self.mode_boxes[kind] = mode
            layout.addWidget(mode)
            mode.toggled.connect(lambda _checked, k=kind: self.mode_changed(k))
        layout.addWidget(choices)
        layout.addWidget(selected)
        layout.addWidget(status)
        choices.currentItemChanged.connect(
            lambda current, _previous, k=kind: self.choice_changed(k, current)
        )
        choices.itemDoubleClicked.connect(lambda entry, k=kind: self.activate(k, entry))
        return box

    def candidates(self, kind: str) -> list[Path]:
        if kind != "video" and self.mode_boxes[kind].isChecked():
            video = self.selected["video"]
            if video is None:
                return []
            self.scan_tracks(video.parent)
            index = 0 if kind == "audio" else 1
            return matching(video, self.snapshot[index])
        return [path for path in list_directory(self.directories[kind], self.extensions[kind])
                if path.is_file()]

    def fill(self, kind: str):
        choices = self.lists[kind]
        choices.blockSignals(True)
        choices.clear()
        if kind != "video":
            empty = QListWidgetItem("Без внешней дорожки")
            empty.setData(TYPE_ROLE, "none")
            choices.addItem(empty)
        directory = self.directories[kind]
        self.folder_fields[kind].setText(str(directory))
        self.folder_fields[kind].setToolTip(str(directory))
        search = kind != "video" and self.mode_boxes[kind].isChecked()
        try:
            if search:
                paths = self.candidates(kind)
                root = self.selected["video"].parent if self.selected["video"] else directory
                for path in paths:
                    choices.addItem(file_item(path, str(path.relative_to(root)), "file"))
                errors = self.snapshot[2] if self.selected["video"] else []
                self.status_labels[kind].setText(
                    f"Не удалось прочитать: {errors[0]}" if errors else ""
                )
            else:
                if directory.parent != directory:
                    choices.addItem(file_item(directory.parent, "..", "folder"))
                for path in list_directory(directory, self.extensions[kind]):
                    label = f"📁 {path.name}" if path.is_dir() else path.name
                    choices.addItem(file_item(path, label, "folder" if path.is_dir() else "file"))
                self.status_labels[kind].setText("")
        except OSError as error:
            self.status_labels[kind].setText(f"Не удалось открыть папку: {error}")
        selected = self.selected[kind]
        if selected:
            for row in range(choices.count()):
                entry = choices.item(row)
                if entry.data(TYPE_ROLE) == "file" and entry.data(PATH_ROLE) == str(selected):
                    choices.setCurrentRow(row)
                    break
        choices.blockSignals(False)
        self.show_selected(kind)

    def show_selected(self, kind: str):
        path = self.selected[kind]
        value = str(path) if path else ""
        field = self.path_fields[kind]
        field.setText(value)
        field.setToolTip(value)

    def choice_changed(self, kind: str, entry: QListWidgetItem | None):
        path = Path(entry.data(PATH_ROLE)) if entry and entry.data(TYPE_ROLE) == "file" else None
        self.selected[kind] = path
        if kind != "video" and (path or entry and entry.data(TYPE_ROLE) == "none"):
            self.sources[kind] = (source_folder(self.selected["video"], path)
                                  if path and self.selected["video"] else path.parent if path else None)
            self.issues[kind] = ""
            self.status_labels[kind].setText("")
        self.show_selected(kind)
        if kind == "video":
            self.video_changed()
        self.update_actions()

    def activate(self, kind: str, entry: QListWidgetItem):
        if entry.data(TYPE_ROLE) == "folder":
            self.open_directory(kind, Path(entry.data(PATH_ROLE)))

    def open_directory(self, kind: str, path: Path):
        try:
            list_directory(path, self.extensions[kind])
        except OSError as error:
            self.status_labels[kind].setText(f"Не удалось открыть папку: {error}")
            return
        self.directories[kind] = path
        self.settings.setValue(f"paths/{kind}", str(path))
        self.selected[kind] = None
        self.fill(kind)
        if kind == "video":
            self.video_changed()
            self.update_actions()
        elif self.issues[kind]:
            self.status_labels[kind].setText(self.issues[kind])

    def video_changed(self):
        video = self.selected["video"]
        self.status_labels["video"].setText("")
        for kind in ("audio", "subtitle"):
            self.selected[kind] = None
            if video and self.follow.isChecked():
                self.directories[kind] = video.parent
                self.settings.setValue(f"paths/{kind}", str(video.parent))
            self.issues[kind] = ""
            source = self.sources[kind]
            if video and source is not None:
                folder = source if source.is_absolute() else video.parent / source
                try:
                    matches = source_matches(video, source, self.extensions[kind])
                except OSError:
                    matches = []
                if len(matches) == 1:
                    self.selected[kind] = matches[0]
                    if not self.mode_boxes[kind].isChecked():
                        self.directories[kind] = matches[0].parent
                        self.settings.setValue(f"paths/{kind}", str(matches[0].parent))
                else:
                    self.issues[kind] = (f"Нет дорожки из {folder}" if not matches else
                                         f"Несколько дорожек в {folder}: выберите вручную")
                    if folder.is_dir() and not self.mode_boxes[kind].isChecked():
                        self.directories[kind] = folder
                        self.settings.setValue(f"paths/{kind}", str(folder))
            self.fill(kind)
            if video and source is None:
                self.auto_select(kind)
            if self.issues[kind]:
                self.status_labels[kind].setText(self.issues[kind])
        self.update_actions()

    def update_actions(self):
        video = self.selected["video"] is not None
        self.watch.setEnabled(video and not any(self.issues.values()))
        self.next.setEnabled(video)

    def next_episode(self):
        video = self.selected["video"]
        if video is None:
            return
        if any(self.issues.values()):
            self.status_labels["video"].setText("Сначала выберите недостающую дорожку")
            return
        choices = self.lists["video"]
        matches = []
        for row in range(choices.currentRow() + 1, choices.count()):
            entry = choices.item(row)
            if entry.data(TYPE_ROLE) == "file":
                candidate = Path(entry.data(PATH_ROLE))
                if is_next_episode(video, candidate):
                    matches.append(row)
        if len(matches) == 1:
            choices.setCurrentRow(matches[0])
            if not any(self.issues.values()):
                self.launch()
        else:
            self.status_labels["video"].setText(
                "Следующая серия (+1) не найдена" if not matches else
                "Несколько подходящих следующих серий"
            )

    def auto_select(self, kind: str):
        video = self.selected["video"]
        if not video or not self.auto.isChecked():
            return
        try:
            candidates = matching(video, self.candidates(kind))
        except OSError:
            return
        if len(candidates) == 1:
            self.selected[kind] = candidates[0]
            self.sources[kind] = source_folder(video, candidates[0])
            self.fill(kind)

    def auto_changed(self, enabled: bool):
        self.settings.setValue("options/auto_select", enabled)
        if enabled:
            for kind in ("audio", "subtitle"):
                if self.selected[kind] is None and not self.issues[kind]:
                    self.auto_select(kind)

    def mode_changed(self, kind: str):
        self.selected[kind] = None
        if not self.issues[kind]:
            self.sources[kind] = None
        if self.mode_boxes[kind].isChecked() and self.selected["video"]:
            self.scan_tracks(self.selected["video"].parent, force=True)
        self.fill(kind)
        if not self.issues[kind]:
            self.auto_select(kind)
        else:
            self.status_labels[kind].setText(self.issues[kind])
        self.update_actions()

    def scan_tracks(self, root: Path, force: bool = False):
        if force or self.snapshot_root != root:
            from files import scan_tracks
            self.snapshot = scan_tracks(root, self.extensions["audio"], self.extensions["subtitle"])
            self.snapshot_root = root

    def launch(self):
        video = self.selected["video"]
        if not video or any(self.issues.values()):
            return
        for path in self.selected.values():
            if path and not path.is_file():
                QMessageBox.warning(self, "Файл недоступен", f"Файл не найден:\n{path}")
                return
        command = ["mpv", str(video)]
        if self.selected["audio"]:
            command.append("--audio-file=" + str(self.selected["audio"]))
        if self.selected["subtitle"]:
            command.append("--sub-file=" + str(self.selected["subtitle"]))
        try:
            subprocess.Popen(command, start_new_session=True)
        except OSError as error:
            QMessageBox.critical(self, "Не удалось запустить mpv", str(error))


def main():
    app = QApplication(sys.argv)
    window = MediaPicker()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
