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
import sys

from kidmon import config
from kidmon.control import TimeControl
from kidmon.platform import get_platform
from kidmon.storage import Storage
from kidmon.web import create_app


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler("kidmon.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
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
    control.start_threads()

    app = create_app(control, config, storage)
    port = config.get_web_port()
    log.info("Web UI on http://0.0.0.0:%d  (kid status at /, admin at /admin)", port)

    # threaded=True so the kid status page and admin requests don't block each
    # other; the enforcement loops run on their own daemon threads already.
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
