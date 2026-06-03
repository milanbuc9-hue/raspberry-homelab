#!/bin/bash
# Secrets zentral aus .env laden (auch im Cron-Kontext)
set -a; [ -f /home/milan/.env ] && . /home/milan/.env; set +a
# ============================================================
# notify-dashboard-gen.sh – HTML Status-Dashboard generieren
# Cron: */5 * * * * /home/milan/scripts/notify-dashboard-gen.sh
# Output: /home/milan/docker_data/homeassistant/www/notify-status.html
# URL: http://milan:8123/local/notify-status.html
# ============================================================

OUT="/home/milan/docker_data/homeassistant/www/notify-status.html"
LOG_FILE="/home/milan/logs/notifications.log"
DEDUP_DIR="/home/milan/logs/notify_dedup"
BUNDLE_DIR="/home/milan/logs/notify_bundles"
HEARTBEAT_FILE="/home/milan/logs/notify_heartbeat"
FLUSH_HB_FILE="/home/milan/logs/notify_flush_heartbeat"
NOW=$(date +%s)
TS=$(date '+%d.%m.%Y %H:%M:%S')

# ── Telegram Bot Status ───────────────────────────────────────
TG_TOKEN="${TELEGRAM_BOT_TOKEN}"
TG_STATUS=$(curl -s --max-time 5 "https://api.telegram.org/bot${TG_TOKEN}/getMe" \
  | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print('ok' if d.get('ok') else 'error')
except: print('error')
" 2>/dev/null)
TG_OK=0; [ "$TG_STATUS" = "ok" ] && TG_OK=1

# ── Heartbeat-Alter ───────────────────────────────────────────
if [ -f "$HEARTBEAT_FILE" ]; then
  LAST_HB=$(cat "$HEARTBEAT_FILE" 2>/dev/null || echo 0)
  HB_AGE=$(( NOW - LAST_HB ))
  HB_HOURS=$((HB_AGE / 3600))
  HB_MIN=$(( (HB_AGE % 3600) / 60 ))
  HB_LABEL="${HB_HOURS}h ${HB_MIN}min"
  HB_OK=1; [ $HB_AGE -gt 90000 ] && HB_OK=0
else
  HB_LABEL="kein File"
  HB_OK=0
fi

if [ -f "$FLUSH_HB_FILE" ]; then
  LAST_FLUSH=$(cat "$FLUSH_HB_FILE" 2>/dev/null || echo 0)
  FLUSH_AGE=$(( NOW - LAST_FLUSH ))
  FLUSH_MIN=$((FLUSH_AGE / 60))
  FLUSH_LABEL="${FLUSH_MIN}min"
  FLUSH_OK=1; [ $FLUSH_AGE -gt 600 ] && FLUSH_OK=0
else
  FLUSH_LABEL="kein File"
  FLUSH_OK=0
fi

# ── Statistiken ───────────────────────────────────────────────
SENDS_24H=$(grep -c "Telegram OK\|ntfy Fallback OK" "$LOG_FILE" 2>/dev/null; true)
FAILS_24H=$(grep -c "ALLE Kanäle" "$LOG_FILE" 2>/dev/null; true)
DEDUP_24H=$(grep -c "DEDUP" "$LOG_FILE" 2>/dev/null; true)
SENDS_24H="${SENDS_24H:-0}"
FAILS_24H="${FAILS_24H:-0}"
DEDUP_24H="${DEDUP_24H:-0}"

# ── Aktive Locks (als JSON-Zeilen) ────────────────────────────
ACTIVE_LOCKS=0
LOCK_JSON="["
SEP=""
for f in "$DEDUP_DIR"/*; do
  [ -f "$f" ] || continue
  LAST=$(cat "$f" 2>/dev/null || echo 0)
  AGE=$((NOW - LAST))
  if [ $AGE -lt 7200 ]; then
    ACTIVE_LOCKS=$((ACTIVE_LOCKS+1))
    if [ $AGE -lt 1800 ]; then REM=$((1800-AGE)); PRIO="normal"
    else REM=$((7200-AGE)); PRIO="low"; fi
    HASH=$(basename "$f" | cut -c1-12)
    LOCK_JSON="${LOCK_JSON}${SEP}{\"hash\":\"${HASH}\",\"prio\":\"${PRIO}\",\"rem\":${REM}}"
    SEP=","
  fi
done
LOCK_JSON="${LOCK_JSON}]"

# ── Pending Bundles (als JSON-Zeilen) ─────────────────────────
PENDING_BUNDLES=0
BUNDLE_JSON="["
SEP=""
for b in "$BUNDLE_DIR"/*.bundle; do
  [ -f "$b" ] || continue
  CNT=$(wc -l < "$b")
  NAME=$(basename "$b" .bundle)
  PENDING_BUNDLES=$((PENDING_BUNDLES+1))
  BUNDLE_JSON="${BUNDLE_JSON}${SEP}{\"name\":\"${NAME}\",\"count\":${CNT}}"
  SEP=","
done
BUNDLE_JSON="${BUNDLE_JSON}]"

# ── Letzte Log-Zeilen ─────────────────────────────────────────
LAST_LINES=$(tail -10 "$LOG_FILE" 2>/dev/null || echo "(Log leer)")

# ── Python generiert das HTML ─────────────────────────────────
export D_TS="$TS"
export D_TG_OK="$TG_OK"
export D_TG_STATUS="$TG_STATUS"
export D_HB_OK="$HB_OK"
export D_HB_LABEL="$HB_LABEL"
export D_FL_OK="$FLUSH_OK"
export D_FL_LABEL="$FLUSH_LABEL"
export D_SENDS="$SENDS_24H"
export D_FAILS="$FAILS_24H"
export D_DEDUP="$DEDUP_24H"
export D_ACT_LOCKS="$ACTIVE_LOCKS"
export D_LOCK_JSON="$LOCK_JSON"
export D_PEND_BUND="$PENDING_BUNDLES"
export D_BUNDLE_JSON="$BUNDLE_JSON"
export D_LAST_LINES="$LAST_LINES"

python3 << 'PYEOF'
import os, json, sys

ts           = os.environ.get("D_TS")
tg_ok        = os.environ.get("D_TG_OK") == "1"
tg_status    = os.environ.get("D_TG_STATUS", "?")
hb_ok        = os.environ.get("D_HB_OK") == "1"
hb_label     = os.environ.get("D_HB_LABEL", "?")
fl_ok        = os.environ.get("D_FL_OK") == "1"
fl_label     = os.environ.get("D_FL_LABEL", "?")
sends        = os.environ.get("D_SENDS", "0")
fails        = os.environ.get("D_FAILS", "0")
dedup        = os.environ.get("D_DEDUP", "0")
act_locks    = os.environ.get("D_ACT_LOCKS", "0")
lock_json    = json.loads(os.environ.get("D_LOCK_JSON", "[]"))
pend_bund    = os.environ.get("D_PEND_BUND", "0")
bundle_json  = json.loads(os.environ.get("D_BUNDLE_JSON", "[]"))
last_lines   = os.environ.get("D_LAST_LINES", "(Log leer)")

def badge(ok, label, ok_text=None):
    cls = "ok" if ok else "fail"
    icon = "✅" if ok else "❌"
    return f'<span class="badge {cls}">{icon} {label}</span>'

def stat_row(label, val, color=""):
    return f'<div class="stat-row"><span>{label}</span><span class="stat-val {color}">{val}</span></div>'

tg_badge = badge(tg_ok, tg_status)
hb_badge = badge(hb_ok, f"vor {hb_label}")
fl_badge = badge(fl_ok, f"vor {fl_label}")

fails_color = "red" if int(fails.strip()) > 0 else "green"

lock_rows = ""
for l in lock_json:
    lock_rows += f"<tr><td>{l['hash']}…</td><td>{l['prio']}</td><td>noch {l['rem']}s</td></tr>"
if not lock_rows:
    lock_rows = "<tr><td colspan='3' style='color:#8b949e'>keine aktiven Throttles</td></tr>"

bundle_rows = ""
for b in bundle_json:
    bundle_rows += f"<tr><td>{b['name']}</td><td>{b['count']} Meldung(en)</td></tr>"
if not bundle_rows:
    bundle_rows = "<tr><td colspan='2' style='color:#8b949e'>keine pending Bundles</td></tr>"

import html as htmlmod
log_escaped = htmlmod.escape(last_lines)

print(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="60">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Notification System Status</title>
<style>
  :root {{
    --bg:#0d1117;--card:#161b22;--border:#30363d;
    --text:#c9d1d9;--dim:#8b949e;--green:#3fb950;
    --red:#f85149;--yellow:#d29922;--blue:#58a6ff;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;padding:20px}}
  h1{{font-size:1.4rem;color:var(--blue);margin-bottom:4px}}
  .ts{{color:var(--dim);font-size:.8rem;margin-bottom:20px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
  .card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px}}
  .card h2{{font-size:.85rem;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px}}
  .badge{{display:inline-block;padding:3px 8px;border-radius:4px;font-size:.8rem;font-weight:600}}
  .badge.ok{{background:#1a3a25;color:var(--green)}}
  .badge.fail{{background:#3a1a1a;color:var(--red)}}
  .stat-row{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)}}
  .stat-row:last-child{{border-bottom:none}}
  .stat-val{{font-weight:600}}
  .stat-val.green{{color:var(--green)}}
  .stat-val.red{{color:var(--red)}}
  table{{width:100%;border-collapse:collapse;font-size:.82rem}}
  td{{padding:5px 4px;border-bottom:1px solid var(--border)}}
  tr:last-child td{{border-bottom:none}}
  pre{{background:#0a0d12;border-radius:4px;padding:10px;font-size:.75rem;overflow-x:auto;line-height:1.6;color:#a8b8c8;white-space:pre-wrap;word-break:break-all}}
  .refresh{{color:var(--dim);font-size:.75rem;float:right}}
</style>
</head>
<body>
<h1>📡 Notification System</h1>
<p class="ts">Stand: {ts} &nbsp;&middot;&nbsp; <span class="refresh">Auto-Refresh 60s</span></p>
<div class="grid">
  <div class="card">
    <h2>Kanäle</h2>
    <div class="stat-row"><span>Telegram Bot</span>{tg_badge}</div>
    <div class="stat-row"><span>ntfy Fallback</span><span class="badge ok">✅ konfiguriert</span></div>
  </div>
  <div class="card">
    <h2>Watchdog / Cron</h2>
    <div class="stat-row"><span>Self-Test (letzter HB)</span>{hb_badge}</div>
    <div class="stat-row"><span>Flush-Cron (letzter HB)</span>{fl_badge}</div>
  </div>
  <div class="card">
    <h2>Letzte 24h</h2>
    {stat_row("Gesendet", sends+"x", "green")}
    {stat_row("Fehlgeschlagen", fails+"x", fails_color)}
    {stat_row("Unterdrückt (Dedup)", dedup+"x")}
  </div>
  <div class="card">
    <h2>Aktive Throttles ({act_locks})</h2>
    <table>
      <tr style="color:var(--dim)"><th align="left">Hash</th><th align="left">Prio</th><th align="left">Cooldown</th></tr>
      {lock_rows}
    </table>
  </div>
  <div class="card">
    <h2>Pending Bundles ({pend_bund})</h2>
    <table>
      <tr style="color:var(--dim)"><th align="left">Quelle</th><th align="left">Anzahl</th></tr>
      {bundle_rows}
    </table>
  </div>
  <div class="card" style="grid-column:1/-1">
    <h2>Letzte 10 Log-Einträge</h2>
    <pre>{log_escaped if log_escaped.strip() else "(Log leer)"}</pre>
  </div>
</div>
</body>
</html>""")
PYEOF
