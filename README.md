# 🏠 Raspberry Pi 5 Homelab

Personal homelab running on a **Raspberry Pi 5 (8GB)** with Debian 12 Bookworm.
Fully dockerized, GitOps-ready – `git push` deploys automatically via GitHub Actions.

## Stack

| Service | Port | Beschreibung |
|---|---|---|
| Home Assistant | `8123` | Smart Home Zentrale |
| n8n | `5678` | Automation & Workflows |
| Grafana | `3000` | Monitoring Dashboards |
| Prometheus | `9090` | Metrics & Alerting |
| Blackbox Exporter | `9115` | HTTP/TCP Uptime-Monitoring |
| cAdvisor | `8082` | Container Metrics |
| Node Exporter | `9100` | System Metrics |
| Evolution API | `8089` | WhatsApp API |
| Uptime Kuma | `3001` | Service Status |
| Portainer | `9000` | Docker Management |
| code-server | `8443` | VS Code im Browser |
| Duplicati | `8200` | Backup UI |
| Whisper | `10300` | Speech-to-Text (Wyoming) |
| Watchtower | – | Auto-Updates (täglich 04:00) |
| Tailscale | – | VPN / Remote-Zugriff |
| Cloudflared | – | Cloudflare Tunnel (systemd) |
| Matter Server | – | Thread/Matter für HA |
| OpenThread | – | Thread Border Router |

## Setup

### Voraussetzungen
- Docker & Docker Compose installiert
- Git installiert
- Tailscale eingerichtet (optional, für Remote-Zugriff)

### 1. Repo klonen
```bash
git clone https://github.com/milanbuc9-hue/raspberry-homelab.git
cd raspberry-homelab
```

### 2. `.env` anlegen
```bash
cp .env.example .env
nano .env   # Alle Werte ausfüllen
```

### 3. Home Assistant Token für Prometheus
```bash
# HA Long-Lived Token in diese Datei schreiben:
echo "dein-ha-token" > docker_data/prometheus/ha_token.txt
```

### 4. Stack starten
```bash
docker compose up -d
```

## Backup-System

**Layer 1 – Lokal** (täglich 03:00)
`rsync` nach `/home/milan/backups/daily/` – letzte 7 Tage behalten

**Layer 2 – Linux PC via Tailscale** (alle 2h)
Snapshots mit Hard Links (`rsync --link-dest`) – 4 Snapshots behalten
Telegram-Benachrichtigung täglich + Alarm bei 24h Ausfall

```bash
# Manuell ausführen:
bash scripts/backup-local.sh
bash scripts/backup-to-pc.sh
```

## CI/CD

GitHub Actions deployt automatisch bei jedem Push auf `main`:

```
git push → GitHub Actions → SSH → docker compose pull && up -d
```

**Benötigte GitHub Secrets:**

| Secret | Wert |
|---|---|
| `PI_HOST` | Tailscale IP des Pi |
| `PI_USER` | `milan` |
| `SSH_PRIVATE_KEY` | Inhalt von `~/.ssh/id_ed25519` |

## Struktur

```
├── docker-compose.yml              # Hauptkonfiguration
├── .env.example                    # Secret-Vorlage
├── scripts/
│   ├── backup-local.sh             # Layer 1 Backup
│   ├── backup-to-pc.sh             # Layer 2 Backup (→ PC)
│   └── health_check.sh             # Stack-Status
├── evolution-reset.sh              # WhatsApp Instanz zurücksetzen
├── docker_data/
│   ├── prometheus/prometheus.yml   # Scrape-Konfiguration
│   ├── blackbox/config.yml         # HTTP/TCP Probe-Module
│   └── grafana/
│       ├── provisioning/           # Auto-Provisioning
│       └── dashboards/             # Dashboard-JSONs
└── .github/workflows/deploy.yml   # CI/CD Pipeline
```
