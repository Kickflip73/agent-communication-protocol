#!/usr/bin/env python3
"""T1: STUNClient 基础测试"""
import asyncio
import sys
import struct as _struct
sys.path.insert(0, '/root/.openclaw/workspace/agent-communication-protocol/relay')

from acp_relay import STUNClient

print("=" * 60)
print("T1: STUNClient 基础测试")
print("=" * 60)

async def test_stun():
    results = {}
    
    # T1.1: 正常调用 Google STUN（网络不可达时应返回 None 不报异常）
    print("\n[T1.1] 调用 get_public_address (stun.l.google.com:19302)")
    try:
        result = await STUNClient.get_public_address('stun.l.google.com', 19302, timeout=4.0)
        if result is None:
            print("  ✅ 返回 None（网络不可达，正确降级，无异常）")
            results['t1_1'] = True
        elif isinstance(result, tuple) and len(result) == 2:
            ip, port = result
            print(f"  ✅ 返回 ({ip}, {port}) — 格式正确")
            assert isinstance(ip, str), "IP 应为 str"
            assert isinstance(port, int), "port 应为 int"
            assert 1 <= port <= 65535, f"port 超出范围: {port}"
            results['t1_1'] = True
        else:
            print(f"  ❌ 返回类型异常: {type(result)} = {result}")
            results['t1_1'] = False
    except Exception as e:
        print(f"  ❌ 抛出异常（不应该）: {type(e).__name__}: {e}")
        results['t1_1'] = False

    # T1.2: 无效 STUN 主机（应返回 None 不报异常）
    print("\n[T1.2] 调用 get_public_address (无效主机:19302)")
    try:
        result = await STUNClient.get_public_address('invalid.nonexistent.stun.host.xyz', 19302, timeout=2.0)
        if result is None:
            print("  ✅ 无效主机返回 None（正确，无异常）")
            results['t1_2'] = True
        else:
            print(f"  ❌ 无效主机竟返回了: {result}")
            results['t1_2'] = False
    except Exception as e:
        print(f"  ❌ 抛出异常（不应该）: {type(e).__name__}: {e}")
        results['t1_2'] = False

    # T1.3: 超短超时（应返回 None 不报异常）
    print("\n[T1.3] 调用 get_public_address（超短超时 0.1s）")
    try:
        result = await STUNClient.get_public_address('stun.l.google.com', 19302, timeout=0.1)
        if result is None:
            print("  ✅ 超时返回 None（正确）")
            results['t1_3'] = True
        elif isinstance(result, tuple):
            print(f"  ✅ 意外快速成功: {result}（也可接受）")
            results['t1_3'] = True
        else:
            print(f"  ❌ 意外返回值: {result}")
            results['t1_3'] = False
    except Exception as e:
        print(f"  ❌ 抛出异常（不应该）: {type(e).__name__}: {e}")
        results['t1_3'] = False

    # T1.4: _parse_response 单元测试（不依赖网络）
    print("\n[T1.4] _parse_response 解析测试（纯解析，无网络）")
    try:
        magic = STUNClient.MAGIC_COOKIE  # 0x2112A442
        txn = b'\x00' * 12
        # XOR-MAPPED-ADDRESS attr: type=0x0020, len=8
        port_raw = 4242 ^ (magic >> 16)
        ip_int = (1 << 24) | (2 << 16) | (3 << 8) | 4
        xip_int = ip_int ^ magic
        attr_val = _struct.pack("!BBHI", 0x00, 0x01, port_raw, xip_int)
        attr = _struct.pack("!HH", 0x0020, 8) + attr_val
        msg_len = len(attr)
        header = _struct.pack("!HHI12s", 0x0101, msg_len, magic, txn)
        test_data = header + attr

        result = STUNClient._parse_response(test_data)
        if result == ("1.2.3.4", 4242):
            print(f"  ✅ _parse_response 正确解析 XOR-MAPPED-ADDRESS: {result}")
            results['t1_4'] = True
        else:
            print(f"  ❌ 解析结果错误: {result}，期望 ('1.2.3.4', 4242)")
            results['t1_4'] = False
    except Exception as e:
        print(f"  ❌ 异常: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        results['t1_4'] = False

    # T1.5: _parse_response 空数据
    print("\n[T1.5] _parse_response 空/短数据测试")
    try:
        r1 = STUNClient._parse_response(b"")
        r2 = STUNClient._parse_response(b"\x00" * 10)
        if r1 is None and r2 is None:
            print(f"  ✅ 空/短数据正确返回 None")
            results['t1_5'] = True
        else:
            print(f"  ❌ 应返回 None，得 r1={r1}, r2={r2}")
            results['t1_5'] = False
    except Exception as e:
        print(f"  ❌ 异常: {type(e).__name__}: {e}")
        results['t1_5'] = False

    # T1.6: MAPPED-ADDRESS fallback（没有 XOR 时）
    print("\n[T1.6] _parse_response 解析 MAPPED-ADDRESS fallback")
    try:
        magic = STUNClient.MAGIC_COOKIE
        txn = b'\x00' * 12
        # MAPPED-ADDRESS attr: type=0x0001, len=8
        # family=0x01, port=5000, ip=192.168.1.100
        port_raw = 5000
        ip_raw = b'\xc0\xa8\x01\x64'  # 192.168.1.100
        attr_val = bytes([0x00, 0x01]) + _struct.pack("!H", port_raw) + ip_raw
        attr = _struct.pack("!HH", 0x0001, 8) + attr_val
        msg_len = len(attr)
        header = _struct.pack("!HHI12s", 0x0101, msg_len, magic, txn)
        test_data = header + attr

        result = STUNClient._parse_response(test_data)
        if result == ("192.168.1.100", 5000):
            print(f"  ✅ MAPPED-ADDRESS 解析正确: {result}")
            results['t1_6'] = True
        else:
            print(f"  ❌ 解析结果错误: {result}，期望 ('192.168.1.100', 5000)")
            results['t1_6'] = False
    except Exception as e:
        print(f"  ❌ 异常: {type(e).__name__}: {e}")
        results['t1_6'] = False

    total = sum(results.values())
    print(f"\n[T1 Summary] {total}/{len(results)} 通过")
    return results

if __name__ == "__main__":
    r = asyncio.run(test_stun())
    passed = sum(r.values())
    total = len(r)
    print(f"\nT1 Result: {'PASS' if passed == total else 'FAIL'} ({passed}/{total})")
    sys.exit(0 if passed == total else 1)
