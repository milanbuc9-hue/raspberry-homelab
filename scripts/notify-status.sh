#!/bin/bash
# Secrets zentral aus .env laden (auch im Cron-Kontext)
set -a; [ -f /home/milan/.env ] && . /home/milan/.env; set +a
# ============================================================
# notify-status.sh – Status-Dashboard Benachrichtigungssystem
# Usage: notify-status.sh [--json]
# ============================================================

LOG_FILE="/home/milan/logs/notifications.log"
DEDUP_DIR="/home/milan/logs/notify_dedup"
BUNDLE_DIR="/home/milan/logs/notify_bundles"
TG_TOKEN="${TELEGRAM_BOT_TOKEN}"
JSON_MODE="${1:-}"
NOW=$(date +%s)

# ── Telegram Bot Status ───────────────────────────────────────
TG_STATUS=$(curl -s --max-time 5 "https://api.telegram.org/bot${TG_TOKEN}/getMe" \
  | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print('ok' if d.get('ok') else 'error')
except: print('error')
" 2>/dev/null)

# ── Letzte Sends aus Log ──────────────────────────────────────
LAST_OK=$(grep "✅ Telegram OK\|✅ ntfy Fallback OK" "$LOG_FILE" 2>/dev/null | tail -1)
LAST_FAIL=$(grep "❌ ALLE Kanäle\|WhatsApp FAILED nach Retry" "$LOG_FILE" 2>/dev/null | tail -1)
LAST_DEDUP=$(grep "🔕 DEDUP" "$LOG_FILE" 2>/dev/null | tail -1)
LAST_TEST=$(grep "\[self-test\].*Selbsttest abgeschlossen" "$LOG_FILE" 2>/dev/null | tail -1)

# ── Aktive Dedup-Locks ────────────────────────────────────────
ACTIVE_LOCKS=0
LOCK_DETAILS=""
for f in "$DEDUP_DIR"/*; do
  [ -f "$f" ] || continue
  LAST=$(cat "$f" 2>/dev/null || echo 0)
  AGE=$((NOW - LAST))
  # Cooldown anhand Alter schätzen (30 Min oder 2 Std)
  if [ $AGE -lt 1800 ]; then
    REM=$((1800 - AGE))
    LOCK_DETAILS="${LOCK_DETAILS}  $(basename $f | cut -c1-8)... noch ${REM}s (normal)\n"
    ACTIVE_LOCKS=$((ACTIVE_LOCKS+1))
  elif [ $AGE -lt 7200 ]; then
    REM=$((7200 - AGE))
    LOCK_DETAILS="${LOCK_DETAILS}  $(basename $f | cut -c1-8)... noch ${REM}s (low)\n"
    ACTIVE_LOCKS=$((ACTIVE_LOCKS+1))
  fi
done

# ── Pending Bundles ───────────────────────────────────────────
PENDING_BUNDLES=0
BUNDLE_DETAILS=""
for b in "$BUNDLE_DIR"/*.bundle; do
  [ -f "$b" ] || continue
  CNT=$(wc -l < "$b")
  NAME=$(basename "$b" .bundle)
  BUNDLE_DETAILS="${BUNDLE_DETAILS}  $NAME: ${CNT} Meldung(en)\n"
  PENDING_BUNDLES=$((PENDING_BUNDLES+1))
done

# ── Letzte 24h Statistik ──────────────────────────────────────
if [ -f "$LOG_FILE" ]; then
  SINCE=$(date -d '24 hours ago' '+%d.%m.%Y' 2>/dev/null || date '+%d.%m.%Y')
  SENDS_24H=$(grep -c "✅ Telegram OK\|✅ ntfy Fallback OK" "$LOG_FILE" 2>/dev/null || echo 0)
  FAILS_24H=$(grep -c "❌ ALLE Kanäle" "$LOG_FILE" 2>/dev/null || echo 0)
  DEDUP_24H=$(grep -c "🔕 DEDUP" "$LOG_FILE" 2>/dev/null || echo 0)
fi

# ── Ausgabe ───────────────────────────────────────────────────
if [ "$JSON_MODE" = "--json" ]; then
  python3 -c "
import json
print(json.dumps({
  'telegram_status': '${TG_STATUS}',
  'active_locks': ${ACTIVE_LOCKS},
  'pending_bundles': ${PENDING_BUNDLES},
  'sends_24h': ${SENDS_24H:-0},
  'fails_24h': ${FAILS_24H:-0},
  'dedup_24h': ${DEDUP_24H:-0},
  'last_ok': '${LAST_OK}',
  'last_fail': '${LAST_FAIL}',
}, indent=2, ensure_ascii=False))"
  exit 0
fi

# Text-Dashboard
TG_ICON="✅" ; [ "$TG_STATUS" != "ok" ] && TG_ICON="❌"

echo "╔══════════════════════════════════════════════════╗"
echo "║       NOTIFICATION SYSTEM STATUS                ║"
echo "║       $(date '+%d.%m.%Y %H:%M:%S')                    ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "📡 KANÄLE"
echo "  Telegram Bot:         ${TG_ICON} ${TG_STATUS}"
echo "  ntfy Fallback:        ✅ konfiguriert (milan-homelab-b16b1e8d)"
echo ""
echo "📊 LETZTE 24h"
echo "  Gesendet:    ${SENDS_24H:-0}x"
echo "  Fehlgeschl.: ${FAILS_24H:-0}x"
echo "  Unterdrückt: ${DEDUP_24H:-0}x"
echo ""
echo "🔕 AKTIVE THROTTLES (${ACTIVE_LOCKS})"
if [ "$ACTIVE_LOCKS" -gt 0 ]; then
  printf "$LOCK_DETAILS"
else
  echo "  keine"
fi
echo ""
echo "📦 PENDING BUNDLES (${PENDING_BUNDLES})"
if [ "$PENDING_BUNDLES" -gt 0 ]; then
  printf "$BUNDLE_DETAILS"
else
  echo "  keine"
fi
echo ""
echo "🕐 LETZTE EREIGNISSE"
echo "  Letzter Send:   ${LAST_OK:-(keine)}"
echo "  Letzter Fehler: ${LAST_FAIL:-(keine)}"
echo "  Letzter Test:   ${LAST_TEST:-(keine)}"
echo "  Letzter DEDUP:  ${LAST_DEDUP:-(keine)}"
echo ""
echo "📋 LETZTEN 8 LOG-EINTRÄGE"
echo "─────────────────────────────────────────────────"
tail -8 "$LOG_FILE" 2>/dev/null || echo "  (Log leer)"
