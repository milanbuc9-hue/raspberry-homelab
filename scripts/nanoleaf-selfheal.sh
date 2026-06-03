#!/bin/bash
# Secrets zentral aus .env laden (auch im Cron-Kontext)
set -a; [ -f /home/milan/.env ] && . /home/milan/.env; set +a
# Nanoleaf Self-Heal: prüft alle 5 Minuten ob light.licht erreichbar ist.
# Bei Ausfall >5 Min: openthread restart → matter-server restart → Claude Code Diagnose.
#
# Cron: */5 * * * * /home/milan/scripts/nanoleaf-selfheal.sh >> /home/milan/logs/nanoleaf-selfheal.log 2>&1

HA_TOKEN="${HA_TOKEN}"
NTFY_URL="https://ntfy.sh/milan-homelab-b16b1e8d"
TELEGRAM_URL="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
TELEGRAM_CHAT="6372069186"
STATE_FILE="/tmp/nanoleaf_offline_since"
HEAL_LOCK="/tmp/nanoleaf_healing"
RF_NOTIFY_LOCK="/tmp/nanoleaf_rf_notified"
OFFLINE_THRESHOLD=300   # 5 Minuten bis erster Heal-Versuch
HEAL_COOLDOWN=1800      # 30 Minuten zwischen Heal-Versuchen
RF_NOTIFY_COOLDOWN=3600 # 1h zwischen RF-Schwäche-Notifications (kein Spam)
NANOLEAF_MAC="5eadfd9d0e81a358"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

notify() {
    local title="$1" msg="$2" priority="${3:-default}"
    curl -sf -X POST "$TELEGRAM_URL" \
      -H "Content-Type: application/json" \
      -d "{\"chat_id\":\"$TELEGRAM_CHAT\",\"text\":\"🏠 <b>${title}</b>\n${msg}\",\"parse_mode\":\"HTML\"}" > /dev/null
    curl -sf -X POST "$NTFY_URL" \
      -H "Title: $title" -H "Priority: $priority" \
      -d "$msg" > /dev/null
}

push_thread_credentials() {
    local DATASET
    DATASET=$(docker exec openthread ot-ctl dataset active -x 2>/dev/null | head -1 | tr -d '\r\n')
    [ -z "$DATASET" ] && return 1
    python3 - <<EOF 2>/dev/null
import asyncio, json, websockets
async def push():
    async with websockets.connect('ws://localhost:5580/ws') as ws:
        await ws.recv()
        await ws.send(json.dumps({'message_id': 'tc', 'command': 'set_thread_dataset', 'args': {'dataset': '${DATASET}'}}))
        resp = json.loads(await ws.recv())
        print('OK' if 'error_code' not in resp else resp.get('error_code'))
asyncio.run(push())
EOF
}

# Startet otbr-agent wenn er tot ist und stellt Thread-Dataset aus HA wieder her.
# Gibt 0 zurück wenn otbr-agent danach läuft, 1 wenn RCP nicht antwortet.
restore_thread_network() {
    if docker exec openthread pgrep -x otbr-agent >/dev/null 2>&1; then
        log "restore_thread_network: otbr-agent läuft bereits"
        return 0
    fi
    log "restore_thread_network: otbr-agent tot — starte direkt..."
    docker exec -d openthread /usr/sbin/otbr-agent \
        -I wpan0 -B eth0 \
        spinel+hdlc+uart:///dev/ttyUSB0?uart-baudrate=460800 \
        -d6
    sleep 12
    if ! docker exec openthread pgrep -x otbr-agent >/dev/null 2>&1; then
        log "restore_thread_network: otbr-agent Start fehlgeschlagen (RCP antwortet nicht)"
        return 1
    fi
    log "restore_thread_network: otbr-agent gestartet, restore Thread-Dataset aus HA..."
    local HA_DATASET
    HA_DATASET=$(docker exec homeassistant python3 -c "
import json
with open('/config/.storage/thread.datasets') as f:
    d = json.load(f)
print(d['data']['datasets'][0]['tlv'])
" 2>/dev/null)
    if [ -n "$HA_DATASET" ]; then
        docker exec openthread ot-ctl dataset set active "$HA_DATASET" 2>/dev/null
        docker exec openthread ot-ctl ifconfig up 2>/dev/null
        docker exec openthread ot-ctl thread start 2>/dev/null
        sleep 15
        /home/milan/scripts/otbr-apply-config.sh >/dev/null 2>&1
        log "restore_thread_network: Thread-Dataset restored, State=$(docker exec openthread ot-ctl state 2>/dev/null | tr -d '\r\n ')"
    else
        log "restore_thread_network: kein HA-Dataset gefunden"
    fi
    push_thread_credentials >/dev/null 2>&1
    return 0
}

ha_state() {
    curl -sf -H "Authorization: Bearer $HA_TOKEN" \
      "http://localhost:8123/api/states/$1" \
      | python3 -c "import json,sys; print(json.load(sys.stdin).get('state','unknown'))" 2>/dev/null
}

# ── Health-Checks: erkennen ob Stack tatsächlich kaputt ist ──────────────────
# otbr_healthy: 0 wenn otbr-agent läuft UND State in (leader|router|child)
otbr_healthy() {
    docker exec openthread pgrep -x otbr-agent >/dev/null 2>&1 || return 1
    local STATE
    STATE=$(docker exec openthread ot-ctl state 2>/dev/null | head -1 | tr -d '\r\n ')
    case "$STATE" in
        leader|router|child) return 0 ;;
        *) return 1 ;;
    esac
}

# chip_json_ok: 0 wenn chip.json existiert UND > 1KB (echter Node-Store, nicht leer)
chip_json_ok() {
    local SIZE
    SIZE=$(docker exec matter-server stat -c %s /data/chip.json 2>/dev/null)
    [ -n "$SIZE" ] && [ "$SIZE" -gt 1024 ]
}

# credentials_set: 0 wenn matter-server thread_credentials_set=true meldet
credentials_set() {
    python3 - <<'EOF' 2>/dev/null | grep -q '^OK$'
import asyncio, json, websockets
async def check():
    try:
        async with websockets.connect('ws://localhost:5580/ws', open_timeout=5) as ws:
            srv_info = json.loads(await ws.recv())
            if srv_info.get('thread_credentials_set'):
                print('OK')
    except Exception:
        pass
asyncio.run(check())
EOF
}

# matter_healthy: chip.json ok UND credentials gesetzt
matter_healthy() {
    chip_json_ok && credentials_set
}

# ── Prüfen ob Gerät physisch im Thread-Netz sichtbar ist ─────────────────────
device_in_thread() {
    # Sichtbar als Router oder Neighbor → powered on
    docker exec openthread ot-ctl router table 2>/dev/null | grep -qi "$NANOLEAF_MAC" && return 0
    docker exec openthread ot-ctl neighbor table 2>/dev/null | grep -qi "$NANOLEAF_MAC" && return 0
    # Letzte Chance: ping auf bekannte Thread-IPv6
    docker exec openthread ot-ctl ping fd9f:5dff:70af:1:0:ff:fe00:1c00 1 2>/dev/null | grep -q "1 packets received" && return 0
    return 1
}

# ── Claude Code Diagnose (Schritt 5) ─────────────────────────────────────────
claude_diagnose() {
    local entity="$1" offline_sec="$2" steps_so_far="$3"
    log "Starte Claude Code Diagnose für $entity..."
    notify "Claude Code Diagnose 🤖" "Alle manuellen Schritte fehlgeschlagen. Claude Code analysiert jetzt $entity..." "default"

    local RESULT
    RESULT=$(timeout 300 /home/milan/.local/bin/claude \
      --dangerously-skip-permissions \
      --print \
      "Matter-Gerät ${entity} ist seit ${offline_sec}s unavailable. Bisherige Schritte ohne Erfolg: ${steps_so_far}. Führe eine Tiefenanalyse durch (matter-server logs, Thread-Netz, Node-Status) und versuche das Problem zu lösen. Antworte auf Deutsch in max. 5 Sätzen: was du analysiert hast, was das Problem war, was du getan hast und ob es geklappt hat." \
      2>/dev/null | tail -20)

    local NEW_STATE
    NEW_STATE=$(ha_state "$entity")
    if [ "$NEW_STATE" != "unavailable" ] && [ "$NEW_STATE" != "unknown" ]; then
        notify "Claude Code hat gefixt ✅" "Gerät war ${offline_sec}s offline.\n\n<b>Analyse:</b>\n${RESULT}" "low"
        log "Claude Code erfolgreich: $entity wieder online"
        return 0
    else
        notify "${entity} OFFLINE ❌ Claude Code gescheitert" "${RESULT}\n\n<i>Tipp: Gerät vom Strom trennen und neu starten.</i>" "high"
        log "Claude Code konnte $entity nicht reparieren"
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────

STATE=$(ha_state "light.licht")

if [ "$STATE" != "unavailable" ] && [ "$STATE" != "unknown" ]; then
    if [ -f "$STATE_FILE" ]; then
        OFFLINE_SINCE=$(cat "$STATE_FILE")
        OFFLINE_SEC=$(( $(date +%s) - OFFLINE_SINCE ))
        log "Nanoleaf wieder online (war ${OFFLINE_SEC}s offline)"
        notify "Nanoleaf wieder online ✅" "Licht war ${OFFLINE_SEC}s offline und ist jetzt wieder verbunden." "low"
        rm -f "$STATE_FILE" "$HEAL_LOCK"
    fi
    exit 0
fi

# Offline-Pfad
if [ ! -f "$STATE_FILE" ]; then
    date +%s > "$STATE_FILE"
    log "Nanoleaf offline erkannt — starte Beobachtung"
    exit 0
fi

OFFLINE_SINCE=$(cat "$STATE_FILE")
NOW=$(date +%s)
OFFLINE_SEC=$((NOW - OFFLINE_SINCE))

log "Nanoleaf offline seit ${OFFLINE_SEC}s (state=$STATE)"

[ "$OFFLINE_SEC" -lt "$OFFLINE_THRESHOLD" ] && exit 0

# ── Früherkennung: Gerät vom Strom getrennt oder OTBR-Agent tot? ─────────────
OTBR_AGENT_ALIVE=$(docker exec openthread pgrep -x otbr-agent 2>/dev/null)
if ! device_in_thread; then
    if [ -z "$OTBR_AGENT_ALIVE" ]; then
        # otbr-agent ist tot → Thread-Netz down → kein Signal, aber kein echter Geräte-Ausfall
        log "OTBR-Agent nicht aktiv — Thread-Netz down, kein Signal. Heilung wird trotzdem versucht."
    else
        log "Nanoleaf nicht im Thread-Netz sichtbar — wahrscheinlich ausgeschaltet oder vom Strom getrennt"
        # Nur einmalig benachrichtigen (nicht bei jedem 5-Minuten-Check)
        if [ ! -f "$HEAL_LOCK" ] || [ $(( NOW - $(cat "$HEAL_LOCK") )) -ge "$HEAL_COOLDOWN" ]; then
            date +%s > "$HEAL_LOCK"
            notify "Nanoleaf offline — kein Thread-Signal 🔌" \
              "Licht seit ${OFFLINE_SEC}s offline und im Thread-Netz nicht sichtbar.\nWahrscheinlich ausgeschaltet oder vom Strom getrennt. Kein automatischer Heal möglich." "low"
        fi
        exit 0
    fi
fi

log "Nanoleaf im Thread-Netz sichtbar → kein Strom-/Power-Problem"

# ── RF-Schwäche-Vorprüfung: wenn der gesamte Stack gesund ist und die Heizung
#    weiterhin funktioniert, dann ist es kein Software-Defekt, sondern ein
#    physikalisches RF-Problem. In dem Fall bringt KEIN Restart etwas — nur
#    USB-Verlängerung, Repeater oder besserer Standort hilft.
HEIZUNG_PRE=$(ha_state "climate.heizung_milans_zimmer")
if otbr_healthy && matter_healthy && \
   [ "$HEIZUNG_PRE" != "unavailable" ] && [ "$HEIZUNG_PRE" != "unknown" ]; then
    log "Diagnose: Stack gesund (otbr+matter+credentials OK, Heizung online) → RF-Schwäche, kein Restart"
    if [ ! -f "$RF_NOTIFY_LOCK" ] || [ $(( NOW - $(cat "$RF_NOTIFY_LOCK") )) -ge "$RF_NOTIFY_COOLDOWN" ]; then
        date +%s > "$RF_NOTIFY_LOCK"
        notify "Nanoleaf RF-schwach 📶" \
          "Licht seit ${OFFLINE_SEC}s offline, aber Thread-Mesh + matter-server gesund.\nUrsache: schwaches Funksignal zur Lampe. USB-Verlängerung für SLZB-07 oder Thread-Repeater nötig." "low"
    fi
    exit 0
fi

# Cooldown prüfen (übersprungen wenn otbr-agent tot ist — direkter Start ist leichtgewichtig)
if [ -f "$HEAL_LOCK" ] && [ -n "$OTBR_AGENT_ALIVE" ]; then
    LAST_HEAL=$(cat "$HEAL_LOCK")
    SINCE_HEAL=$((NOW - LAST_HEAL))
    if [ "$SINCE_HEAL" -lt "$HEAL_COOLDOWN" ]; then
        log "Cooldown aktiv — letzter Heal vor ${SINCE_HEAL}s, warte..."
        exit 0
    fi
fi

log "Starte Auto-Heal nach ${OFFLINE_SEC}s Ausfall (Stack-Defekt vermutet)..."
date +%s > "$HEAL_LOCK"
notify "Nanoleaf Auto-Heal gestartet 🔧" "Licht seit ${OFFLINE_SEC}s offline (Thread-Signal vorhanden). Starte Diagnose..." "default"
STEPS=""

# Schritt 0: Partition-Recovery — wenn OTBR NICHT Leader ist, ist das Mesh
# fehlerhaft attached (Nanoleaf hat Leadership übernommen, klassischer Split).
# Wir können releaserouterid nur als Leader ausführen → erst otbr-apply-config
# triggern, das macht thread stop/start + Leader-Wahl.
OTBR_STATE=$(docker exec openthread ot-ctl state 2>/dev/null | tr -d '\r\n ')
if [ "$OTBR_STATE" != "leader" ]; then
    LEADER_RID=$(docker exec openthread ot-ctl leaderdata 2>/dev/null | grep "Leader Router ID" | awk '{print $NF}')
    if [ -n "$LEADER_RID" ] && [ "$LEADER_RID" != "40" ]; then
        log "Schritt 0a: OTBR ist nicht Leader (state=$OTBR_STATE, Leader=$LEADER_RID) → otbr-apply-config"
        /home/milan/scripts/otbr-apply-config.sh >> /home/milan/logs/nanoleaf-selfheal.log 2>&1
        sleep 30
        OTBR_STATE=$(docker exec openthread ot-ctl state 2>/dev/null | tr -d '\r\n ')
        log "Schritt 0a: state nach Recovery=$OTBR_STATE"
    fi
fi

if [ "$OTBR_STATE" = "leader" ]; then
    NL_RLOC=$(docker exec openthread ot-ctl router table 2>/dev/null | grep -i "$NANOLEAF_MAC" | awk '{print $4}')
    if [ -n "$NL_RLOC" ]; then
        RLOC_DEC=$((16#${NL_RLOC#0x}))
        ROUTER_ID=$((RLOC_DEC >> 10))
        log "Schritt 0: releaserouterid $ROUTER_ID"
        docker exec openthread ot-ctl releaserouterid "$ROUTER_ID" 2>/dev/null
        sleep 30
        STATE=$(ha_state "light.licht")
        if [ "$STATE" != "unavailable" ] && [ "$STATE" != "unknown" ]; then
            log "Schritt 0 erfolgreich"
            rm -f "$STATE_FILE" "$HEAL_LOCK"
            notify "Nanoleaf geheilt ✅" "Licht war ${OFFLINE_SEC}s offline — Router-ID Release hat geholfen." "low"
            exit 0
        fi
        STEPS="releaserouterid fehlgeschlagen"
        log "Schritt 0 fehlgeschlagen"
    fi
fi

# Schritt 0.5: otbr-agent direkt starten wenn tot (kein voller Container-Restart nötig)
if [ -z "$OTBR_AGENT_ALIVE" ]; then
    log "Schritt 0.5: otbr-agent tot — direkter Neustart ohne Container-Restart"
    if restore_thread_network >> /home/milan/logs/nanoleaf-selfheal.log 2>&1; then
        sleep 60
        STATE=$(ha_state "light.licht")
        if [ "$STATE" != "unavailable" ] && [ "$STATE" != "unknown" ]; then
            log "Schritt 0.5 erfolgreich"
            rm -f "$STATE_FILE" "$HEAL_LOCK"
            notify "Nanoleaf geheilt ✅" "Licht war ${OFFLINE_SEC}s offline — otbr-agent-Direktstart hat geholfen." "low"
            exit 0
        fi
    fi
    STEPS="${STEPS:+$STEPS, }otbr-agent-Direktstart fehlgeschlagen"
    log "Schritt 0.5 fehlgeschlagen"
fi

# Schritt 1: openthread neu starten — NUR wenn OTBR-Stack defekt UND Heizung
# auch offline ist. Wenn OTBR healthy ist, bringt restart nichts gegen RF-Probleme
# und killt unnötig alle anderen Matter-Geräte.
HEIZUNG_STATE=$(ha_state "climate.heizung_milans_zimmer")
if otbr_healthy; then
    log "Schritt 1: openthread restart übersprungen — OTBR-Stack ist gesund (state=$(docker exec openthread ot-ctl state 2>/dev/null | head -1 | tr -d '\r\n '))"
    STEPS="${STEPS:+$STEPS, }OTBR-Neustart übersprungen (Stack gesund)"
elif [ "$HEIZUNG_STATE" = "unavailable" ] || [ "$HEIZUNG_STATE" = "unknown" ]; then
    log "Schritt 1: openthread restart (Stack defekt, Heizung ebenfalls offline — vertretbar)"
    docker restart openthread >> /dev/null 2>&1
    sleep 30
    restore_thread_network >> /home/milan/logs/nanoleaf-selfheal.log 2>&1
    /home/milan/scripts/otbr-apply-config.sh >> /home/milan/logs/nanoleaf-selfheal.log 2>&1
    sleep 60
    STATE=$(ha_state "light.licht")
    if [ "$STATE" != "unavailable" ] && [ "$STATE" != "unknown" ]; then
        log "Schritt 1 erfolgreich"
        rm -f "$STATE_FILE"
        notify "Nanoleaf geheilt ✅" "Licht war ${OFFLINE_SEC}s offline — nach OTBR-Neustart wieder verbunden." "low"
        exit 0
    fi
    STEPS="${STEPS:+$STEPS, }OTBR-Neustart fehlgeschlagen"
else
    log "Schritt 1: openthread restart übersprungen — Heizung (W600) ist online, Kollateralschaden vermieden"
    STEPS="${STEPS:+$STEPS, }OTBR-Neustart übersprungen (W600 online)"
fi

# Schritt 2a: Wenn nur Thread-Credentials fehlen → push (kein Restart nötig)
if ! credentials_set; then
    log "Schritt 2a: thread_credentials_set=false → push ohne Restart"
    PUSH_RESULT=$(push_thread_credentials)
    log "Thread-Credentials-Push: ${PUSH_RESULT:-nicht abrufbar}"
    sleep 20
    STATE=$(ha_state "light.licht")
    if [ "$STATE" != "unavailable" ] && [ "$STATE" != "unknown" ]; then
        log "Schritt 2a erfolgreich (nur Credentials-Push, kein Restart)"
        rm -f "$STATE_FILE"
        notify "Nanoleaf geheilt ✅" "Licht war ${OFFLINE_SEC}s offline — Credentials-Push hat geholfen, kein Restart nötig." "low"
        exit 0
    fi
    STEPS="${STEPS:+$STEPS, }Credentials-Push erfolglos"
fi

# Schritt 2b: matter-server restart — NUR wenn chip.json kaputt UND Heizung
# offline. Wenn chip.json ok und Heizung online: Restart bringt nichts (es ist RF).
HEIZUNG_STATE_STEP2=$(ha_state "climate.heizung_milans_zimmer")
if chip_json_ok; then
    log "Schritt 2b: matter-server restart übersprungen — chip.json gesund (Nodes nicht verloren)"
    STEPS="${STEPS:+$STEPS, }matter-server-Restart übersprungen (chip.json ok)"
elif [ "$HEIZUNG_STATE_STEP2" = "unavailable" ] || [ "$HEIZUNG_STATE_STEP2" = "unknown" ]; then
    log "Schritt 2b: matter-server restart (chip.json defekt, Heizung ebenfalls offline)"
    docker restart matter-server >> /dev/null 2>&1
    sleep 60
    PUSH_RESULT=$(push_thread_credentials)
    log "Thread-Credentials nach Restart: ${PUSH_RESULT:-nicht abrufbar}"
    sleep 10
    STATE=$(ha_state "light.licht")
    if [ "$STATE" != "unavailable" ] && [ "$STATE" != "unknown" ]; then
        log "Schritt 2b erfolgreich"
        rm -f "$STATE_FILE"
        notify "Nanoleaf geheilt ✅" "Licht war ${OFFLINE_SEC}s offline — nach matter-server-Neustart wieder verbunden." "low"
        exit 0
    fi
    STEPS="${STEPS:+$STEPS, }matter-server-Neustart fehlgeschlagen"
else
    log "Schritt 2b: matter-server restart übersprungen — Heizung (W600) ist online, Kollateralschaden vermieden"
    STEPS="${STEPS:+$STEPS, }matter-server-Neustart übersprungen (W600 online)"
fi

# Schritt 3: Claude Code Diagnose
claude_diagnose "light.licht" "$OFFLINE_SEC" "$STEPS"
[ $? -eq 0 ] && rm -f "$STATE_FILE" "$HEAL_LOCK"
