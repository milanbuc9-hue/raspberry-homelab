#!/bin/bash
# Secrets zentral aus .env laden (auch im Cron-Kontext)
set -a; [ -f /home/milan/.env ] && . /home/milan/.env; set +a
# ============================================================
# notify.sh – Zentrales Benachrichtigungs-Script
#
# Usage: notify.sh "<message>" [source] [priority] [number]
#
# Prioritäten:
#   critical  – immer sofort, kein Cooldown, kein Bundling, ntfy: urgent
#   normal    – Cooldown 30 Min, Bundling aktiv
#   low       – Cooldown 2 Std, Bundling aktiv
#
# Features:
#   - Telegram mit 1 Retry (3s Delay) + Timeout-Härtung
#   - Dedup via Lock-Files (DEDUP_DIR), Cleanup per Cron
#   - Bundling: gedrosselte Msgs landen im Bundle, Flush per Cron
#   - ntfy Fallback bei WhatsApp-Ausfall
# Log: /home/milan/logs/notifications.log
# ============================================================

MESSAGE="$1"
SOURCE="${2:-unknown}"
PRIORITY="${3:-normal}"    # critical | normal | low
OVERRIDE_NUMBER="$4"

# ── Konfiguration ────────────────────────────────────────────
TG_TOKEN="${TELEGRAM_BOT_TOKEN}"
TG_CHAT_ID="${TELEGRAM_CHAT_ID}"
TG_API="https://api.telegram.org/bot${TG_TOKEN}/sendMessage"
NTFY_TOPIC="milan-homelab-b16b1e8d"
NTFY_URL="https://ntfy.sh/${NTFY_TOPIC}"
LOG_FILE="/home/milan/logs/notifications.log"
DEDUP_DIR="/home/milan/logs/notify_dedup"
BUNDLE_DIR="/home/milan/logs/notify_bundles"
TG_RETRY_DELAY=3      # Sekunden zwischen Retry-Versuchen
TG_TIMEOUT=10         # Sekunden pro Versuch
# ─────────────────────────────────────────────────────────────

if [ -z "$MESSAGE" ]; then
  echo "Usage: notify.sh \"<message>\" [source] [priority] [number]" >&2
  exit 1
fi

mkdir -p "$DEDUP_DIR" "$BUNDLE_DIR"
TS=$(date '+%d.%m.%Y %H:%M:%S')

log() {
  echo "[$TS] [${PRIORITY}] [${SOURCE}] $1" | tee -a "$LOG_FILE"
}

# ── Priorität validieren + ntfy-Mapping ──────────────────────
case "$PRIORITY" in
  critical) COOLDOWN=0;    NTFY_PRIO="urgent";  NTFY_TAGS="rotating_light,warning" ;;
  normal)   COOLDOWN=1800; NTFY_PRIO="default"; NTFY_TAGS="bell"                   ;;
  low)      COOLDOWN=7200; NTFY_PRIO="low";     NTFY_TAGS="information_source"     ;;
  *)
    log "⚠️  Unbekannte Priorität '$PRIORITY', verwende normal"
    PRIORITY="normal"; COOLDOWN=1800; NTFY_PRIO="default"; NTFY_TAGS="bell"
    ;;
esac

# ── Spam-Schutz (Dedup) + Bundling ───────────────────────────
MSG_HASH=$(echo "${SOURCE}:${MESSAGE}" | sha256sum | cut -c1-16)
LOCK_FILE="${DEDUP_DIR}/${MSG_HASH}"
BUNDLE_FILE="${BUNDLE_DIR}/${SOURCE}_${PRIORITY}.bundle"

if [ "$COOLDOWN" -gt 0 ] && [ -f "$LOCK_FILE" ]; then
  LAST_SENT=$(cat "$LOCK_FILE" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  AGE=$((NOW - LAST_SENT))
  REMAINING=$((COOLDOWN - AGE))
  if [ $AGE -lt $COOLDOWN ]; then
    # Nachricht bundeln statt still verwerfen
    echo "[$TS] $MESSAGE" >> "$BUNDLE_FILE"
    log "🔕 DEDUP (${REMAINING}s) → gebündelt ($(wc -l < "$BUNDLE_FILE") im Bundle)"
    exit 0
  fi
fi

# Lock setzen vor dem Senden
[ "$COOLDOWN" -gt 0 ] && date +%s > "$LOCK_FILE"

# ── Telegram-Send-Funktion mit Retry ─────────────────────────
_tg_send() {
  curl -s -o /tmp/notify_tg_resp.json -w "%{http_code}" \
    --max-time "$TG_TIMEOUT" \
    --connect-timeout 5 \
    -X POST "$TG_API" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"$TG_CHAT_ID\",\"text\":$(echo "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'),\"parse_mode\":\"Markdown\"}"
}

# ── 1. Telegram (mit 1 Retry) ────────────────────────────────
TG_RESPONSE=$(_tg_send "$MESSAGE")

if [ "$TG_RESPONSE" != "200" ] && [ "$TG_RESPONSE" != "201" ]; then
  log "⚠️  Telegram Versuch 1 fehlgeschlagen (HTTP $TG_RESPONSE) → Retry in ${TG_RETRY_DELAY}s"
  sleep "$TG_RETRY_DELAY"
  TG_RESPONSE=$(_tg_send "$MESSAGE")
fi

if [ "$TG_RESPONSE" = "200" ] || [ "$TG_RESPONSE" = "201" ]; then
  log "✅ Telegram OK → Chat $TG_CHAT_ID"
  # Erfolgreich → ggf. Bundle leeren (wurde gerade als "Zusammenfassung" gesendet)
  rm -f "$BUNDLE_FILE"
  exit 0
fi

# Beide Versuche fehlgeschlagen → Lock zurücksetzen für spätere Retry-Möglichkeit
[ "$COOLDOWN" -gt 0 ] && rm -f "$LOCK_FILE"

TG_ERR=$(cat /tmp/notify_tg_resp.json 2>/dev/null \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('description','?'))" 2>/dev/null \
  || echo "HTTP $TG_RESPONSE")
log "⚠️  Telegram FAILED nach Retry (${TG_ERR}) → Fallback ntfy"

# ── 2. Fallback: ntfy.sh ─────────────────────────────────────
NTFY_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
  --max-time 10 \
  --connect-timeout 5 \
  -X POST "$NTFY_URL" \
  -H "Title: [${PRIORITY}] Homelab (${SOURCE})" \
  -H "Priority: ${NTFY_PRIO}" \
  -H "Tags: ${NTFY_TAGS}" \
  -d "$MESSAGE")

if [ "$NTFY_RESPONSE" = "200" ] || [ "$NTFY_RESPONSE" = "201" ]; then
  [ "$COOLDOWN" -gt 0 ] && date +%s > "$LOCK_FILE"
  rm -f "$BUNDLE_FILE"
  log "✅ ntfy Fallback OK (priority: ${NTFY_PRIO})"
  exit 0
fi

log "❌ ALLE Kanäle fehlgeschlagen (ntfy HTTP $NTFY_RESPONSE)"
exit 1
