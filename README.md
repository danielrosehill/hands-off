# Hands Off

**Toddler-proof keyboard & mouse lock for Linux and Windows.**

A small child grabs the laptop and starts mashing keys and dragging the mouse
into your open apps. Hands Off lets you *instantly freeze* the keyboard (and
optionally the mouse) with a hot-key, then unlock it with a secret word or a
click on the tray icon.

It grabs input at the kernel level with `evdev` (`EVIOCGRAB`), so the lock works
the same under **X11 and Wayland** — no other application receives the events
while a lock is active.

## How it works

- **Activate the lock:** press **Num-pad `*` + `-`** together (they sit next to
  each other and are almost never pressed together by accident). A notification
  confirms *Hands Off ON*, and the tray icon turns red.
- **Unlock:** type the secret word — **`quit`** by default. Because the keyboard
  is grabbed, the word never leaks into any application. If the mouse isn't
  locked, you can also left-click the tray icon.

- **Num-pad toggle code (optional):** set a 4–8 digit PIN in Settings and type it
  on the **numeric keypad** to toggle the lock on *and* off. Only Num-pad digit
  keys count — top-row digits, letters and your other shortcuts are ignored — and
  any other key or a 3-second pause resets entry, so key-mashing practically never
  hits it. The lock engages on *release* of the last digit, so no key is left
  stuck. Trade-off: when you lock, the code's digits have already reached the
  focused app (the keyboard isn't grabbed yet), so lock from somewhere harmless.

All unlock methods are toggleable in Settings — handy when an older child has
figured out the tray-click and you want to leave only the typed word.

## Settings

Right-click the tray icon → **Settings…** (stored in `~/.config/handsoff/config.json`):

| Setting | Default | Notes |
|---|---|---|
| Num-pad toggle code | *(blank = off)* | 4–8 digits, Num-pad only, toggles lock on/off |
| Unlock word | `quit` | Typed to release the lock |
| Unlock by typing the word | on | |
| Unlock by clicking the tray icon | on | Only usable when the mouse is *not* locked |
| Also lock the mouse | on | Full lockdown; use the typed word to unlock |
| Show notifications | on | Desktop notifications named "Hands Off" (via `notify-send`) |
| Play voice announcements | on | Spoken "Lock enabled" / "Unlocked" clips |

Activation keys and combo/sequence mode are configurable in the JSON file
(`activation_keys`, `activation_mode`).

## Voice announcements

`handsoff/resources/sounds/locked.ogg` and `unlocked.ogg` are spoken by Herman
Poppleberry, a cast voice from the *My Weird Prompts* podcast, rendered on
2026-11-18 with the MWP OmniVoice adapter set `v3` (same pipeline as
[MWP-Announcer](https://github.com/My-Weird-Prompts/MWP-Announcer),
`scripts/render_voices.py`). Ogg Opus, 48 kHz mono, loudnorm −16 LUFS. Lines:
"Hands Off. Lock enabled." / "Hands Off. Unlocked." Played with `pw-play`,
falling back to `paplay` or `ffplay`. Swap in your own clips by replacing the
two files.

## Building

The .deb is plain `dpkg-deb` — no compilation, builds in a second locally with
`./build-deb.sh`. Pushing a `v*` tag also builds it in GitHub Actions and
attaches it to the release.

## Install (Windows 10/11)

Download `HandsOff-<version>-windows.zip` from the
[latest release](https://github.com/danielrosehill/hands-off/releases/latest),
extract it, then run:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

No admin rights needed. It installs to `%LOCALAPPDATA%\Programs\HandsOff`, adds
Start-menu and Startup shortcuts and starts the tray app. Settings live in
`%APPDATA%\HandsOff\config.json`. Remove with `uninstall.ps1`.

How the Windows build works and its limits:

- Low-level keyboard/mouse hooks (`WH_KEYBOARD_LL`, `WH_MOUSE_LL`) swallow input
  while locked (`handsoff/winhook.py`). Keys are matched by hardware scan code,
  so the Num-pad code works whether NumLock is on or off.
- Windows never lets an app block **Ctrl+Alt+Del** or **Win+L**, and a normal
  (non-elevated) app can't block input going to an *elevated* window that has
  focus (e.g. an admin prompt).
- Synthetic input (remote-desktop tools, automation) is deliberately not
  blocked, so a remote session can still unlock.
- Built with PyInstaller by `packaging/windows/build.ps1` (also run in GitHub
  Actions on every `v*` tag).

## Install (Debian / Ubuntu / KDE)

```bash
./build-deb.sh
sudo dpkg -i dist/handsoff_*.deb
sudo apt-get -f install      # pull deps if needed
```

The package installs a launcher, an app-menu entry, and an autostart entry so
Hands Off runs on login.

### Permissions

Grabbing input devices requires membership in the `input` group. The package's
post-install step adds the installing user automatically; **log out and back in**
for it to take effect. To do it manually:

```bash
sudo usermod -aG input "$USER"
```

## Run from source

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
python -m handsoff
```

(You still need to be in the `input` group.)

## License

MIT — see [LICENSE](LICENSE).
