# Распространение Media Picker на Linux

## Цель

Чтобы приложение ставилось на **любой Linux-десктоп (включая GNOME, где нет Qt)** одной командой, без клонирования репозитория и запуска скрипта, и при этом понятно сообщало, что нужно доустановить. Внешний `mpv` остаётся требованием системы — по вашему выбору его ставит пользователь, приложение лишь помогает с этим.

## Проверенные факты (на них опирается план)

- **Qt не надо ставить отдельно.** `.venv/lib/python3.12/site-packages/PySide6` = 648 МБ и содержит `libQt6Core.so.6`, `libQt6Gui.so.6`, `libQt6Widgets.so.6`. Колёса PySide6 с PyPI везут Qt с собой, поэтому GNOME без Qt не помеха.
- **Хватит `pyside6-essentials`.** Код импортирует только `QtCore` и `QtWidgets` (`media_picker.py`, `files.py`, тесты). Essentials включает QtCore/QtGui/QtWidgets/QtSvg/QtDBus и др., но не Addons (WebEngine, 3D, Charts) → пакет и сборки заметно легче.
- **Пол по glibc.** В `uv.lock` колёса PySide6 6.11.2 — `manylinux_2_34_x86_64` и `manylinux_2_39_aarch64`, то есть на x86_64 нужен glibc ≥ 2.34 (Ubuntu 22.04+, Debian 12+, Fedora 35+). Для Debian 11 и RHEL 8 нужен пин `pyside6-essentials==6.6.*` (manylinux_2_28) или сборка AppImage.
- **Имя на PyPI свободно:** `GET https://pypi.org/pypi/media-picker/json` → HTTP 404.
- **Репозиторий:** `github.com:IngvarListard/media-picker`, ветка `master`, CI нет, `pyproject.toml` без `[build-system]` и entry point, иконки и `.desktop` нет.
- **Правила проекта:** спеки ведутся в `specs/00N-*` (есть 001–003), скрипты — `.specify/scripts/bash/{create-new-feature,setup-plan,setup-tasks}.sh`.

## Шаг 1. Артефакты Spec Kit (правило проекта)

```sh
.specify/scripts/bash/create-new-feature.sh --json --short-name "distribute-linux" \
  "Distribute Media Picker as an installable Linux package"
.specify/scripts/bash/setup-plan.sh --json
```

Заполнить `specs/004-distribute-linux/spec.md`, `plan.md`, `tasks.md` по шагам ниже (spec — что получает пользователь, plan — как, tasks — этот список работ).

**Проверка:** каталог `specs/004-distribute-linux/` с четырьмя файлами; `tasks.md` покрывает шаги 2–6.

## Шаг 2. Превратить скрипт в устанавливаемый пакет

Файлы: `pyproject.toml` (+ перегенерация `uv.lock`).

- `[build-system]` → setuptools, `[tool.setuptools] py-modules = ["media_picker", "files"]`. Так **не нужно двигать файлы**: `files.py` остаётся рядом, импорты и тесты не меняются. (Альтернатива — перенести оба модуля в пакет `media_picker/`; она оправдана только если появятся пакетные данные.)
- `dependencies = ["pyside6-essentials>=6.11.2"]` вместо `pyside6`.
- `[project.scripts] media-picker = "media_picker:main"` — `main()` уже готова, кода менять не надо.
- Добавить `description`, `license`, `readme`, `classifiers`, `[project.urls]`.

**Проверка:** `uv sync` работает; `uv run media-picker` открывает окно.

## Шаг 3. Не падать без mpv и уважать локализованные пути

Файлы: `media_picker.py`, `files.py`, `tests/` (новый `tests/test_launch.py`).

- `find_mpv(explicit: str | None, path: str | None) -> str | None` — чистая функция: сначала явный путь (если задан и существует), затем `shutil.which("mpv")` по `PATH`. Никаких shell-строк, только список аргументов.
- Новая настройка `options/mpv_path` в INI (пусто = искать в `PATH`). Поле в UI **не добавляем**, чтобы не расширять текущую спеку — только документируем в README.
- `mpv` не найден → понятный текст с командами: Debian/Ubuntu `sudo apt install mpv`, Fedora `sudo dnf install mpv`, Arch `sudo pacman -S mpv`, Flatpak `flatpak install flathub io.mpv.Mpv`. Кнопка «Смотреть» остаётся активной, чтобы после установки не перезапускать приложение.
- `QStandardPaths.writableLocation(DownloadLocation)` вместо `Path.home() / "Downloads"` — на локализованных системах папка может зваться «Загрузки».
- При старте, если mpv не найден, показать это в статус-строке колонки видео (мягко, без модального окна).
- `start_new_session=True` оставляем — на Linux это правильно.

**Проверка:** `uv run python -m unittest discover -s tests` зелёный; новые тесты на `find_mpv` (явный путь есть/нет, `which` нашёл/нет) и на текст подсказки (содержит apt/dnf/pacman).

## Шаг 4. Доказать, что пакет действительно ставится

```sh
uv build
uv tool install --force ./dist/media_picker-0.1.0-py3-none-any.whl
cd /tmp && media-picker          # запуск вне репозитория
```

- Окно открывается из `/tmp`, настройки пишутся в `~/.config/MediaPicker/MediaPicker.ini`.
- Без mpv: `options/mpv_path=/nonexistent` в INI → диалог с подсказкой, приложение не падает.
- Проверка независимости от KDE: `QT_QPA_PLATFORM=wayland`, затем `QT_QPA_PLATFORM=xcb`, затем `XDG_CURRENT_DESKTOP=GNOME` — окно стартует и в каждом случае.
- `uv run python -m unittest discover -s tests` — зелёный.

## Шаг 5. Иконка и .desktop для AppImage и ручной установки

Файлы: `packaging/media-picker.desktop`, `packaging/icons/hicolor/256x256/apps/media-picker.png`, `packaging/io.github.IngvarListard.MediaPicker.metainfo.xml`.

- Иконку **не кладём в колесо**: при `pip`/`uv tool install` оболочка всё равно не подхватит `.desktop` из venv. Для PyPI-пути это косметика, для AppImage/Flatpak — обязательный вход.
- В README: две команды ручной установки (`cp` в `~/.local/share/applications` и `~/.local/share/icons/hicolor/256x256/apps`, затем `update-desktop-database ~/.local/share/applications`).
- **Опционально и отдельно:** `Exec=media-picker %F` и приём пути к видео аргументом — открывать файл из файлового менеджера. Это правка `main()` и новая проверка; делать только если нужно.

**Проверка:** `.desktop` проходит `desktop-file-validate`, метаинфо — `appstreamcli validate` (если установлены; иначе просто визуальная сверка с требованиями).

## Шаг 6. Раздача через CI

Файлы: `.github/workflows/ci.yml`, `.github/workflows/release.yml`.

- CI: тесты на Python 3.12 и 3.13 (`uv run python -m unittest discover -s tests`), `uv build`, `uvx twine check dist/*`, артефакты в job.
- Release по тегу `v*`: сборка и публикация на PyPI через **Trusted Publishing** (нужны ваши действия: аккаунт PyPI + publisher для репозитория), плюс wheel/sdist в GitHub Release.
- Пока PyPI не настроен, раздача уже работает из git:
  `uvx --from git+ssh://git@github.com/IngvarListard/media-picker.git media-picker`
- README: раздел «Установка» — три пути (uv tool / pipx / из git), таблица команд установки mpv по дистрибутивам и оговорка про glibc ≥ 2.34 для установки из PyPI.

**Проверка:** workflow зелёный на push; установка из git-ссылки в чистом окружении открывает окно.

## Шаг 7 (отдельная фича, если понадобится). AppImage — «скачал и запустил» без Python

- Сборка через `linuxdeploy-plugin-python` или `python-appimage` на базе Ubuntu 22.04 → пол glibc 2.35, ниже не получится из-за PySide6 6.11.
- Известные грабли PySide6+AppImage: нужны xcb-плагины, бывают segfault; почти наверняка потребуется Docker-образ и отладка.
- Проверка: запуск в контейнерах `ubuntu:24.04`, `debian:12`, `fedora:latest`, `archlinux` — окно стартует и вызывается системный mpv.
- Для Debian 11 / RHEL 8 — отдельная сборка с пином `pyside6-essentials==6.6.*`, либо не поддерживать.

## Явно вне объёма

- **Flatpak** (по вашему выбору «mpv ставим отдельно»): в песочнице внешний mpv недоступен, нужен `flatpak-spawn --host mpv` и разрешение `--talk-name=org.freedesktop.Flatpak`, либо сборка mpv внутрь — это противоречит выбору. Вернуться можно отдельной фичей.
- Windows, macOS, Snap, AUR, автообновления, подпись кода.

## Риски и неизвестности

| Риск | Что делаем |
|---|---|
| PySide6 6.11 требует glibc ≥ 2.34 | Честно пишем в README; для старых систем — пин 6.6.* или AppImage |
| Мелкий риск упаковки плоских модулей (`files.py` рядом) | Проверяется шагом 4; запасной вариант — перенос в пакет `media_picker/` |
| AppImage с PySide6 капризен | Отдельная фича (шаг 7), не блокирует шаги 2–6 |
| Trusted Publishing требует действий в аккаунте PyPI | Пока не настроено — раздача из git-ссылки |
| Локально нет GNOME для честного теста | Проверяем плагины и переменные окружения (`XDG_CURRENT_DESKTOP=GNOME`), остальное — по отзывам пользователей |
| Имя `media-picker` на PyPI свободно, но никем не зарезервировано | Занять публикацией на шаге 6 |

## Порядок и объём

Шаги 1–4 — один вечер, дают главное: ставится через `uv tool install` на GNOME и KDE, mpv ставится отдельно с понятной подсказкой. Шаг 5–6 — ещё вечер. Шаг 7 — отдельная работа на несколько дней, браться только после того, как PyPI-путь обкатан.
