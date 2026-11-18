"""Configuration loading and saving.

Settings live in ``~/.config/handsoff/config.json`` and are created with sane
defaults on first run.
"""
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "handsoff"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS = {
    # Keys (evdev names) that trigger a lock. Defaults to the numeric keypad
    # asterisk and minus, which sit next to each other and are almost never
    # pressed together by accident.
    "activation_keys": ["KEY_KPASTERISK", "KEY_KPMINUS"],
    # "combo"    -> both keys held down at the same time
    # "sequence" -> the keys pressed one after another, in order
    "activation_mode": "combo",
    # The secret word the parent types to unlock.
    "unlock_word": "quit",
    # Numeric-keypad PIN that toggles the lock on AND off (e.g. "4827").
    # Only Num-pad digits count; any other key or a 3 s pause resets entry.
    # Empty = disabled.
    "toggle_code": "",
    "allow_unlock_word": True,
    "allow_unlock_tray": True,
    # Lock the mouse too, not just the keyboard. When True the tray icon can't
    # be clicked while locked, so use the unlock word instead.
    "grab_mouse": True,
    "notifications": True,
    # Spoken announcements on lock/unlock (bundled clips, Herman Poppleberry voice).
    "sounds": True,
}


def load_config():
    """Return the merged config, writing defaults out on first run."""
    data = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH) as f:
            data.update(json.load(f))
    except FileNotFoundError:
        save_config(data)
    except (json.JSONDecodeError, OSError):
        pass
    return data


def save_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
