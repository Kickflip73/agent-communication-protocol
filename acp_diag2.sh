#!/bin/bash
echo "=== ACP 端口数据层诊断 ==="
TARGET="33.229.113.196"

python3 - << PYEOF
import socket, time

target = "33.229.113.196"
ports = [7681, 8080, 18789, 6080, 7820, 9223]

for port in ports:
    s = socket.socket()
    s.settimeout(4)
    try:
        s.connect((target, port))
        # 发一个 HTTP 请求
        s.sendall(b"GET / HTTP/1.1\r\nHost: " + target.encode() + b"\r\nConnection: close\r\n\r\n")
        time.sleep(1.5)
        try:
            data = s.recv(512)
            first = data.split(b'\r\n')[0].decode(errors='replace') if data else '(empty)'
            print(f"  {port}: ✅ DATA  <- {first[:60]}")
        except socket.timeout:
            print(f"  {port}: ❌ TCP ok but DATA TIMEOUT")
        s.close()
    except ConnectionRefusedError:
        print(f"  {port}: ❌ Connection refused")
    except Exception as e:
        print(f"  {port}: ❌ {e}")
PYEOF
