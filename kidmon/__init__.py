"""Kid PC Monitor — the kidmon package.

The monitoring app runs on each kid PC. It serves a single web UI (kid status
page, open; admin controls, password-protected) and enforces daily time limits,
scheduled locks, sound notifications and activity logging. The parent connects
their browser directly to ``http://<kid-ip>:<port>``.

Pure, OS-independent decision logic lives in the small ``*_logic`` modules
(usage / grace / warning / schedule) and is unit-tested in ``tests/``. All
OS-specific actions (lock, detect-lock, foreground process, play sound) live
behind the ``kidmon.platform`` abstraction with Windows and Linux backends.
"""
