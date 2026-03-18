FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn aiohttp

COPY ../sdk/python/acp_sdk ./acp_sdk
COPY server.py .

EXPOSE 8765

HEALTHCHECK --interval=10s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/acp/v1/health')"

CMD ["python", "server.py"]
