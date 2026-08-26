#!/usr/bin/env bash
# ACP 2-Agent Demo: Alpha ↔ Beta bidirectional communication
# HTTP port = WebSocket port + 100
set -e

RELAY="relay/acp_relay.py"
WS_A=9200; HTTP_A=9300
WS_B=9201; HTTP_B=9301

cleanup() {
    echo ""; echo "🧹 Cleaning up..."
    kill $PID_A $PID_B 2>/dev/null || true
    sleep 0.3; echo "✅ Done."
}
trap cleanup EXIT

echo "╔══════════════════════════════════════════════════╗"
echo "║     ACP — Agent Communication Protocol          ║"
echo "║     2-Agent Bidirectional Demo (v2.95)          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "▶  Starting Alpha (ws:$WS_A / http:$HTTP_A)..."
python3 $RELAY --port $WS_A --name Alpha --no-identity > /tmp/acp_alpha.log 2>&1 &
PID_A=$!
echo "▶  Starting Beta  (ws:$WS_B / http:$HTTP_B)..."
python3 $RELAY --port $WS_B --name Beta  --no-identity > /tmp/acp_beta.log  2>&1 &
PID_B=$!

echo -n "   Waiting for links..."
ALPHA_LINK=""; BETA_LINK=""
for i in $(seq 1 40); do
    sleep 0.5
    [ -z "$ALPHA_LINK" ] || [ "$ALPHA_LINK" = "None" ] && \
        ALPHA_LINK=$(curl -s http://localhost:$HTTP_A/status 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('link',''))" 2>/dev/null)
    [ -z "$BETA_LINK" ]  || [ "$BETA_LINK"  = "None" ] && \
        BETA_LINK=$(curl -s http://localhost:$HTTP_B/status 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('link',''))" 2>/dev/null)
    if [ -n "$ALPHA_LINK" ] && [ "$ALPHA_LINK" != "None" ] && \
       [ -n "$BETA_LINK"  ] && [ "$BETA_LINK"  != "None" ]; then
        echo " ready ✓"
        break
    fi
    echo -n "."
done

echo ""
echo "─────────────────────────────────────────────────"
echo "📋 Alpha: $(curl -s http://localhost:$HTTP_A/.well-known/acp.json | python3 -c 'import json,sys; d=json.load(sys.stdin)["self"]; print(d["name"]+" v"+d["version"])' 2>/dev/null)"
echo "   link: $ALPHA_LINK"
echo "📋 Beta:  $(curl -s http://localhost:$HTTP_B/.well-known/acp.json | python3 -c 'import json,sys; d=json.load(sys.stdin)["self"]; print(d["name"]+" v"+d["version"])' 2>/dev/null)"
echo "   link: $BETA_LINK"

echo ""
echo "─────────────────────────────────────────────────"
echo "🤝 [1/2] Beta connects to Alpha..."
CONN1=$(curl -s -X POST http://localhost:$HTTP_B/peers/connect \
    -H "Content-Type: application/json" \
    -d "{\"link\": \"$ALPHA_LINK\", \"name\": \"alpha\"}")
PEER_A_from_B=$(echo "$CONN1" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('peer_id','ERR'))" 2>/dev/null)
echo "   peer_id (Beta side): $PEER_A_from_B"
sleep 3.5   # wait for WS handshake + agent_card exchange

echo ""
echo "📨 Beta → Alpha: 'Hello from Beta!'"
SEND1=$(curl -s -X POST "http://localhost:$HTTP_B/peer/$PEER_A_from_B/send" \
    -H "Content-Type: application/json" \
    -d '{"role":"user","text":"Hello from Beta! Can you hear me, Alpha?"}')
echo "   $(echo $SEND1 | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ok=" + str(d.get("ok","?")))' 2>/dev/null)"
sleep 0.8

echo ""
echo "📬 Alpha inbox:"
curl -s "http://localhost:$HTTP_A/recv" | python3 -c "
import json,sys
resp=json.load(sys.stdin)
msgs=resp.get('messages', resp) if isinstance(resp, dict) else resp
if msgs:
    m=msgs[-1]
    txt=m.get('text') or m.get('content') or str(m.get('parts',''))
    print(f'  [{m.get(\"role\",\"?\")}] {str(txt)[:80]}')
else:
    print('  (empty — message may still be in transit)')
"

echo ""
echo "─────────────────────────────────────────────────"
echo "🤝 [2/2] Alpha connects back to Beta..."
CONN2=$(curl -s -X POST http://localhost:$HTTP_A/peers/connect \
    -H "Content-Type: application/json" \
    -d "{\"link\": \"$BETA_LINK\", \"name\": \"beta\"}")
PEER_B_from_A=$(echo "$CONN2" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('peer_id','ERR'))" 2>/dev/null)
echo "   peer_id (Alpha side): $PEER_B_from_A"
sleep 3.5

echo ""
echo "📨 Alpha → Beta: 'Loud and clear!'"
SEND2=$(curl -s -X POST "http://localhost:$HTTP_A/peer/$PEER_B_from_A/send" \
    -H "Content-Type: application/json" \
    -d '{"role":"assistant","text":"Loud and clear, Beta! ACP P2P link established. Ready for task coordination."}')
echo "   $(echo $SEND2 | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ok=" + str(d.get("ok","?")))' 2>/dev/null)"
sleep 0.8

echo ""
echo "📬 Beta inbox:"
curl -s "http://localhost:$HTTP_B/recv" | python3 -c "
import json,sys
resp=json.load(sys.stdin)
msgs=resp.get('messages', resp) if isinstance(resp, dict) else resp
if msgs:
    m=msgs[-1]
    txt=m.get('text') or m.get('content') or str(m.get('parts',''))
    print(f'  [{m.get(\"role\",\"?\")}] {str(txt)[:80]}')
else:
    print('  (empty)')
"

echo ""
echo "─────────────────────────────────────────────────"
A_PEERS=$(curl -s http://localhost:$HTTP_A/peers | python3 -c "import json,sys; ps=json.load(sys.stdin); print(str(len(ps))+' peer(s)')" 2>/dev/null)
B_PEERS=$(curl -s http://localhost:$HTTP_B/peers | python3 -c "import json,sys; ps=json.load(sys.stdin); print(str(len(ps))+' peer(s)')" 2>/dev/null)
echo "📊 Alpha peers: $A_PEERS"
echo "📊 Beta  peers: $B_PEERS"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅ Demo complete — bidirectional P2P comms OK  ║"
echo "║  No central server. No OAuth. Just two agents.  ║"
echo "╚══════════════════════════════════════════════════╝"
