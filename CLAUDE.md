# hands-off

Release tier: **small** — tags `v<major>.<N>` (e.g. v0.2, v0.3), version mirrored in `pyproject.toml` and `handsoff/__init__.py`. Pushing a `v*` tag builds the .deb in GitHub Actions and attaches it to the release. v0.1.0 predates this scheme.

Layout: `handsoff/grabber.py` = shared key logic; backends `evdev_backend.py` (Linux) and `winhook.py` (Windows). Key codes are Linux `KEY_*` numbers = PC set-1 scan codes (`keycodes.py`). Windows build: `packaging/windows/` (PyInstaller zip + per-user install.ps1); CI job `build-windows`.
