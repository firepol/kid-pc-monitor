# Kid PC Monitor

DIY parental control system for parents who code. If you know what 'pip install' means, this is for you!

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Kid PC](https://img.shields.io/badge/kid_PC-Windows%20%7C%20Linux-green.svg)

## How it works

One app — `agent.py` — runs on each kid's PC and does everything: it enforces the daily time limit, locks the screen at bedtime, plays warning sounds as time runs low, logs which programs are used, and serves a single web UI. There is **no separate parent PC or panel** anymore.

The parent just points a browser (phone, laptop, anything on the network) at the kid PC: `http://<kid-pc-ip>:9999`.

- The **kid** sees a read-only "time left" page — no login.
- The **parent** logs in at `/admin` with a single shared password (no username — each parent just picks a chat display name like "Mom"/"Dad" at login) to set limits, lock now, schedule bedtime, send a message, and view usage history.

History, activity and live state are stored in a local SQLite database on the kid PC, so everything survives restarts and you get a usage history over time.

## Features

- **One app per kid PC** — connect your browser straight to it, nothing to run on a parent PC.
- **Password-protected admin** — the kid status page is open; the controls require a parent login.
- **Per-weekday daily limits** — e.g. 90 min on school days, 4 h on weekends, auto-applied each day.
- **Scheduled bedtime locks** — lock automatically at set times.
- **Sound warnings** — a different named sound per minutes-remaining mark (e.g. `15:gentle, 5:urgent`), instead of a mandatory popup. `.wav` works out of the box; `mp3`/`opus`/`ogg`/`flac`/… work too if `ffmpeg` or `mpv` is installed (see [Sounds](#sounds)). Optional on-screen popup too.
- **Once-per-day save session** — after the first lock the kid gets one short window to log back in and save their work.
- **Locked time doesn't count** — stepping away and locking the screen pauses the usage clock.
- **Usage history + activity log** — SQLite-backed; see past days (with a tiny bar chart) and today's top programs on the admin page.
- **Parent ⇄ kid chat** — on the status page. The kid replies from their own page; the parent chats from the same page on their device and sets their display name there (so Mom and Dad differ). A note sent from the admin panel pops up on the kid's screen; a message typed in the chat window just plays a sound there (both configurable — see `[chat]`). Kid replies raise an unread badge + browser notification on the parent's device.
- **Cross-platform** — Windows and Linux kid PCs, behind a small OS-abstraction layer.
- **User-specific monitoring** — restrict to (or exempt) specific OS accounts on a shared PC.

## Requirements

- **Kid PC:** Windows 10/11 or a desktop Linux, with Python 3.9+.
- **Parent:** any device with a browser, on the same network as the kid PC.
- **Network:** the kid PC must accept inbound TCP on the web port (default **9999**) from your device. The Windows installer opens it; on Linux open it with your firewall (e.g. `sudo ufw allow 9999/tcp`).

> Traffic is plain HTTP by default. On a home LAN that's usually fine; the admin side is password-protected. If you expose it beyond your LAN, put it behind HTTPS (e.g. a reverse proxy).

## Quick start

On the kid's PC:

```bash
git clone https://github.com/rookie7799/kid-pc-monitor.git
cd kid-pc-monitor

# recommended: install into a virtual environment (keeps deps off system Python)
python -m venv .venv
# Linux:   source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt

# (optional) customise settings
cp config.ini.example config.ini

# set the parent admin password (stored hashed, never in plain text)
python scripts/set_password.py

# run it
python agent.py
```

A virtual environment is optional for a quick manual run, but **recommended if you'll install the auto-start service** below — see [Run it automatically at startup](#run-it-automatically-at-startup) for how the service is tied to the interpreter you install it with.

Then from any device on the network open `http://<kid-pc-ip>:9999`. To find kid PCs automatically:

```bash
python discover.py     # scans your /24 and prints each agent's URL to bookmark
```

### Run it automatically at startup

> **The auto-start service runs whichever Python interpreter you install it with.** Both installers bake the *absolute path* of the Python that runs them into the service (the Windows scheduled task and the Linux systemd unit). So if you use a virtual environment, **run the installer with that venv's interpreter** — then the service uses the venv (and its installed packages) automatically, with no "activation" needed at runtime. If you later move or rebuild the venv, re-run the installer so the path is updated.
>
> Install the repo somewhere the kid account can read/write (e.g. `C:\KidPCMonitor` or under the kid's home) — **not** `C:\Program Files\…`. The agent writes its SQLite database (and log) next to the repo, and the service runs in the kid's session.

**Windows** — from an **Administrator** prompt, using the venv you created in Quick start. Call the venv's Python by full path so the right interpreter is captured regardless of activation. This creates a logon scheduled task and opens the firewall port:

```cmd
cd C:\KidPCMonitor
:: install deps into the venv first if you haven't:
.venv\Scripts\python.exe -m pip install -r requirements.txt

.venv\Scripts\python.exe scripts\install_windows.py
.venv\Scripts\python.exe scripts\set_password.py
```

The installer **prompts for the kid's Windows account** — the account they log in with, *not* the admin account you're running the installer from. The task is registered to run in **that account's** session at their logon (so it can lock the kid's screen, not the admin's), and the kid account is written to `[monitoring] monitored_users` so only they are restricted. To skip the prompt (e.g. for scripted installs), pass `--user Tommy` (or `--user ""` to run in the installing account's session).

Verify the task points at your venv:

```cmd
schtasks /query /tn KidPCMonitor /fo list /v | findstr "Task To Run"
:: -> "C:\KidPCMonitor\.venv\Scripts\pythonw.exe" "C:\KidPCMonitor\agent.py"
```

Remove it later with `.venv\Scripts\python.exe scripts\install_windows.py --remove`. (Without a venv, just use `python` — the system interpreter is captured instead; make sure `pip install -r requirements.txt` ran against that same interpreter.)

**Linux** (as the kid's user) — installs a systemd user service. The unit's `ExecStart` is set from the `python3` on `PATH` at install time, so **activate the venv first** (or otherwise put it first on `PATH`):

```bash
cd ~/kid-pc-monitor
source .venv/bin/activate          # so the unit captures the venv's python3
scripts/install_linux.sh
python3 scripts/set_password.py
```

Confirm the unit uses the venv with `systemctl --user cat kidmon.service` (look at the `ExecStart=` line). Remove it later with `scripts/install_linux.sh --remove`. Open the web port in your firewall if you want to reach it from another device (e.g. `sudo ufw allow 9999/tcp`).

## Configuration

All settings live in an optional `config.ini` at the repo root (copy `config.ini.example`). Every value falls back to a built-in default, so the file — or any key — is optional. It is gitignored (per-machine).

| Section | Key | Meaning |
|---|---|---|
| `[web]` | `port` | Web UI port (default 9999). |
| `[web]` | `password_hash` | Single shared admin password (no username). Set via `scripts/set_password.py`. |
| `[limits]` | `default` | Daily allowance in minutes for any day not listed. |
| `[limits]` | `monday`..`sunday` | Per-weekday allowance overrides. |
| `[sounds]` | `name = path` | Name your sound files once, then reference them by name in `notify`. Relative paths resolve against the repo root. See [Sounds](#sounds). |
| `[notifications]` | `notify`, `sound_enabled`, `popup_enabled`, `sound_file`, `thresholds` | `notify = 15:gentle, 5:urgent, 1:urgent` maps each minutes-remaining mark to a named sound (the minutes are the alert thresholds). `sound_file` is the fallback; `thresholds` is the legacy single-sound form. |
| `[monitoring]` | `monitored_users`, `exempt_users`, `grace_period_seconds` | Which OS accounts to restrict/exempt, and the save-session length. |
| `[activity]` | `enabled`, `interval_seconds` | Foreground-program logging on/off and sample interval. |
| `[storage]` | `db_path` | SQLite database path (relative to the repo root). |
| `[chat]` | `enabled`, `kid_name`, `admin_popup_enabled`, `chat_sound_enabled`, `chat_sound` | Turn the parent⇄kid chat on/off and set the kid's display name (defaults to the OS username). `admin_popup_enabled` (default on) pops up admin-panel "send message" notes on the kid's screen; a message typed in the chat window instead plays `chat_sound` (a `[sounds]` name or path; empty = system beep) when `chat_sound_enabled`, with no popup. |

The parent can override the day's limit at runtime from the admin page; the configured per-weekday allowance auto-applies again the next day.

### Sounds

The agent plays a warning sound at each minutes-remaining mark. You configure sounds in two sections:

```ini
[sounds]
# Name each sound file once (so you don't repeat full paths below).
# Relative paths resolve against the repo root; absolute paths work too.
gentle = sounds/gentle.wav
bell   = sounds/bell.opus
urgent = /home/kid/alerts/urgent.mp3

[notifications]
sound_enabled = true
# Map each minutes-left mark to a sound name from [sounds]. The minutes listed
# here ARE the alert thresholds — alert at 15, 5, 2 and 1 minutes left.
notify = 15:gentle, 5:bell, 2:urgent, 1:urgent
# Fallback sound for any mark whose name is missing/unknown (empty = system beep).
sound_file = sounds/warning.wav
```

**Supported formats**

- **`.wav` always works** on both Windows and Linux with nothing extra installed (Windows uses the built-in `winsound`; Linux uses `aplay`/`paplay`).
- **`mp3`, `opus`, `ogg`, `flac`, `m4a`/`aac`, `wma`, …** work when a general-purpose player is on `PATH`. The agent looks for [`ffmpeg`](https://ffmpeg.org/)'s `ffplay` first, then [`mpv`](https://mpv.io/). Install either one to use compressed formats:
  - **Windows:** `winget install Gyan.FFmpeg` (or `choco install ffmpeg`), then re-open the session so `PATH` updates.
  - **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg` — or `mpv`.

If you reference a non-`.wav` sound but neither `ffplay` nor `mpv` is installed, the agent logs a warning and falls back to a system beep (Windows) or terminal bell (Linux); enforcement is unaffected. On Linux, `paplay` also covers `ogg`/`flac` even without ffmpeg.

**Paths** — relative paths in `[sounds]` (and `sound_file`) are resolved against the repo root, so `gentle = sounds/gentle.wav` points at `<repo>/sounds/gentle.wav` regardless of where the agent is launched from. Absolute paths (e.g. `C:\sounds\urgent.opus` or `/home/kid/alerts/urgent.mp3`) are used as-is.

**Legacy single-sound form** — instead of `notify`, you can set `thresholds = 15,5,2,1` to play the one `sound_file` at each of those marks. `notify` takes precedence when both are set.

## Project layout

```
agent.py        # entry point — runs on each kid PC (monitor loop + web server)
discover.py     # convenience LAN scanner to find agents
kidmon/         # the package
  config.py         # config.ini loader
  usage_logic.py    # pure: usage-time accounting (locked time excluded)
  grace_logic.py    # pure: once-per-day save-session decision
  warning_logic.py  # pure: pre-lock countdown warnings
  schedule_logic.py # pure: per-weekday allowance selection
  storage.py        # SQLite: state, daily history, activity, messages
  control.py        # the platform-agnostic enforcement engine
  platform/         # OS abstraction (lock / is_locked / foreground / sound)
    base.py, windows.py, linux.py, audio.py  # audio.py: multi-format sound playback
  web/              # single Flask app: kid status (open) + admin (login)
scripts/        # set_password.py, install_windows.py, install_linux.sh
tests/          # unit tests for the pure logic, config and storage
```

The `*_logic` modules are pure and dependency-free, so the core enforcement rules are unit-tested without any OS or Flask involved.

## Running the tests

```bash
# From the repo root — each file runs on its own and prints a line per case
python tests/test_usage_logic.py
python tests/test_grace_logic.py
python tests/test_warning_logic.py
python tests/test_schedule_logic.py
python tests/test_config.py
python tests/test_storage.py

# or, if you prefer:
pip install pytest && pytest tests/
```

## Security notes

- The admin controls are password-protected (werkzeug-hashed); the kid status page is intentionally open.
- Traffic is plain HTTP by default — fine on a trusted LAN, but use HTTPS if exposed further.
- A kid with admin rights on their own PC can stop the process or task. OS-level account separation is what actually enforces this; the app assumes the kid is a standard (non-admin) user.

## License

MIT License — feel free to modify for your family's needs!

**Need Help?** Open an [issue](https://github.com/rookie7799/kid-pc-monitor/issues) or check the [FAQ](docs/FAQ.md).
