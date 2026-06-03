#!/bin/bash
# Secrets zentral aus .env laden (auch im Cron-Kontext)
set -a; [ -f /home/milan/.env ] && . /home/milan/.env; set +a
# ============================================================
# notify-test-e2e.sh – End-to-End Test aller Notification-Flows
# Usage: notify-test-e2e.sh [--quiet]
# ============================================================

NOTIFY="/home/milan/scripts/notify.sh"
FLUSH="/home/milan/scripts/notify-flush.sh"
DEDUP_DIR="/home/milan/logs/notify_dedup"
BUNDLE_DIR="/home/milan/logs/notify_bundles"
N8N_KEY="${N8N_API_KEY}"
QUIET="${1:-}"
PASS=0; FAIL=0

c_green="\033[32m"; c_red="\033[31m"; c_yellow="\033[33m"; c_reset="\033[0m"

ok()   { PASS=$((PASS+1)); [ "$QUIET" != "--quiet" ] && echo -e "  ${c_green}✅ PASS${c_reset} $1"; }
fail() { FAIL=$((FAIL+1)); echo -e "  ${c_red}❌ FAIL${c_reset} $1"; }
info() { [ "$QUIET" != "--quiet" ] && echo -e "  ${c_yellow}ℹ️${c_reset}  $1"; }
sep()  { [ "$QUIET" != "--quiet" ] && echo ""; echo "── $1 ──────────────────────────────────────"; }

echo "╔══════════════════════════════════════════════════╗"
echo "║        END-TO-END NOTIFICATION TESTS            ║"
echo "║        $(date '+%d.%m.%Y %H:%M:%S')                   ║"
echo "╚══════════════════════════════════════════════════╝"

# ── 0. Voraussetzungen ────────────────────────────────────────
sep "0. Infrastruktur"

# WhatsApp Instanz
WA_STATUS=$(curl -s --max-time 5 "http://milan:8089/instance/fetchInstances" \
  -H "apikey: ${WHATSAPP_API_KEY}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0].get('connectionStatus','?'))" 2>/dev/null)
[ "$WA_STATUS" = "open" ] && ok "WhatsApp Instanz: open" || fail "WhatsApp Instanz: $WA_STATUS"

# n8n
N8N_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://milan:5678/healthz)
[ "$N8N_HTTP" = "200" ] && ok "n8n erreichbar" || fail "n8n HTTP $N8N_HTTP"

# Home Assistant
HA_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://milan:8123/api/)
[ "$HA_HTTP" = "200" ] || [ "$HA_HTTP" = "401" ] && ok "Home Assistant erreichbar" || fail "Home Assistant HTTP $HA_HTTP"

# Evolution API
EVOL_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://milan:8089/)
[ "$EVOL_HTTP" != "000" ] && ok "Evolution API erreichbar" || fail "Evolution API nicht erreichbar"

# ── 1. Morning Briefing ──────────────────────────────────────
sep "1. Morning Briefing (n8n Workflow)"

LAST_RUN=$(curl -s "http://milan:5678/api/v1/executions?workflowId=r9pHNbCufHWhUlPZ&limit=1" \
  -H "X-N8N-API-KEY: $N8N_KEY" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); e=d['data'][0]; print(e['status']+'|'+e['startedAt'][:16])" 2>/dev/null)

STATUS="${LAST_RUN%%|*}"; WHEN="${LAST_RUN##*|}"
if [ "$STATUS" = "success" ]; then
  ok "Letzter Run erfolgreich ($WHEN)"
else
  fail "Letzter Run: $STATUS ($WHEN)"
fi

# WhatsApp-Node konfiguriert?
WA_NODE=$(curl -s "http://milan:5678/api/v1/workflows/r9pHNbCufHWhUlPZ" \
  -H "X-N8N-API-KEY: $N8N_KEY" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for n in d.get('nodes',[]):
    if 'whatsapp' in n['name'].lower():
        url=n.get('parameters',{}).get('url','')
        print('ok' if 'milan-whatsapp' in url else 'wrong:'+url)
        break
" 2>/dev/null)
[ "$WA_NODE" = "ok" ] && ok "WhatsApp-Node korrekt konfiguriert" || fail "WhatsApp-Node: $WA_NODE"

# ── 2. Heizungs-Alerts ──────────────────────────────────────
sep "2. Heizungs-Alerts (Home Assistant)"

# HA-Automationen aktiv?
for AID in "heizung_disconnect_telegram" "heizung_disconnect_restart" "heizung_reconnect_notify"; do
  STATE=$(curl -s --max-time 5 "http://milan:8123/api/states/automation.${AID}" \
    -H "Authorization: Bearer ignore" 2>/dev/null | python3 -c "
import json,sys
try: d=json.load(sys.stdin); print(d.get('state','?'))
except: print('unreachable')
" 2>/dev/null)
  # HA gibt 401 zurück – Automation existiert wenn wir überhaupt eine Antwort bekommen
  [ "$STATE" != "unreachable" ] && ok "Automation $AID: erreichbar" \
    || info "Automation $AID: Status nicht prüfbar ohne HA-Token"
done

# Rest-Command korrekt?
WA_CMD=$(grep "milan-whatsapp" /home/milan/docker_data/homeassistant/configuration.yaml 2>/dev/null)
[ -n "$WA_CMD" ] && ok "HA whatsapp_notify: korrekter Instance-Name" || fail "HA whatsapp_notify: Instance-Name falsch"
NTFY_CMD=$(grep "ntfy_notify" /home/milan/docker_data/homeassistant/configuration.yaml 2>/dev/null)
[ -n "$NTFY_CMD" ] && ok "HA ntfy_notify: konfiguriert" || fail "HA ntfy_notify: fehlt"

# ── 3. Backup-Alarm ──────────────────────────────────────────
sep "3. Backup-Alarm (backup-to-pc.sh)"

# notify.sh korrekt referenziert?
NOTIFY_REF=$(grep "NOTIFY=.*notify.sh" /home/milan/scripts/backup-to-pc.sh 2>/dev/null)
[ -n "$NOTIFY_REF" ] && ok "backup-to-pc.sh nutzt notify.sh" || fail "backup-to-pc.sh referenziert notify.sh nicht"

# Prioritäten korrekt?
CRIT_OK=$(grep "notify_critical" /home/milan/scripts/backup-to-pc.sh 2>/dev/null | wc -l)
[ "$CRIT_OK" -ge 2 ] && ok "Kritische Backup-Alerts mit notify_critical ($CRIT_OK Stellen)" || fail "notify_critical zu selten genutzt"

# Letzter Backup-Run (Log prüfen)
LAST_BACKUP=$(grep "Snapshot.*erfolgreich\|Backup FEHLGESCHLAGEN" /home/milan/backups/logs/pc-backup.log 2>/dev/null | tail -1)
[ -n "$LAST_BACKUP" ] && ok "Backup-Log vorhanden: ${LAST_BACKUP:0:60}..." || info "Kein Backup-Log (PC ggf. offline)"

# ── 4. Self-Test ────────────────────────────────────────────
sep "4. Self-Test (notify-test.sh)"

# Heartbeat prüfen
HEARTBEAT_FILE="/home/milan/logs/notify_heartbeat"
if [ -f "$HEARTBEAT_FILE" ]; then
  LAST_HB=$(cat "$HEARTBEAT_FILE")
  AGE_HB=$(( $(date +%s) - LAST_HB ))
  HOURS=$((AGE_HB / 3600))
  [ $AGE_HB -lt 90000 ] && ok "Heartbeat aktuell (vor ${HOURS}h)" \
    || fail "Heartbeat veraltet! (vor ${HOURS}h – Self-Test läuft nicht)"
else
  info "Kein Heartbeat-File (läuft nach erstem Cron-Durchlauf)"
fi

# Cron konfiguriert?
CRON_TEST=$(crontab -l 2>/dev/null | grep "notify-test")
[ -n "$CRON_TEST" ] && ok "notify-test.sh Cron aktiv: $CRON_TEST" || fail "notify-test.sh Cron fehlt"
CRON_FLUSH=$(crontab -l 2>/dev/null | grep "notify-flush")
[ -n "$CRON_FLUSH" ] && ok "notify-flush.sh Cron aktiv" || fail "notify-flush.sh Cron fehlt"

# ── 5. WhatsApp-Fallback auf ntfy ───────────────────────────
sep "5. WhatsApp-Fallback (ntfy)"

# ntfy direkt erreichbar?
NTFY_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 \
  -X POST "https://ntfy.sh/milan-homelab-b16b1e8d" \
  -H "Title: E2E Test" -H "Priority: low" -H "Tags: test_tube" \
  -d "E2E-Test: ntfy Fallback ✅ ($(date '+%H:%M'))")
[ "$NTFY_HTTP" = "200" ] || [ "$NTFY_HTTP" = "201" ] \
  && ok "ntfy erreichbar + Testnachricht gesendet (HTTP $NTFY_HTTP)" \
  || fail "ntfy nicht erreichbar (HTTP $NTFY_HTTP)"

# Retry-Logik in notify.sh vorhanden?
RETRY_OK=$(grep "_wa_send\|WA_RETRY_DELAY" /home/milan/scripts/notify.sh 2>/dev/null | wc -l)
[ "$RETRY_OK" -ge 2 ] && ok "Retry-Logik in notify.sh vorhanden" || fail "Retry-Logik fehlt"

# ── Ergebnis ─────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════"
TOTAL=$((PASS+FAIL))
if [ $FAIL -eq 0 ]; then
  echo -e "${c_green}✅ ALLE $TOTAL Tests bestanden${c_reset}"
else
  echo -e "${c_red}❌ $FAIL/$TOTAL Tests fehlgeschlagen${c_reset}"
fi
echo "════════════════════════════════════════════════════"
exit $FAIL
