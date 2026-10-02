# Project instructions

- Simpler code is better. Fewer lines are better when clarity and correctness stay intact.
- Prefer small functions and immutable data. Keep filesystem matching and sorting as pure functions; keep Qt and process launching at the edges.
- Reuse Python, Qt, and existing project code before adding a dependency or abstraction.
- Implement only the current spec. Avoid frameworks, layers, caches, and settings that the behavior does not require.
- Keep file handling safe: never build a shell command from filenames; pass argument lists to subprocesses.
- Use `uv` for dependencies and running the project.
- Follow the project’s Spec Kit artifacts in `specs/` when implementing a feature.
