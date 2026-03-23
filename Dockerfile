# ── ACP Relay — Official Docker Image ────────────────────────────────────────
# Single-file relay: zero-dependency fast path (no websockets) works out of
# the box; install optional deps for full feature set (see below).
#
# Build:
#   docker build -t acp-relay .                              # base: websockets only
#   docker build --build-arg EXTRAS=full -t acp-relay:full . # full: + cryptography (Ed25519)
#
# Run (basic — P2P, HTTP fallback, no signing):
#   docker run --rm -p 8000:8000 -p 8100:8100 acp-relay --name MyAgent
#
# Run (HMAC signing + replay-window):
#   docker run --rm -p 8000:8000 -p 8100:8100 acp-relay \
#     --name MyAgent --secret mysecret --hmac-window 120
#
# Run (heartbeat/cron mode):
#   docker run --rm -p 8000:8000 -p 8100:8100 acp-relay \
#     --name HourlyAgent --availability-mode cron --heartbeat-interval 3600
#
# Run (Ed25519 identity — persistent keypair via volume):
#   docker run --rm -p 8000:8000 -p 8100:8100 \
#     -v acp-identity:/root/.acp \
#     acp-relay:full --name MyAgent --identity
#
# Run (v1.3 Extension + DID identity):
#   docker run --rm -p 8000:8000 -p 8100:8100 \
#     -v acp-identity:/root/.acp \
#     acp-relay:full --name MyAgent --identity \
#     --extension-uri https://example.com/ext/my-capability/v1
#
# Health check:
#   curl http://localhost:8100/.well-known/acp.json
#
# Pull from GHCR (after CI publish):
#   docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay:latest
#   docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay:full
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# Build arg: "base" = websockets only (default), "full" = websockets + cryptography
ARG EXTRAS=base

LABEL org.opencontainers.image.title="ACP Relay" \
      org.opencontainers.image.description="ACP P2P Agent Communication Protocol relay" \
      org.opencontainers.image.version="1.3.0" \
      org.opencontainers.image.source="https://github.com/Kickflip73/agent-communication-protocol" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Copy relay (single file — no build step needed)
COPY relay/acp_relay.py /app/acp_relay.py

# websockets is required for all variants; cryptography is optional (Ed25519 identity)
# base = websockets only, full = websockets + cryptography
RUN pip install --no-cache-dir websockets \
    && if [ "$EXTRAS" = "full" ]; then \
         pip install --no-cache-dir cryptography; \
       fi \
    && chmod +x /app/acp_relay.py

# WS port + HTTP port (HTTP = WS + 100; default WS=8000 → HTTP=8100)
EXPOSE 8000 8100

# Healthcheck via AgentCard endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/.well-known/acp.json', timeout=4)" || exit 1

# Default: listen on all interfaces inside the container
# --http-host 0.0.0.0 is required so Docker port mapping (-p 8100:8100) works;
# the HTTP server must bind 0.0.0.0 inside the container, not 127.0.0.1.
# Pass any acp_relay.py flags after the image name to override defaults.
ENTRYPOINT ["python3", "/app/acp_relay.py"]
CMD ["--name", "ACP-Agent", "--port", "8000", "--http-host", "0.0.0.0"]
