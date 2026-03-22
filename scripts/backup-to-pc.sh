#!/bin/bash
# ============================================================
# backup-to-pc.sh – Raspberry Pi → Linux PC via Tailscale
# Läuft alle 2h per Cron. Nur wenn PC online, sonst stille Pause.
# Snapshots mit Hard Links – 4 Snapshots werden behalten.
# ============================================================

PC_IP="100.78.126.104"
PC_USER="${BACKUP_PC_USER:-milo}"
PC_DEST="${BACKUP_PC_DEST:-/home/$PC_USER/raspberry-backup}"
KEEP_SNAPSHOTS=4
LOG_FILE="/home/milan/backups/logs/pc-backup.log"
LAST_SUCCESS_FILE="/home/milan/backups/logs/last-pc-backup-success"
TELEGRAM_BOT="8577766573:AAFkMIeGMRaE9tTGP8S1L6cJrP1ebDNgKNU"
TELEGRAM_CHAT="6372069186"

# ---- Hilfsfunktionen ----
log() { echo "[$(date '+%d.%m.%Y %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

telegram() {
  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${TELEGRAM_CHAT}\",\"text\":\"$1\",\"parse_mode\":\"Markdown\"}" > /dev/null
}

# ---- PC Online? ----
if ! ping -c 1 -W 3 "$PC_IP" > /dev/null 2>&1; then
  exit 0
fi

# ---- SSH erreichbar? ----
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no \
    "${PC_USER}@${PC_IP}" "mkdir -p ${PC_DEST}" 2>/dev/null; then
  log "ERROR: PC online aber SSH nicht erreichbar (${PC_IP})"
  telegram "⚠️ *Backup-Fehler*\nPC ist online aber SSH schlägt fehl.\nBitte SSH auf dem PC prüfen."
  exit 1
fi

SNAPSHOT=$(date +%Y-%m-%d_%H-%M)
SNAPSHOT_DIR="${PC_DEST}/${SNAPSHOT}"

# Letzten Snapshot finden für --link-dest (nicht der aktuelle)
LATEST=$(ssh -o StrictHostKeyChecking=no "${PC_USER}@${PC_IP}" \
  "ls -1d ${PC_DEST}/????-??-??_??-??/ 2>/dev/null | sort | grep -v '${SNAPSHOT}' | tail -1 | sed 's|/$||'" 2>/dev/null || echo "")

ssh -o StrictHostKeyChecking=no "${PC_USER}@${PC_IP}" "mkdir -p ${SNAPSHOT_DIR}/docker_data" 2>/dev/null

log "PC online – starte Snapshot ${SNAPSHOT}"
START_TIME=$(date +%s)

# ---- rsync mit Hard Links ----
LINK_DEST_ARG=""
[ -n "$LATEST" ] && LINK_DEST_ARG="--link-dest=${LATEST}/docker_data"

rsync -az --ignore-errors $LINK_DEST_ARG \
  --exclude='homeassistant/backups/' \
  --exclude='gym-tracker/data/*.backup_*' \
  --exclude='prometheus/' \
  --exclude='*.tmp' \
  --exclude='*.log' \
  --exclude='node-exporter/' \
  -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
  /home/milan/docker_data/ \
  "${PC_USER}@${PC_IP}:${SNAPSHOT_DIR}/docker_data/" \
  2>> "$LOG_FILE"

RSYNC_EXIT=$?
[ $RSYNC_EXIT -eq 23 ] && RSYNC_EXIT=0

rsync -az \
  -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
  /home/milan/docker-compose.yml \
  /home/milan/.env \
  /home/milan/scripts/ \
  "${PC_USER}@${PC_IP}:${SNAPSHOT_DIR}/" \
  2>> "$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

if [ $RSYNC_EXIT -eq 0 ]; then
  # Alte Snapshots löschen, nur KEEP_SNAPSHOTS behalten
  ssh -o StrictHostKeyChecking=no "${PC_USER}@${PC_IP}" \
    "ls -1d ${PC_DEST}/????-??-??_??-??/ 2>/dev/null | sort | head -n -${KEEP_SNAPSHOTS} | xargs -r rm -rf" 2>/dev/null

  SIZE=$(ssh -o StrictHostKeyChecking=no "${PC_USER}@${PC_IP}" \
    "du -sh ${PC_DEST} 2>/dev/null | cut -f1" 2>/dev/null || echo "?")

  log "✅ Snapshot ${SNAPSHOT} erfolgreich | Dauer: ${DURATION}s | Gesamt: ${SIZE}"
  date +%s > "$LAST_SUCCESS_FILE"

  # Telegram nur einmal täglich bei Erfolg
  LAST_NOTIFIED="/home/milan/backups/logs/last-telegram-success"
  TODAY=$(date +%Y-%m-%d)
  LAST_DAY=$(cat "$LAST_NOTIFIED" 2>/dev/null || echo "")
  if [ "$LAST_DAY" != "$TODAY" ]; then
    telegram "✅ *Backup auf PC erfolgreich*\n$(date '+%d.%m.%Y %H:%M')\nGesamt: ${SIZE} | Dauer: ${DURATION}s"
    echo "$TODAY" > "$LAST_NOTIFIED"
  fi
else
  log "❌ Backup FEHLGESCHLAGEN (rsync exit: $RSYNC_EXIT)"
  if [ -f "$LAST_SUCCESS_FILE" ]; then
    LAST=$(cat "$LAST_SUCCESS_FILE")
    NOW=$(date +%s)
    AGE=$((NOW - LAST))
    if [ $AGE -gt 86400 ]; then
      telegram "🔴 *Backup-Alarm!*\nKein erfolgreiches PC-Backup seit 24+ Stunden!\nLetztes Backup: $(date -d @$LAST '+%d.%m.%Y %H:%M')"
    fi
  fi
fi
