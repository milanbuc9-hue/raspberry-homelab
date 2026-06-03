#!/bin/bash
# Secrets zentral aus .env laden (auch im Cron-Kontext)
set -a; [ -f /home/milan/.env ] && . /home/milan/.env; set +a
# ============================================================
# notify-test.sh – Täglicher Selbsttest des Notification-Systems
# Cron: 5 8 * * * /home/milan/scripts/notify-test.sh
# ============================================================

LOG_FILE="/home/milan/logs/notifications.log"
TS=$(date '+%d.%m.%Y %H:%M:%S')
FAILURES=0

log() { echo "[$TS] [low] [self-test] $1" | tee -a "$LOG_FILE"; }

# ── 1. Telegram Bot API Erreichbarkeit ──────────────────────
TG_TOKEN="${TELEGRAM_BOT_TOKEN}"
TG_STATUS=$(curl -s --max-time 8 "https://api.telegram.org/bot${TG_TOKEN}/getMe" \
  | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print('ok' if d.get('ok') else 'error')
except: print('error')
" 2>/dev/null)

if [ "$TG_STATUS" = "ok" ]; then
  log "✅ Telegram Bot: erreichbar"
else
  log "❌ Telegram Bot: $TG_STATUS"
  FAILURES=$((FAILURES+1))
fi

# ── 2. Test-Nachricht senden ─────────────────────────────────
/home/milan/scripts/notify.sh \
  "🔧 *Täglicher Selbsttest*
System: milan (Pi 5)
Zeit: $(date '+%d.%m.%Y %H:%M')
Telegram Bot: ${TG_STATUS}
Status: ✅ OK" \
  "self-test" "low"

if [ $? -eq 0 ]; then
  log "✅ Test-Nachricht erfolgreich gesendet"
else
  log "❌ Test-Nachricht fehlgeschlagen"
  FAILURES=$((FAILURES+1))
fi

# ── 3. n8n Status ────────────────────────────────────────────
N8N_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://milan:5678/healthz)
if [ "$N8N_STATUS" = "200" ]; then
  log "✅ n8n: running"
else
  log "⚠️  n8n: HTTP $N8N_STATUS"
fi

# ── 4. Home Assistant Status ─────────────────────────────────
HA_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://milan:8123/manifest.json)
if [ "$HA_STATUS" = "200" ]; then
  log "✅ Home Assistant: running"
else
  log "⚠️  Home Assistant: HTTP $HA_STATUS"
fi

log "Selbsttest abgeschlossen. Fehler: $FAILURES"

# ── Heartbeat schreiben (für Watchdog in notify-flush.sh) ────
date +%s > /home/milan/logs/notify_heartbeat

exit $FAILURES
