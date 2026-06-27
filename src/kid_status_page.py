"""Read-only "kid" status page.

A friendly browser page on the kid's PC showing how much computer time is
left. It only reads from a PCTimeControl instance - it cannot change any
limits, lock the PC, or run commands. All control still happens from the
parent web panel.
"""
import json
import logging
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Default port for the read-only kid status page. Reachable on the local
# network so the kid can also open it from, e.g., their phone.
DEFAULT_KID_PAGE_PORT = 8080

KID_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Computer Time</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center;
    justify-content: center; font-family: system-ui, "Segoe UI", Roboto, sans-serif;
    background: #0f172a; color: #f8fafc; padding: 1.5rem;
  }
  .card {
    width: 100%; max-width: 460px; background: #1e293b; border-radius: 24px;
    padding: 2.5rem 2rem; text-align: center; box-shadow: 0 20px 50px rgba(0,0,0,.4);
  }
  h1 { font-size: 1.1rem; font-weight: 600; margin: 0 0 1.5rem; color: #94a3b8; }
  .big { font-size: 4.5rem; font-weight: 800; line-height: 1; margin: .25rem 0; }
  .big.green  { color: #4ade80; }
  .big.orange { color: #fbbf24; }
  .big.red    { color: #f87171; }
  .label { font-size: 1.1rem; color: #cbd5e1; margin-bottom: 1.75rem; }
  .details { font-size: .95rem; color: #94a3b8; line-height: 1.7;
             border-top: 1px solid #334155; padding-top: 1.25rem; }
  .details b { color: #e2e8f0; }
  .foot { margin-top: 1.5rem; font-size: .75rem; color: #475569; }
</style>
</head>
<body>
  <div class="card">
    <h1 id="user">My Computer Time</h1>
    <div class="big green" id="big">…</div>
    <div class="label" id="label">Checking…</div>
    <div class="details" id="details"></div>
    <div class="foot">Updates automatically every 15 seconds</div>
  </div>
<script>
function fmt(mins) {
  if (mins >= 60) {
    const h = Math.floor(mins / 60), m = mins % 60;
    return h + "h " + String(m).padStart(2, "0") + "m";
  }
  return mins + " min";
}
function render(s) {
  const big = document.getElementById("big");
  const label = document.getElementById("label");
  const details = document.getElementById("details");
  const user = document.getElementById("user");
  user.textContent = s.user ? s.user + "'s Computer Time" : "My Computer Time";

  if (!s.monitored) {
    big.textContent = "∞"; big.className = "big green";
    label.textContent = "No time limit right now — have fun! 🎉";
    details.innerHTML = ""; return;
  }
  if (s.time_remaining === null || s.time_remaining === undefined) {
    big.textContent = "∞"; big.className = "big green";
    label.textContent = "No limit set right now";
  } else {
    const r = Math.max(0, s.time_remaining);
    big.textContent = fmt(r);
    big.className = "big " + (r > 30 ? "green" : (r > 10 ? "orange" : "red"));
    label.textContent = r <= 0 ? "Time's up!" : "left before the computer locks";
  }
  let d = "";
  if (s.usage_limit) d += "Daily limit: <b>" + fmt(s.usage_limit) + "</b><br>";
  if (s.next_lock)   d += "Next bedtime lock: <b>" + s.next_lock + "</b><br>";
  details.innerHTML = d;
}
async function refresh() {
  try {
    const r = await fetch("/api/status", { cache: "no-store" });
    render(await r.json());
  } catch (e) {
    document.getElementById("label").textContent = "Can't reach the time monitor…";
  }
}
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>"""


def build_kid_status(pc_control):
    """Build a read-only status summary for the kid-facing web page."""
    monitored = pc_control.should_monitor_user()
    remaining = pc_control.get_time_remaining() if monitored else None

    # Find the soonest upcoming scheduled lock time, as "HH:MM"
    next_lock = None
    soonest = None
    now = datetime.now()
    for lt in pc_control.lock_times:
        when = now.replace(hour=lt.hour, minute=lt.minute, second=0, microsecond=0)
        if when <= now:
            when += timedelta(days=1)
        if soonest is None or when < soonest:
            soonest = when
            next_lock = f"{lt.hour:02d}:{lt.minute:02d}"

    return {
        "user": pc_control.current_user,
        "monitored": monitored,
        "time_remaining": int(remaining) if remaining is not None else None,
        "usage_limit": pc_control.usage_limit,
        "lock_times": [f"{lt.hour:02d}:{lt.minute:02d}" for lt in pc_control.lock_times],
        "next_lock": next_lock,
    }


def make_kid_handler(pc_control):
    """Build an HTTP request handler bound to the given PCTimeControl instance."""
    class KidStatusHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # silence default stderr logging (no console under pythonw)

        def _send(self, body, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/status"):
                body = json.dumps(build_kid_status(pc_control)).encode("utf-8")
                self._send(body, "application/json")
            elif self.path == "/" or self.path.startswith("/?"):
                self._send(KID_PAGE_HTML.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self.send_response(404)
                self.end_headers()

    return KidStatusHandler


class KidStatusServer:
    """Serves the read-only kid status page over HTTP on the local network."""
    def __init__(self, pc_control, port=DEFAULT_KID_PAGE_PORT):
        self.pc_control = pc_control
        self.port = port
        self.httpd = None
        self.logger = logging.getLogger('KidStatusServer')

    def start(self):
        try:
            self.httpd = ThreadingHTTPServer(('0.0.0.0', self.port), make_kid_handler(self.pc_control))
            self.logger.info(f"Kid status page available on port {self.port}")
            print(f"[{datetime.now():%H:%M:%S}] Kid status page on http://localhost:{self.port}")
            self.httpd.serve_forever()
        except Exception as e:
            # Best-effort feature: never take down the agent if this fails.
            self.logger.error(f"Kid status page failed to start: {e}")
            print(f"[{datetime.now():%H:%M:%S}] Kid status page disabled: {e}")

    def start_in_thread(self):
        """Start the server on a daemon thread and return the thread."""
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        return thread
