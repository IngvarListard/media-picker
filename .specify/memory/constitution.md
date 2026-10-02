# Media Picker Constitution

## Principles

1. Build only the behavior described in the current spec. Prefer the smallest clear implementation.
2. Prefer small pure functions for file discovery, sorting, and matching. Keep GUI state and `mpv` launching at the edges.
3. Use Python, Qt, and standard library features before adding dependencies or abstractions.
4. Keep the interface responsive: avoid repeated full-directory scans on every selection.
5. Show selected paths before launch and pass filenames as subprocess arguments, never through a shell.

## Workflow

Use `uv` for the Python environment. Keep specs, plans, and tasks proportional to this small desktop application. Verify file matching against representative local layouts and check the GUI manually before calling a feature complete.

**Version**: 1.0.0 | **Ratified**: 2026-10-02 | **Last Amended**: 2026-10-02
