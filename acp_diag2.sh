#!/bin/bash
echo "=== ACP 端口数据层诊断 v2 ==="
TARGET="33.229.113.196"

python3 - << PYEOF
import socket, time

target = "33.229.113.196"

# 详细测试 8080
print("── 8080 详细诊断 ──")
for path in ["/", "/health", "/acp/test"]:
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((target, 8080))
        req = f"GET {path} HTTP/1.1\r\nHost: {target}\r\nConnection: close\r\n\r\n"
        s.sendall(req.encode())
        time.sleep(2)
        try:
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk: break
                data += chunk
        except: pass
        if data:
            lines = data.split(b'\r\n')
            print(f"  GET {path} -> {lines[0].decode(errors='replace')}")
            for l in lines[1:6]:
                if l: print(f"    {l.decode(errors='replace')}")
        else:
            print(f"  GET {path} -> (empty)")
        s.close()
    except Exception as e:
        print(f"  GET {path} -> ❌ {e}")

# WebSocket 升级测试 8080
print("")
print("── 8080 WebSocket 测试 ──")
s = socket.socket()
s.settimeout(5)
try:
    s.connect((target, 8080))
    req = (
        "GET /acp/tok_c04abe90fafa4049 HTTP/1.1\r\n"
        f"Host: {target}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode())
    time.sleep(2)
    try:
        resp = s.recv(4096)
        first = resp.split(b'\r\n')[0].decode(errors='replace')
        print(f"  WS upgrade -> {first}")
        if b'101' in resp:
            print("  ✅ WebSocket 101 成功！")
    except socket.timeout:
        print("  ❌ WS 握手超时")
    s.close()
except Exception as e:
    print(f"  ❌ {e}")
PYEOF
