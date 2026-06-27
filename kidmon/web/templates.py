"""Inline HTML templates for the web UI.

Kept as Python strings (rendered with ``render_template_string``) rather than a
``templates/`` directory: it keeps the whole web layer in the package without a
separate template-path/packaging concern, and the repo's .gitignore historically
ignored ``templates/``.
"""

# Open, read-only page the kid sees: how much time is left.
KID_PAGE = """<!DOCTYPE html>
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
    flex-direction: column; justify-content: center;
    font-family: system-ui, "Segoe UI", Roboto, sans-serif;
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
  .foot a { color: #64748b; }
  .chat { width: 100%; max-width: 460px; margin-top: 1rem; background: #1e293b;
          border-radius: 20px; padding: 1rem 1.1rem; display: none; flex-direction: column; }
  .chat h2 { font-size: .95rem; font-weight: 600; color: #94a3b8;
             margin: .1rem .1rem .7rem; display: flex; justify-content: space-between; align-items: center; }
  .asname { font-weight: 400; font-size: .78rem; color: #93c5fd; cursor: pointer; }
  .msgs { display: flex; flex-direction: column; gap: .4rem; max-height: 46vh;
          overflow-y: auto; padding: .2rem; }
  .empty { color: #64748b; font-size: .85rem; text-align: center; padding: 1rem 0; }
  .msg { max-width: 82%; padding: .45rem .7rem; border-radius: 14px; font-size: .9rem; line-height: 1.3; word-wrap: break-word; }
  .msg .who { display: block; font-size: .68rem; opacity: .75; margin-bottom: .1rem; }
  .msg.me   { align-self: flex-end;   background: #2563eb; color: #fff; border-bottom-right-radius: 4px; }
  .msg.them { align-self: flex-start; background: #334155; color: #e2e8f0; border-bottom-left-radius: 4px; }
  .composer { display: flex; gap: .4rem; margin-top: .7rem; }
  .composer input { flex: 1; padding: .6rem; border-radius: 10px; border: 1px solid #334155;
                    background: #0f172a; color: #f8fafc; }
  .composer button { padding: .6rem .9rem; border: none; border-radius: 10px;
                     background: #2563eb; color: #fff; cursor: pointer; }
</style>
</head>
<body>
  <div class="card">
    <h1 id="user">My Computer Time</h1>
    <div class="big green" id="big">…</div>
    <div class="label" id="label">Checking…</div>
    <div class="details" id="details"></div>
    <div class="foot">Updates automatically every 15 seconds · <a href="/admin">parent login</a></div>
  </div>

  <div class="chat" id="chat">
    <h2><span>💬 Messages</span><span class="asname" id="asname"></span></h2>
    <div class="msgs" id="msgs"><div class="empty">No messages yet.</div></div>
    <div class="composer">
      <input id="cinput" placeholder="Type a message…" maxlength="500" autocomplete="off">
      <button id="csend">Send</button>
    </div>
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

// --- chat ---
var chatMeta = { is_parent:false, kid_name:"", parent_name:"Parent", asked:false };
var SEEN_KEY = "kidmon_seen_chat_id";
var NAME_COOKIE = "kidmon_parent_name";
function getCookie(n){ var m=document.cookie.match("(^|;)\\s*"+n+"\\s*=\\s*([^;]+)"); return m?decodeURIComponent(m.pop()):null; }
function setCookie(n,v){ document.cookie=n+"="+encodeURIComponent(v)+";path=/;max-age=31536000;samesite=lax"; }
function esc(s){ return (s||"").replace(/[&<>"']/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]; }); }
function mine(sender){ return chatMeta.is_parent ? sender==="parent" : sender==="kid"; }

async function refreshChat(){
  var data;
  try { data = await (await fetch("/api/chat",{cache:"no-store"})).json(); } catch(e){ return; }
  var panel = document.getElementById("chat");
  if(!data.enabled){ panel.style.display="none"; return; }
  panel.style.display="flex";
  chatMeta.is_parent = data.is_parent;
  chatMeta.kid_name = data.kid_name;
  chatMeta.parent_name = getCookie(NAME_COOKIE) || data.parent_name || "Parent";

  var asn = document.getElementById("asname");
  if(data.is_parent){ asn.style.display="inline"; asn.textContent = "you: " + chatMeta.parent_name + " ✎"; }
  else { asn.style.display="none"; }

  var box = document.getElementById("msgs");
  var atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  if(data.messages.length){
    box.innerHTML = data.messages.map(function(m){
      return "<div class='msg "+(mine(m.sender)?"me":"them")+"'>"
           + "<span class='who'>"+esc(m.name||m.sender)+"</span>"+esc(m.body)+"</div>";
    }).join("");
  } else {
    box.innerHTML = "<div class='empty'>No messages yet.</div>";
  }
  if(atBottom) box.scrollTop = box.scrollHeight;

  handleUnread(data.messages);
  if(data.is_parent && !chatMeta.asked && "Notification" in window && Notification.permission==="default"){
    chatMeta.asked = true; Notification.requestPermission();
  }
}

function handleUnread(msgs){
  var lastSeen = parseInt(localStorage.getItem(SEEN_KEY) || "0", 10);
  var maxId = msgs.length ? Math.max.apply(null, msgs.map(function(m){return m.id;})) : 0;
  var fresh = msgs.filter(function(m){ return !mine(m.sender) && m.id > lastSeen; });
  if(chatMeta.is_parent && fresh.length && "Notification" in window && Notification.permission==="granted" && document.hidden){
    var last = fresh[fresh.length-1];
    new Notification(last.name || "New message", { body: last.body });
  }
  document.title = fresh.length ? "(" + fresh.length + ") My Computer Time" : "My Computer Time";
  if(!document.hidden){ localStorage.setItem(SEEN_KEY, String(maxId)); document.title = "My Computer Time"; }
}

async function sendChat(){
  var inp = document.getElementById("cinput");
  var body = inp.value.trim();
  if(!body) return;
  inp.value = "";
  try { await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({body:body})}); } catch(e){}
  refreshChat();
}
document.getElementById("csend").addEventListener("click", sendChat);
document.getElementById("cinput").addEventListener("keydown", function(e){ if(e.key==="Enter") sendChat(); });
document.getElementById("asname").addEventListener("click", function(){
  if(!chatMeta.is_parent) return;
  var name = prompt("Your name (shown to your kid):", chatMeta.parent_name);
  if(name && name.trim()){ setCookie(NAME_COOKIE, name.trim()); chatMeta.parent_name = name.trim(); refreshChat(); }
});
document.addEventListener("visibilitychange", function(){ if(!document.hidden) refreshChat(); });
refreshChat();
setInterval(refreshChat, 5000);
</script>
</body>
</html>"""


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Parent login</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         font-family: system-ui, sans-serif; background:#0f172a; color:#f8fafc; }
  form { background:#1e293b; padding:2rem; border-radius:16px; width:320px; max-width:90vw; }
  h1 { font-size:1.2rem; margin:0 0 1.25rem; }
  input { width:100%; padding:.7rem; margin:.4rem 0; border:1px solid #334155; border-radius:8px;
          background:#0f172a; color:#f8fafc; box-sizing:border-box; }
  button { width:100%; padding:.8rem; margin-top:.75rem; border:none; border-radius:8px;
           background:#2563eb; color:#fff; font-size:1rem; cursor:pointer; }
  .err { color:#f87171; font-size:.9rem; margin-top:.5rem; }
  .note { color:#94a3b8; font-size:.85rem; margin-top:1rem; }
</style>
</head>
<body>
  <form method="post">
    <h1>🔒 Parent login</h1>
    <input name="username" placeholder="Username" autofocus autocomplete="username">
    <input name="password" type="password" placeholder="Password" autocomplete="current-password">
    <button type="submit">Log in</button>
    {% if error %}<div class="err">{{ error }}</div>{% endif %}
    {% if not configured %}<div class="note">No admin password is configured yet.
      Set one with <code>scripts/set_password.py</code>.</div>{% endif %}
  </form>
</body>
</html>"""


ADMIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin · {{ s.user }}</title>
<style>
  body { font-family: system-ui, sans-serif; margin:0; padding:20px; background:#f1f5f9; color:#0f172a; }
  .wrap { max-width:560px; margin:0 auto; }
  h1 { text-align:center; font-size:1.4rem; }
  .top { text-align:center; color:#64748b; margin-bottom:1rem; }
  .top a { color:#2563eb; }
  .group { background:#fff; border-radius:14px; padding:18px; margin:14px 0; box-shadow:0 1px 4px rgba(0,0,0,.08); }
  .group h2 { font-size:1.05rem; margin:0 0 12px; }
  button { padding:12px; border:none; border-radius:8px; font-size:1rem; cursor:pointer; color:#fff; }
  .row { display:flex; gap:8px; flex-wrap:wrap; }
  .row button { flex:1; }
  .lock { background:#f59e0b; } .danger { background:#ef4444; } .ok { background:#2563eb; }
  .pill { background:#e2e8f0; color:#0f172a; border-radius:18px; padding:8px 14px; }
  input { padding:10px; border:1px solid #cbd5e1; border-radius:8px; font-size:1rem; width:100%; box-sizing:border-box; margin:6px 0; }
  .muted { color:#64748b; }
  table { width:100%; border-collapse:collapse; font-size:.9rem; }
  td, th { text-align:left; padding:4px 6px; border-bottom:1px solid #e2e8f0; }
  .barrow { display:flex; align-items:center; gap:8px; font-size:.85rem; padding:3px 0; }
  .barrow .d { width:52px; flex:none; color:#64748b; }
  .barrow .v { width:54px; flex:none; text-align:right; }
  .track { flex:1; height:14px; background:#e2e8f0; border-radius:4px; position:relative; overflow:hidden; }
  .bar { height:100%; border-radius:4px; min-width:2px; }
  .lim { position:absolute; top:-1px; bottom:-1px; width:2px; background:#ef4444; }
  #msg { text-align:center; padding:10px; border-radius:8px; display:none; margin:10px 0; }
  #msg.s { background:#dcfce7; color:#166534; } #msg.e { background:#fee2e2; color:#991b1b; }
</style>
</head>
<body>
<div class="wrap">
  <h1>💻 {{ s.user }}'s computer</h1>
  <div class="top">
    {% if s.is_locked %}🔒 Currently LOCKED{% else %}● Online{% endif %}
    · <a href="/">💬 messages</a> · <a href="/logout">log out</a>
  </div>
  <div id="msg"></div>

  <div class="group">
    <h2>📊 Status</h2>
    <p>⏱️ <b>Daily limit:</b> <span id="st-limit"></span></p>
    <p>⏳ <b>Time remaining:</b> <span id="st-rem"></span></p>
    <p>🕐 <b>Scheduled locks:</b> <span id="st-locks"></span></p>
  </div>

  <div class="group">
    <h2>🔒 Quick actions</h2>
    <div class="row">
      <button class="lock" onclick="post('/api/admin/lock')">Lock now</button>
    </div>
  </div>

  <div class="group">
    <h2>⏱️ Time limit (today)</h2>
    <div class="row">
      <button class="pill" onclick="setLimit(30)">30m</button>
      <button class="pill" onclick="setLimit(60)">1h</button>
      <button class="pill" onclick="setLimit(120)">2h</button>
      <button class="pill" onclick="setLimit(180)">3h</button>
    </div>
    <input id="limit" type="number" placeholder="Minutes…">
    <div class="row">
      <button class="ok" onclick="setLimit()">Set limit</button>
      <button class="ok" onclick="extend()">+ Extend</button>
    </div>
    <button class="danger" style="width:100%;margin-top:8px" onclick="clearWhat('usage')">Clear limit</button>
  </div>

  <div class="group">
    <h2>🕐 Bedtime lock</h2>
    <input id="locktime" type="time" value="21:00">
    <button class="ok" style="width:100%" onclick="addLock()">Add scheduled lock</button>
    <button class="danger" style="width:100%;margin-top:8px" onclick="clearWhat('locks')">Clear scheduled locks</button>
  </div>

  <div class="group">
    <h2>💬 Send message</h2>
    <input id="message" placeholder="Type a message to show on the kid's screen…">
    <button class="ok" style="width:100%" onclick="sendMsg()">Send</button>
  </div>

  <div class="group">
    <h2>📈 Usage history <span class="muted" style="font-weight:400;font-size:.8rem">(red mark = limit)</span></h2>
    <div id="history" class="muted">Loading…</div>
  </div>

  <div class="group">
    <h2>🖥️ Today's programs</h2>
    <table id="activity"><tbody class="muted"><tr><td>Loading…</td></tr></tbody></table>
  </div>
</div>
<script>
function flash(text, ok) {
  const m = document.getElementById("msg");
  m.textContent = text; m.className = ok ? "s" : "e"; m.style.display = "block";
  setTimeout(() => m.style.display = "none", 3000);
}
async function post(url, body) {
  const r = await fetch(url, { method:"POST", headers:{"Content-Type":"application/json"},
                               body: JSON.stringify(body || {}) });
  const data = await r.json();
  flash(data.message || (data.ok ? "Done" : "Error"), data.ok);
  refresh();
  return data;
}
function fmt(mins){ if(mins==null) return "—"; if(mins>=60){const h=Math.floor(mins/60),m=mins%60;return h+"h "+String(m).padStart(2,"0")+"m";} return mins+" min"; }
function setLimit(preset){ const v = preset || parseInt(document.getElementById("limit").value); if(!v){flash("Enter minutes",false);return;} post("/api/admin/set_limit",{minutes:v}); }
function extend(){ const v=parseInt(document.getElementById("limit").value); if(!v){flash("Enter minutes",false);return;} post("/api/admin/extend",{minutes:v}); }
function addLock(){ const t=document.getElementById("locktime").value; if(!t){flash("Pick a time",false);return;} post("/api/admin/add_lock_time",{time:t}); }
function clearWhat(what){ if(confirm("Clear "+what+"?")) post("/api/admin/clear",{what:what}); }
function sendMsg(){ const t=document.getElementById("message").value; if(!t){flash("Type a message",false);return;} post("/api/admin/message",{message:t}).then(()=>document.getElementById("message").value=""); }
async function refresh(){
  const s = await (await fetch("/api/status",{cache:"no-store"})).json();
  document.getElementById("st-limit").textContent = s.usage_limit ? fmt(s.usage_limit) : "Not set";
  document.getElementById("st-rem").textContent = s.time_remaining==null ? "—" : fmt(Math.max(0,s.time_remaining));
  document.getElementById("st-locks").textContent = (s.lock_times && s.lock_times.length) ? s.lock_times.join(", ") : "None";
  const hist = await (await fetch("/api/admin/history",{cache:"no-store"})).json();
  const rows = hist.rows.slice().reverse();  // oldest -> newest, reads top-down
  const scale = Math.max(1, ...rows.map(r => Math.max(r.used_seconds/60, r.limit_minutes||0)));
  document.getElementById("history").innerHTML = rows.length
    ? rows.map(r => {
        const used = Math.round(r.used_seconds/60);
        const lim = r.limit_minutes;
        const over = lim != null && used > lim;
        const w = Math.min(100, used/scale*100);
        const limMark = lim != null ? "<span class='lim' style='left:"+(lim/scale*100)+"%'></span>" : "";
        return "<div class='barrow'><span class='d'>"+r.day.slice(5)+"</span>"
             + "<span class='track'><span class='bar' style='width:"+w+"%;background:"+(over?"#ef4444":"#3b82f6")+"'></span>"+limMark+"</span>"
             + "<span class='v'>"+fmt(used)+"</span></div>";
      }).join("")
    : "<span class='muted'>No history yet</span>";
  const act = await (await fetch("/api/admin/activity",{cache:"no-store"})).json();
  document.getElementById("activity").innerHTML = "<tbody>" + (act.rows.length
    ? act.rows.map(r=>"<tr><td>"+(r.process||"?")+"</td><td>"+fmt(Math.round(r.total/60))+"</td></tr>").join("")
    : "<tr><td class='muted'>No activity logged yet</td></tr>") + "</tbody>";
}
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>"""
