#!/bin/bash
# Vaidyx startup script
# Starts: ChromaDB → Medical MoE Router → Vaidyx (HTTPS)
set -e

VAIDYX_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$VAIDYX_DIR"

echo "[1/4] Starting ChromaDB on port 8100..."
pkill -f "chroma run" 2>/dev/null || true
sleep 1
mkdir -p data/chromadb
nohup chroma run --path data/chromadb --port 8100 > /tmp/chromadb.log 2>&1 &
sleep 3
curl -s http://localhost:8100/api/v2/heartbeat > /dev/null && echo "      ChromaDB UP" || echo "      ChromaDB failed — check /tmp/chromadb.log"

echo "[2/4] Starting Medical MoE Router on port 11435..."
pkill -f "medical_moe_proxy" 2>/dev/null || true
sleep 1
nohup python3 -m uvicorn src.medical_moe_proxy:app \
  --host 0.0.0.0 --port 11435 \
  --log-level warning > /tmp/moe_proxy.log 2>&1 &
sleep 4
curl -s http://localhost:11435/v1/models > /dev/null && echo "      Medical MoE Router UP" || echo "      MoE Router failed — check /tmp/moe_proxy.log"

echo "[3/4] Starting Vaidyx with HTTPS on port 7000..."
pkill -f "uvicorn app:app" 2>/dev/null || true
sleep 2
nohup python3 -m uvicorn app:app \
  --host 0.0.0.0 --port 7000 \
  --ssl-keyfile ssl/key.pem \
  --ssl-certfile ssl/cert.pem \
  --log-level warning > /tmp/vaidyx.log 2>&1 &
sleep 8
curl -sk -o /dev/null -w "      Vaidyx HTTP %{http_code}" https://127.0.0.1:7000/ && echo " — UP" || echo " — failed, check /tmp/vaidyx.log"

echo "[4/4] Done."
echo ""
echo "  Vaidyx:             https://localhost:7000"
echo "  Medical MoE Router: http://localhost:11435"
echo "  ChromaDB:           http://localhost:8100"
echo ""
echo "  In the model picker, select 'medical-moe' to use the MoE Router."
echo "  Browser: click 'Advanced' → 'Proceed to localhost' for self-signed cert."
