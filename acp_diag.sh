#!/bin/bash
# ACP P2P 连接诊断脚本
# 目标：33.229.113.196  端口：9223  路径：/acp/TOKEN
# 运行方式：bash acp_diag.sh

TARGET_IP="33.229.113.196"
TARGET_PORT="9223"
TOKEN="tok_c04abe90fafa4049"

echo "=========================================="
echo "ACP P2P 连接诊断"
echo "目标: $TARGET_IP:$TARGET_PORT"
echo "时间: $(date)"
echo "=========================================="
echo ""

# ── 1. 基础网络 ──────────────────────────────
echo "【1】基础网络"
echo -n "  ping $TARGET_IP ... "
if ping -c 1 -W 2 "$TARGET_IP" &>/dev/null; then
    echo "✅ 通"
else
    echo "❌ 不通（可能被 ICMP 过滤，不影响 TCP）"
fi

# ── 2. TCP 连接 ──────────────────────────────
echo ""
echo "【2】TCP 连接测试 (port $TARGET_PORT)"
python3 - << 'PYEOF'
import socket, sys
TARGET_IP = "33.229.113.196"
TARGET_PORT = 9223
s = socket.socket()
s.settimeout(5)
try:
    s.connect((TARGET_IP, TARGET_PORT))
    print(f"  ✅ TCP 连接成功 ({TARGET_IP}:{TARGET_PORT})")
    s.close()
except Exception as e:
    print(f"  ❌ TCP 连接失败: {e}")
    sys.exit(1)
PYEOF

# ── 3. HTTP 数据层 ───────────────────────────
echo ""
echo "【3】HTTP 数据层测试（TCP 通了，数据能过来吗？）"
python3 - << 'PYEOF'
import socket, time, sys
TARGET_IP = "33.229.113.196"
TARGET_PORT = 9223
s = socket.socket()
s.settimeout(5)
try:
    s.connect((TARGET_IP, TARGET_PORT))
    s.sendall(b"GET / HTTP/1.1\r\nHost: 33.229.113.196\r\nConnection: close\r\n\r\n")
    time.sleep(2)
    try:
        data = s.recv(4096)
        if data:
            first_line = data.split(b'\r\n')[0].decode(errors='replace')
            print(f"  ✅ 收到 HTTP 响应: {first_line}")
        else:
            print("  ⚠️  连接建立但收到空响应（服务可能不回应非WS请求）")
    except socket.timeout:
        print("  ❌ HTTP 数据层超时——TCP通但HTTP数据被拦截（NetworkPolicy?）")
        sys.exit(2)
    s.close()
except Exception as e:
    print(f"  ❌ 失败: {e}")
    sys.exit(1)
PYEOF

# ── 4. WebSocket 握手 ────────────────────────
echo ""
echo "【4】WebSocket 握手测试（/acp/TOKEN）"
python3 - << PYEOF
import socket, time, sys
TARGET_IP = "33.229.113.196"
TARGET_PORT = 9223
TOKEN = "tok_c04abe90fafa4049"

s = socket.socket()
s.settimeout(8)
try:
    s.connect((TARGET_IP, TARGET_PORT))
    req = (
        f"GET /acp/{TOKEN} HTTP/1.1\r\n"
        f"Host: {TARGET_IP}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    s.sendall(req.encode())
    try:
        resp = s.recv(4096)
        first_line = resp.split(b'\r\n')[0].decode(errors='replace')
        if b'101' in resp:
            print(f"  ✅ WebSocket 握手成功: {first_line}")
            time.sleep(0.5)
            try:
                frame = s.recv(4096)
                if frame:
                    payload = frame[2:] if len(frame) > 2 else b''
                    print(f"  ✅ 收到 WS 数据帧 ({len(frame)} bytes): {payload[:80]}")
                else:
                    print("  ⚠️  WS 握手成功但无后续数据")
            except:
                print("  ✅ WS 握手成功（读帧超时，正常）")
        elif b'301' in resp or b'302' in resp or b'Location' in resp:
            print(f"  ⚠️  收到重定向响应:")
            print(f"  {resp[:300].decode(errors='replace')}")
            sys.exit(3)
        else:
            print(f"  ❌ WS 握手失败，响应: {first_line}")
            print(f"  完整响应: {resp[:300].decode(errors='replace')}")
            sys.exit(3)
    except socket.timeout:
        print("  ❌ WebSocket 握手超时——TCP通、HTTP数据层需检查")
        sys.exit(4)
    s.close()
except Exception as e:
    print(f"  ❌ 失败: {e}")
    sys.exit(1)
PYEOF

# ── 5. websockets 库版本 ─────────────────────
echo ""
echo "【5】本机 websockets 库"
python3 -c "
import websockets, inspect, sys
print(f'  websockets 版本: {websockets.__version__}')
has_proxy = 'proxy' in inspect.signature(websockets.connect).parameters
print(f'  支持 proxy= 参数: {has_proxy}')
print(f'  Python 版本: {sys.version.split()[0]}')
" 2>/dev/null || echo "  ❌ websockets 未安装"

# ── 6. 本机出口 IP ───────────────────────────
echo ""
echo "【6】本机出口 IP"
python3 -c "
import urllib.request
try:
    with urllib.request.urlopen('https://api.ipify.org', timeout=5) as r:
        print(f'  出口 IP: {r.read().decode()}')
except Exception as e:
    print(f'  无法获取: {e}')
"

# ── 7. 代理环境 ──────────────────────────────
echo ""
echo "【7】代理环境变量"
found=0
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    val="${!var}"
    if [ -n "$val" ]; then
        echo "  $var = $val"
        found=1
    fi
done
[ $found -eq 0 ] && echo "  (无代理环境变量)"

echo ""
echo "=========================================="
echo "诊断完成"
echo "=========================================="
