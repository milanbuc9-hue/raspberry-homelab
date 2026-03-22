#!/bin/bash
# Secrets aus .env laden falls vorhanden
[ -f /home/milan/.env ] && export $(grep -v '^#' /home/milan/.env | xargs)

echo "════════════════════════════════════════"
echo "  Evolution API - Complete Reset"
echo "════════════════════════════════════════"
echo ""

# 1. Container stoppen
echo "🛑 Stoppe Container..."
docker stop evolution-api evolution-postgres
echo "  ✓ Container gestoppt"
echo ""

# 2. Datenbank löschen
echo "🗑️  Lösche Datenbank..."
sudo rm -rf /home/milan/docker_data/evolution-postgres/*
sudo rm -rf /home/milan/docker_data/evolution-instances/*
sudo rm -rf /home/milan/docker_data/evolution-store/*
echo "  ✓ Datenbank gelöscht"
echo ""

# 3. Container neu starten
echo "🔄 Starte Container neu..."
docker start evolution-postgres
echo "  ⏳ Warte 5 Sekunden auf PostgreSQL..."
sleep 5
docker start evolution-api
echo "  ⏳ Warte 10 Sekunden auf Evolution API..."
sleep 10
echo "  ✓ Container gestartet"
echo ""

# 4. Neue Instanz erstellen
echo "✨ Erstelle neue Instanz..."
CREATE_RESPONSE=$(curl -s -X POST http://192.168.0.122:8089/instance/create \
  -H "apikey: ${EVOLUTION_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "instanceName": "whatsapp",
    "number": "4915757232013"
  }')

# Prüfe auf Fehler
if echo "$CREATE_RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
  echo "❌ Fehler beim Erstellen:"
  echo "$CREATE_RESPONSE" | jq '.'
  exit 1
else
  echo "  ✓ Instanz erstellt"
  echo "$CREATE_RESPONSE" | jq '.'
fi

echo ""

# 5. Pairing Code holen
echo "⏳ Warte 3 Sekunden und hole Pairing Code..."
sleep 3

CODE_RESPONSE=$(curl -s -X GET "http://192.168.0.122:8089/instance/connect/whatsapp" \
  -H "apikey: ${EVOLUTION_API_KEY}")

PAIRING_CODE=$(echo "$CODE_RESPONSE" | jq -r '.pairingCode // .code // empty')

if [ -z "$PAIRING_CODE" ]; then
  echo "❌ Kein Pairing Code erhalten!"
  echo "Antwort:"
  echo "$CODE_RESPONSE" | jq '.'
  exit 1
fi

echo ""
echo "╔════════════════════════════════════════╗"
echo "║                                        ║"
echo "║     📱 DEIN PAIRING CODE:              ║"
echo "║                                        ║"
echo "║          $PAIRING_CODE                      ║"
echo "║                                        ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "▶ Gib diesen Code in WhatsApp ein:"
echo "  Einstellungen → Verknüpfte Geräte"
echo "  → Mit Telefonnummer verknüpfen"
echo ""
echo "⏱️  Code läuft in 3 Minuten ab!"
echo ""
echo "════════════════════════════════════════"
