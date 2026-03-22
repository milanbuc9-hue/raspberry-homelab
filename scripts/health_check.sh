#!/bin/bash
echo "=== Smart Home Stack Health Check ==="
echo ""

# Container Status
echo "1. Container Status:"
docker ps --format "{{.Names}}: {{.Status}}" | grep -E "homeassistant|n8n|tailscale|prometheus|grafana"
echo ""

# Memory Usage
echo "2. Memory Usage:"
docker stats --no-stream --format "{{.Name}}: {{.MemUsage}}" | grep -E "homeassistant|n8n|postgres"
echo ""

# Service Reachability
echo "3. Service Health:"
curl -s -o /dev/null -w "Home Assistant: %{http_code}\n" http://localhost:8123
curl -s -o /dev/null -w "n8n: %{http_code}\n" http://localhost:5678
curl -s -o /dev/null -w "Prometheus: %{http_code}\n" http://localhost:9090
curl -s -o /dev/null -w "Grafana: %{http_code}\n" http://localhost:3000
echo ""

# Tailscale
echo "4. Tailscale:"
docker exec tailscale tailscale status | grep milan-homelab
echo ""

echo "=== Health Check Complete ==="
