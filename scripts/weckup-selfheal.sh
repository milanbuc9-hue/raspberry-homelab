#!/bin/bash
# Secrets zentral aus .env laden (auch im Cron-Kontext)
set -a; [ -f /home/milan/.env ] && . /home/milan/.env; set +a
# Weckup Self-Heal: prüft um 5:47 ob light.licht an ist.
# Falls nicht: versucht zu heilen, schickt Telegram-Zusammenfassung.

HA_TOKEN="${HA_TOKEN}"
TELEGRAM_URL="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
TELEGRAM_CHAT="6372069186"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

telegram() {
    curl -sf -X POST "$TELEGRAM_URL" \
      -H "Content-Type: application/json" \
      -d "{\"chat_id\":\"$TELEGRAM_CHAT\",\"text\":\"$1\",\"parse_mode\":\"HTML\"}" > /dev/null
}

light_state() {
    curl -sf -H "Authorization: Bearer $HA_TOKEN" \
      http://localhost:8123/api/states/light.licht \
      | python3 -c "import json,sys; print(json.load(sys.stdin).get('state','unknown'))" 2>/dev/null
}

light_on_red() {
    curl -sf -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
      -d '{"entity_id":"light.licht","brightness_pct":17,"hs_color":[0,100]}' \
      http://localhost:8123/api/services/light/turn_on > /dev/null
}

NANOLEAF_MAC="5eadfd9d0e81a358"

device_in_thread() {
    docker exec openthread ot-ctl router table 2>/dev/null | grep -qi "$NANOLEAF_MAC" && return 0
    docker exec openthread ot-ctl neighbor table 2>/dev/null | grep -qi "$NANOLEAF_MAC" && return 0
    docker exec openthread ot-ctl ping fd9d:d51:61c4:1:344e:b652:1ab1:369a 1 2>/dev/null | grep -q "1 packets received" && return 0
    return 1
}

STATE=$(light_state)
log "Weckup-Check: light.licht = $STATE"

if [ "$STATE" = "on" ]; then
    log "Licht ist an — alles gut."
    exit 0
fi

# Früherkennung: Gerät physisch ausgeschaltet?
if ! device_in_thread; then
    log "Nanoleaf nicht im Thread-Netz — ausgeschaltet oder vom Strom getrennt"
    telegram "🌅 <b>Weckup: Nanoleaf ausgeschaltet 🔌</b>
Licht ist nicht erreichbar und auch nicht im Thread-Netz sichtbar.
Wahrscheinlich manuell ausgeschaltet — bitte selbst einschalten!"
    exit 1
fi

log "Thread-Signal vorhanden → Matter-Verbindungsproblem, starte Heal"
# Licht ist aus oder unavailable → Heal starten
log "Licht NICHT an (state=$STATE) — starte Weckup-Heal..."
REPORT="🌅 <b>Weckup Self-Heal gestartet</b>
Licht war um 5:47 Uhr nicht an (state: <code>$STATE</code>). Versuche zu reparieren..."

telegram "$REPORT"
STEPS=""

# Schritt 1: Direkt einschalten versuchen
log "Schritt 1: Direktversuch light.turn_on"
light_on_red
sleep 5
STATE=$(light_state)
if [ "$STATE" = "on" ]; then
    log "Schritt 1 erfolgreich"
    STEPS="${STEPS}\n✅ Direktversuch: Licht hat sofort reagiert"
    telegram "🌅 <b>Weckup Heal erfolgreich</b>
${STEPS}

Licht brennt jetzt. Guten Morgen! ☀️"
    exit 0
fi
STEPS="${STEPS}\n❌ Direktversuch: Licht reagiert nicht (state=$STATE)"
log "Schritt 1 fehlgeschlagen"

# Schritt 2: Thread-Credentials neu pushen
log "Schritt 2: Thread-Credentials pushen"
THREAD_DATASET=$(docker exec openthread ot-ctl dataset active -x 2>/dev/null | head -1 | tr -d '\r\n')
if [ -n "$THREAD_DATASET" ]; then
    PUSH_RESULT=$(python3 - <<EOF 2>&1
import asyncio, json, websockets
async def push():
    async with websockets.connect('ws://localhost:5580/ws') as ws:
        await ws.recv()
        await ws.send(json.dumps({'message_id': 'tc', 'command': 'set_thread_dataset', 'args': {'dataset': '${THREAD_DATASET}'}}))
        resp = json.loads(await ws.recv())
        print('OK' if 'error_code' not in resp else resp.get('error_code'))
asyncio.run(push())
EOF
)
    STEPS="${STEPS}\n🔑 Thread-Credentials: $PUSH_RESULT"
    log "Thread-Credentials: $PUSH_RESULT"
    sleep 10
    light_on_red
    sleep 5
    STATE=$(light_state)
    if [ "$STATE" = "on" ]; then
        log "Schritt 2 erfolgreich"
        STEPS="${STEPS}\n✅ Nach Credential-Push: Licht an"
        telegram "🌅 <b>Weckup Heal erfolgreich</b>
${STEPS}

Licht brennt jetzt. Guten Morgen! ☀️"
        exit 0
    fi
    STEPS="${STEPS}\n❌ Nach Credential-Push: Licht immer noch aus"
else
    STEPS="${STEPS}\n⚠️ Thread-Dataset nicht abrufbar"
fi

# Schritt 3: matter-server neu starten
log "Schritt 3: matter-server restart"
STEPS="${STEPS}\n🔄 matter-server Neustart..."
docker restart matter-server >> /dev/null 2>&1
sleep 60

THREAD_DATASET=$(docker exec openthread ot-ctl dataset active -x 2>/dev/null | head -1 | tr -d '\r\n')
if [ -n "$THREAD_DATASET" ]; then
    python3 - <<EOF > /dev/null 2>&1
import asyncio, json, websockets
async def push():
    async with websockets.connect('ws://localhost:5580/ws') as ws:
        await ws.recv()
        await ws.send(json.dumps({'message_id': 'tc2', 'command': 'set_thread_dataset', 'args': {'dataset': '${THREAD_DATASET}'}}))
        await ws.recv()
asyncio.run(push())
EOF
fi

light_on_red
sleep 10
STATE=$(light_state)
if [ "$STATE" = "on" ]; then
    log "Schritt 3 erfolgreich"
    STEPS="${STEPS}\n✅ Nach matter-server Neustart: Licht an"
    telegram "🌅 <b>Weckup Heal erfolgreich</b>
${STEPS}

Licht brennt jetzt. Guten Morgen! ☀️"
    exit 0
fi
STEPS="${STEPS}\n❌ Nach matter-server Neustart: Licht immer noch aus"

# Schritt 4: openthread + matter-server neu starten
log "Schritt 4: openthread + matter-server restart"
STEPS="${STEPS}\n🔄 openthread Neustart..."
docker restart openthread >> /dev/null 2>&1
sleep 35
/home/milan/scripts/otbr-apply-config.sh >> /home/milan/logs/weckup-selfheal.log 2>&1
sleep 30
docker restart matter-server >> /dev/null 2>&1
sleep 60

THREAD_DATASET=$(docker exec openthread ot-ctl dataset active -x 2>/dev/null | head -1 | tr -d '\r\n')
if [ -n "$THREAD_DATASET" ]; then
    python3 - <<EOF > /dev/null 2>&1
import asyncio, json, websockets
async def push():
    async with websockets.connect('ws://localhost:5580/ws') as ws:
        await ws.recv()
        await ws.send(json.dumps({'message_id': 'tc3', 'command': 'set_thread_dataset', 'args': {'dataset': '${THREAD_DATASET}'}}))
        await ws.recv()
asyncio.run(push())
EOF
fi

light_on_red
sleep 10
STATE=$(light_state)
if [ "$STATE" = "on" ]; then
    log "Schritt 4 erfolgreich"
    STEPS="${STEPS}\n✅ Nach OTBR + matter-server Neustart: Licht an"
    telegram "🌅 <b>Weckup Heal erfolgreich</b>
${STEPS}

Licht brennt jetzt. Guten Morgen! ☀️"
    exit 0
fi

STEPS="${STEPS}\n❌ Alle manuellen Schritte fehlgeschlagen"
log "Manuelle Schritte fehlgeschlagen — starte Claude Code Diagnose..."

telegram "🤖 <b>Claude Code Diagnose gestartet...</b>
${STEPS}

Alle manuellen Schritte haben nicht geholfen. Claude Code analysiert jetzt das Problem."

# Schritt 5: Claude Code übernimmt
CLAUDE_OUTPUT=$(/home/milan/.local/bin/claude \
  --dangerously-skip-permissions \
  --print \
  "light.licht (Nanoleaf NL67E200, Matter/Thread) ist unavailable. Alle bisherigen Heal-Schritte (Thread-Credentials push, matter-server restart, OTBR restart) haben nicht geholfen. Führe eine Tiefenanalyse durch: prüfe matter-server logs, Thread-Netz, Node 3 Status. Versuche das Problem zu lösen und schalte das Licht danach auf 17% Rot (hs_color [0,100]) ein. Antworte auf Deutsch, max 5 Sätze Zusammenfassung was du getan hast und ob es geklappt hat." \
  2>/dev/null | tail -20)

log "Claude Code Ergebnis: $CLAUDE_OUTPUT"

STATE=$(light_state)
if [ "$STATE" = "on" ]; then
    telegram "🌅 <b>Claude Code hat es gefixt! ✅</b>

<b>Was Claude getan hat:</b>
${CLAUDE_OUTPUT}

Licht brennt jetzt. Guten Morgen! ☀️"
else
    telegram "🌅 <b>Auch Claude Code konnte es nicht fixen ❌</b>

<b>Claude's Analyse:</b>
${CLAUDE_OUTPUT}

<i>Tipp: Nanoleaf kurz vom Strom trennen und neu starten.</i>"
fi
exit 1
