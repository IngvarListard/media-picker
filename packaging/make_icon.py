"""Создать файл значка из той же отрисовки, что использует окно."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication

from media_picker import APP_ID, icon_pixmap

TARGET = (Path(__file__).parent / "icons/hicolor/256x256/apps" / f"{APP_ID}.png")


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - нужен для отрисовки QPixmap
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if not icon_pixmap(256).save(str(TARGET)):
        print(f"Не удалось сохранить {TARGET}", file=sys.stderr)
        return 1
    print(TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
