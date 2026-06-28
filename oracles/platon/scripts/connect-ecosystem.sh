#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLATON_URL="${PLATON_URL:-http://78.17.126.214}"
HUB_URL="${HUB_URL:-http://127.0.0.1:9083}"

echo "▸ 1/5 Building Alien Monitor frontend..."
cd /root/alien-monitor/frontend
if [ ! -d node_modules ]; then npm install -q; fi
VITE_BASE_PATH=/monitor/ npm run build

echo "▸ 2/5 Starting ecosystem (Hub + Monitor)..."
cd "$ROOT/ecosystem"
docker compose up -d --build

echo "▸ 3/5 Recreating Platon with ecosystem network..."
cd "$ROOT"
docker compose up -d --build platon-backend

echo "▸ 4/5 Reloading nginx..."
cp "$ROOT/nginx/platon.conf" /etc/nginx/sites-available/platon
nginx -t && systemctl reload nginx

echo "▸ 5/6 Federation crawl — first contact (register peer)..."
sleep 5
ADMIN="${AIMARKET_ADMIN_TOKEN:-platon-ecosystem-admin}"
curl -sf -X POST -H "Authorization: Bearer $ADMIN" \
  "$HUB_URL/ai-market/v2/federation/crawl" | python3 -m json.tool 2>/dev/null || true

echo "▸ 6/6 Federation crawl — index signed manifest..."
sleep 2
curl -sf -X POST -H "Authorization: Bearer $ADMIN" \
  "$HUB_URL/ai-market/v2/federation/crawl" | python3 -m json.tool 2>/dev/null || \
  curl -sf -X POST -H "Authorization: Bearer $ADMIN" "$HUB_URL/ai-market/v2/federation/crawl"

echo ""
echo "▸ Verifying..."
curl -sf "$HUB_URL/ai-market/v2/search?intent=platon+oracle" | python3 -c "
import sys,json
d=json.load(sys.stdin)
hits=d.get('matches') or d.get('results') or d.get('plan') or []
print('search hits:', len(hits))
for h in hits[:5]:
    print(' -', h.get('capability_id') or h.get('name') or h)
" 2>/dev/null || echo "(search pending — crawl may need a moment)"

curl -sf http://127.0.0.1:9100/api/health | python3 -m json.tool 2>/dev/null | head -8

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Ecosystem connected                                 ║"
echo "║  Platon:   $PLATON_URL"
echo "║  Hub:      http://78.17.126.214:9083"
echo "║  Monitor:  http://78.17.126.214/monitor/"
echo "╚══════════════════════════════════════════════════════╝"
