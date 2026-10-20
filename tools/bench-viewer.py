#!/usr/bin/env python3
"""Живой экран стенда PN532 в браузере.

Читает лог `esphome logs` отладочной прошивки (logger VERBOSE — нужны строки
опросов PN532) и шлёт события на страницу по SSE.

    python3 tools/bench-viewer.py <путь-к-логу> [порт]

Лог пишется так:
    esphome logs nfc-debug.yaml --device ... | tee -a bench.log
"""
import http.server
import json
import os
import queue
import re
import sys
import threading
import time
from collections import deque

LOG = sys.argv[1]
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
FIGURKI_H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "esphome", "figurki.h")

TS = re.compile(r"^\[(\d\d:\d\d:\d\d\.\d+)\]")
POLL_HIT = re.compile(r"Response data: 01:01:([0-9A-F:]+)")
PLACED = re.compile(r"ПОСТАВИЛИ: (\S+)")
REMOVED = re.compile(r"СНЯЛИ: (\S+)")


def load_figurines():
    try:
        text = open(FIGURKI_H, encoding="utf-8").read()
    except OSError:
        return {}
    return {uid: int(n) for uid, n in re.findall(r'\{"([0-9A-F-]+)", "figurka-(\d+)"\}', text)}


def uid_from_poll(hexbytes):
    # InListPassiveTarget: Tg, ATQA(2), SAK, длина UID, UID…
    b = hexbytes.split(":")
    try:
        n = int(b[4], 16)
        return "-".join(b[5:5 + n])
    except (IndexError, ValueError):
        return ""


def classify(line):
    ts = TS.match(line)
    t = ts.group(1) if ts else time.strftime("%H:%M:%S")
    m = POLL_HIT.search(line)
    if m:
        return {"type": "hit", "t": t, "uid": uid_from_poll(m.group(1))}
    if "Timed out waiting for readiness" in line:
        return {"type": "miss", "t": t}
    m = PLACED.search(line)
    if m:
        return {"type": "placed", "t": t, "uid": m.group(1)}
    m = REMOVED.search(line)
    if m:
        return {"type": "removed", "t": t, "uid": m.group(1)}
    if "пропуск опроса" in line:
        return {"type": "skip", "t": t}
    if "Requesting tag read failed" in line:
        return {"type": "link", "t": t}
    return None


clients = []
history = deque(maxlen=400)
lock = threading.Lock()


def broadcast(ev):
    data = json.dumps(ev, ensure_ascii=False)
    with lock:
        history.append(data)
        for q in clients:
            q.put(data)


def tail():
    while not os.path.exists(LOG):
        time.sleep(0.5)
    with open(LOG, encoding="utf-8", errors="replace") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.05)
                continue
            ev = classify(line)
            if ev:
                broadcast(ev)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = queue.Queue()
            with lock:
                backlog = list(history)
                clients.append(q)
            try:
                self.wfile.write(f"event: config\ndata: {json.dumps(load_figurines())}\n\n".encode())
                for data in backlog:
                    self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                while True:
                    try:
                        data = q.get(timeout=15)
                        self.wfile.write(f"data: {data}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with lock:
                    clients.remove(q)
            return
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Стенд PN532</title>
<style>
:root{--bg:#0e1013;--panel:#171a1f;--line:#262a31;--text:#e8eaed;--dim:#7d8590;
--ok:#3fb950;--ok-bg:#12261a;--warn:#e3b341;--warn-bg:#2b2410;--bad:#f85149;--bad-bg:#2d1416;--miss:#2a2f37}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px;display:grid;gap:16px;grid-template-columns:1fr 340px}
@media(max-width:860px){main{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
#status{grid-column:1/-1;display:flex;align-items:center;gap:28px;min-height:190px;transition:background .25s,border-color .25s}
#status.empty{background:var(--panel)}
#status.holding{background:var(--ok-bg);border-color:var(--ok)}
#status.losing{background:var(--warn-bg);border-color:var(--warn)}
#status.removed{background:var(--bad-bg);border-color:var(--bad)}
#big{font-size:64px;font-weight:700;letter-spacing:-1px;min-width:260px}
#status.holding #big{color:var(--ok)}#status.losing #big{color:var(--warn)}#status.removed #big{color:var(--bad)}#status.empty #big{color:var(--dim)}
#sub{font-size:20px}#sub .dim{color:var(--dim);font-size:15px}
#timer{font-size:44px;font-variant-numeric:tabular-nums;font-weight:600;margin-left:auto;text-align:right}
#timer small{display:block;font-size:13px;color:var(--dim);font-weight:400}
h2{margin:0 0 12px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);font-weight:600}
#strip{display:flex;gap:3px;height:56px;align-items:stretch}
#strip i{flex:1;border-radius:3px;background:var(--miss)}
#strip i.h{background:var(--ok)}
.legend{display:flex;justify-content:space-between;color:var(--dim);font-size:12px;margin-top:8px}
#signal{font-size:28px;font-weight:600;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--dim);font-weight:500;font-size:12px}
tr.now td{color:var(--ok);font-weight:600}
.good{color:var(--ok)}.badc{color:var(--bad)}.dim{color:var(--dim)}
#log{list-style:none;margin:0;padding:0;max-height:420px;overflow:auto;font-size:14px}
#log li{padding:5px 0;border-bottom:1px solid var(--line);display:flex;gap:10px}
#log time{color:var(--dim);font-variant-numeric:tabular-nums}
#conn{position:fixed;right:12px;bottom:10px;font-size:12px;color:var(--dim)}
</style></head><body>
<main>
  <section id="status" class="panel empty">
    <div id="big">Пусто</div>
    <div id="sub"><span class="dim">Положи метку на ридер</span></div>
    <div id="timer"></div>
  </section>
  <section class="panel">
    <h2>Опросы ридера — последние 60 (каждые 0.5 с)</h2>
    <div id="strip"></div>
    <div class="legend"><span>30 с назад</span><span>Сила сигнала за 5 с: <b id="signal">—</b></span><span>сейчас</span></div>
  </section>
  <section class="panel" style="grid-row:span 2">
    <h2>События</h2>
    <ul id="log"></ul>
  </section>
  <section class="panel">
    <h2>Диски — лучшее удержание</h2>
    <table><thead><tr><th>№</th><th>UID</th><th>Рекорд</th><th>Промахи</th><th>Последний раз</th></tr></thead><tbody id="tags"></tbody></table>
  </section>
</main>
<div id="conn">подключение…</div>
<script>
const N = 60, DEBOUNCE = 1.5;
let fig = {}, polls = [], present = null, placedAt = 0, removedFlash = 0, stats = {}, lastHitUid = "";
const $ = id => document.getElementById(id);
const name = uid => fig[uid] ? "Статуэтка " + fig[uid] : (uid ? "Неизвестная метка" : "");
const secs = t => { const [h,m,s] = t.split(":"); return +h*3600 + +m*60 + parseFloat(s); };
function stat(uid){ return stats[uid] ||= {best:0, misses:0, holds:0, last:"", cur:null}; }

function logLine(t, text, cls){
  const li = document.createElement("li");
  li.innerHTML = `<time>${t.slice(0,8)}</time><span class="${cls||""}">${text}</span>`;
  $("log").prepend(li);
  while ($("log").children.length > 60) $("log").lastChild.remove();
}

function onEvent(ev){
  if (ev.type === "hit" || ev.type === "miss"){
    polls.push(ev.type === "hit"); if (polls.length > N) polls.shift();
    if (ev.type === "hit") lastHitUid = ev.uid;
    if (present){ const s = stat(present.uid); if (ev.type === "miss") s.cur.misses++; else s.cur.hits++; }
  } else if (ev.type === "placed"){
    present = {uid: ev.uid, t: secs(ev.t)}; placedAt = Date.now();
    const s = stat(ev.uid); s.cur = {hits:0, misses:0, start: secs(ev.t)};
    logLine(ev.t, `<b>Поставили</b> — ${name(ev.uid)} <span class="dim">${ev.uid}</span>`, "good");
  } else if (ev.type === "removed"){
    const s = stat(ev.uid);
    if (s.cur){
      const held = Math.max(0, secs(ev.t) - s.cur.start - DEBOUNCE);
      if (held > s.best){ s.best = held; s.misses = s.cur.misses; }
      s.holds++; s.last = `${held.toFixed(1)} с`; s.cur = null;
      logLine(ev.t, `<b>Сняли</b> — ${name(ev.uid)}, держалась ${held.toFixed(1)} с`, held >= 10 ? "good" : "badc");
    }
    present = null; removedFlash = Date.now();
  } else if (ev.type === "skip"){
    logLine(ev.t, "Пропуск опроса — метка на месте, защита сработала", "dim");
  } else if (ev.type === "link"){
    logLine(ev.t, "Ридер не ответил на команду (контакт?)", "badc");
  }
}

function render(){
  const st = $("status"), last5 = polls.slice(-10), hits = last5.filter(Boolean).length;
  $("signal").textContent = last5.length ? Math.round(hits / last5.length * 100) + "%" : "—";
  if (present){
    const losing = polls.length && !polls[polls.length-1];
    st.className = "panel " + (losing ? "losing" : "holding");
    $("big").textContent = losing ? "Теряет…" : "Держится";
    $("sub").innerHTML = `${name(present.uid)}<br><span class="dim">${present.uid}</span>`;
    $("timer").innerHTML = `${((Date.now()-placedAt)/1000).toFixed(0)} с<small>на ридере</small>`;
  } else if (Date.now() - removedFlash < 1500){
    st.className = "panel removed"; $("big").textContent = "Сняли"; $("timer").innerHTML = "";
  } else {
    st.className = "panel empty"; $("big").textContent = "Пусто";
    $("sub").innerHTML = '<span class="dim">Положи метку на ридер</span>'; $("timer").innerHTML = "";
  }
  $("strip").innerHTML = Array.from({length: N}, (_, i) => {
    const p = polls[i - (N - polls.length)]; return `<i class="${p ? "h" : ""}"></i>`; }).join("");
  const uids = Object.keys(fig).sort((a,b) => fig[a]-fig[b]);
  for (const u of Object.keys(stats)) if (!uids.includes(u)) uids.push(u);
  $("tags").innerHTML = uids.map(u => {
    const s = stats[u] || {best:0, misses:0, holds:0, last:""};
    const now = present && present.uid === u;
    const best = s.holds ? `<span class="${s.best >= 10 ? "good" : "badc"}">${s.best.toFixed(1)} с</span>` : '<span class="dim">—</span>';
    return `<tr class="${now ? "now" : ""}"><td>${fig[u] || "?"}</td><td class="dim">${u.slice(-8)}</td><td>${best}</td><td>${s.holds ? s.misses : ""}</td><td class="dim">${s.last}</td></tr>`;
  }).join("");
}

const es = new EventSource("/events");
es.addEventListener("config", e => { fig = JSON.parse(e.data); render(); });
es.onmessage = e => { onEvent(JSON.parse(e.data)); };
es.onopen = () => $("conn").textContent = "лог подключён";
es.onerror = () => $("conn").textContent = "нет связи с сервером стенда";
setInterval(render, 200);
</script></body></html>
"""

if __name__ == "__main__":
    threading.Thread(target=tail, daemon=True).start()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Стенд: http://localhost:{PORT}", flush=True)
    server.serve_forever()
