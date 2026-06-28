#!/usr/bin/env python3
"""Kid PC Monitor — the agent that runs on each kid PC.

Run this on the kid's computer (the installers set it up to start automatically).
It does everything in one process:

* enforces the daily time limit, scheduled bedtime locks and the once-per-day
  save session;
* plays the configured warning sounds as time runs low;
* logs which programs are used, for the activity history;
* serves a single web UI on the configured port — the kid sees a read-only
  "time left" page, and the parent logs in (password) to control it from their
  own browser at ``http://<this-pc-ip>:<port>``.

No separate parent PC or panel is needed. Usage:

    python agent.py
"""
import logging
import os
import sys

from werkzeug.serving import make_server

from kidmon import config
from kidmon.control import TimeControl
from kidmon.platform import get_platform
from kidmon.storage import Storage
from kidmon.web import create_app

# Log beside the agent, not in the process CWD: under the Windows logon task the
# CWD is %windir%\System32 (not writable by a kid account), which would make a
# bare-relative FileHandler raise and abort startup.
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kidmon.log")


def setup_logging():
    handlers = [logging.StreamHandler()]
    try:
        handlers.insert(0, logging.FileHandler(_LOG_PATH, encoding="utf-8"))
    except OSError as e:
        # Read-only install dir, etc.: keep console logging rather than crash.
        print(f"Could not open log file {_LOG_PATH}: {e}", file=sys.stderr)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def main():
    setup_logging()
    log = logging.getLogger("kidmon.agent")

    try:
        platform = get_platform()
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(1)

    storage = Storage(config.get_db_path())
    control = TimeControl(platform, storage, config)

    app = create_app(control, config, storage)
    port = config.get_web_port()

    # Bind the web port BEFORE starting the enforcement threads: make_server
    # binds immediately, so a failed start (e.g. the port is already in use on a
    # restart race or double launch) exits cleanly here instead of letting the
    # enforcement loop lock the kid's screen and then dying with no agent left
    # to grant the save session or serve the unlock/UI.
    try:
        server = make_server("0.0.0.0", port, app, threaded=True)
    except OSError as e:
        log.error("Cannot bind web port %d: %s", port, e)
        sys.exit(1)

    control.start_threads()
    log.info("Web UI on http://0.0.0.0:%d  (kid status at /, admin at /admin)", port)

    # threaded=True so the kid status page and admin requests don't block each
    # other; the enforcement loops run on their own daemon threads already.
    server.serve_forever()


if __name__ == "__main__":
    main()
