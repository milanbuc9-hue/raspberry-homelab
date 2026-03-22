#!/bin/bash
# ============================================================
# backup-local.sh – Lokales tägliches Backup auf dem Pi selbst
# Läuft täglich 03:00 per Cron. Behält letzte 7 Tage.
# ============================================================

DEST="/home/milan/backups/daily"
LOG_FILE="/home/milan/backups/logs/local-backup.log"
KEEP_DAYS=7

log() { echo "[$(date '+%d.%m.%Y %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

TODAY=$(date +%Y-%m-%d)
BACKUP_DIR="${DEST}/${TODAY}"

mkdir -p "$BACKUP_DIR"
log "Starte lokales Backup → $BACKUP_DIR"
START_TIME=$(date +%s)

# docker-compose.yml + .env + scripts (klein, immer komplett)
cp /home/milan/docker-compose.yml "$BACKUP_DIR/"
cp /home/milan/.env "$BACKUP_DIR/"
rsync -a /home/milan/scripts/ "$BACKUP_DIR/scripts/" 2>> "$LOG_FILE"

# Datenbanken + kritische Konfigs (schnell, kein großes rsync)
rsync -a \
  --exclude='homeassistant/backups/' \
  --exclude='gym-tracker/data/*.backup_*' \
  --exclude='prometheus/' \
  --exclude='*.tmp' \
  --include='*/' \
  --include='*.db' \
  --include='*.sqlite' \
  --include='*.json' \
  --include='*.yaml' \
  --include='*.yml' \
  --include='*.conf' \
  --include='*.txt' \
  --exclude='*' \
  /home/milan/docker_data/ \
  "$BACKUP_DIR/docker_data_configs/" \
  2>> "$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
log "✅ Lokales Backup fertig | Dauer: ${DURATION}s | Größe: ${SIZE}"

# Alte Backups löschen (älter als KEEP_DAYS)
DELETED=0
while IFS= read -r old_dir; do
  rm -rf "$old_dir"
  log "🗑️ Altes Backup gelöscht: $old_dir"
  ((DELETED++))
done < <(find "$DEST" -maxdepth 1 -mindepth 1 -type d -mtime +${KEEP_DAYS})

if [ $DELETED -gt 0 ]; then
  log "Aufgeräumt: $DELETED alte Backup(s) gelöscht"
fi
