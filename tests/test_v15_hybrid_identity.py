"""
ACP v1.5 — CA certificate / hybrid identity tests
Uses /status endpoint (reliable agent_card access)
"""
import subprocess, time, requests, tempfile, os

BASE_PORT = 7885
HTTP_PORT = 7985

SAMPLE_PEM = """\
-----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2a2rwplBQLzHPZe5TNJF
FAKE_CERT_FOR_TESTING_ONLY_NOT_VALID_ACP_V15_TEST
-----END CERTIFICATE-----"""

def start_relay(*extra_args, port=BASE_PORT):
    cmd = ["python3",
           "/root/.openclaw/workspace/agent-communication-protocol/relay/acp_relay.py",
           "--name", f"TestV15p{port}", f"--port={port}"] + list(extra_args)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    hp = HTTP_PORT + (port - BASE_PORT)
    for _ in range(25):
        try:
            r = requests.get(f"http://localhost:{hp}/status", timeout=0.5)
            if r.status_code == 200:
                return proc, f"http://localhost:{hp}"
        except Exception:
            pass
        time.sleep(0.3)
    out, err = proc.stdout.read(), proc.stderr.read()
    proc.kill()
    raise RuntimeError(f"relay not ready on port {hp}\nOUT:{out[:300]}\nERR:{err[:300]}")

def get_card(base):
    return requests.get(f"{base}/status").json().get("agent_card", {}) or {}

def stop(proc):
    proc.terminate()
    try: proc.wait(timeout=3)
    except: proc.kill()

results = {}

# V1: --ca-cert without --identity → ignored
print("V1: --ca-cert without --identity...")
with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
    f.write(SAMPLE_PEM); cert_path = f.name
try:
    proc, base = start_relay("--ca-cert", cert_path, port=BASE_PORT)
    card = get_card(base)
    identity_block = card.get("identity")
    cap_identity = card.get("capabilities", {}).get("identity", "none")
    ok = (identity_block is None and cap_identity == "none")
    print(f"  identity=None, cap=none: {'✅' if ok else '❌'} (identity={identity_block}, cap={cap_identity})")
    results["V1_ca_cert_without_identity_ignored"] = ok
    stop(proc)
finally:
    os.unlink(cert_path)
time.sleep(0.5)

# V2: --identity without --ca-cert → scheme=ed25519
print("V2: --identity without --ca-cert → scheme=ed25519...")
proc, base = start_relay("--identity", f"/tmp/v15-id-{BASE_PORT+1}.json", port=BASE_PORT+1)
try:
    card = get_card(base)
    identity = card.get("identity") or {}
    scheme = identity.get("scheme", "MISSING")
    ca_cert = identity.get("ca_cert")
    cap = card.get("capabilities", {}).get("identity")
    ok = (scheme == "ed25519" and ca_cert is None and cap == "ed25519")
    print(f"  scheme=ed25519, no ca_cert: {'✅' if ok else '❌'} (scheme={scheme}, cap={cap})")
    results["V2_identity_only_ed25519"] = ok
finally:
    stop(proc)
time.sleep(0.5)

# V3: --identity + --ca-cert file → scheme=ed25519+ca
print("V3: --identity + --ca-cert (file)...")
with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
    f.write(SAMPLE_PEM); cert_path = f.name
try:
    proc, base = start_relay("--identity", f"/tmp/v15-id-{BASE_PORT+2}.json",
                              "--ca-cert", cert_path, port=BASE_PORT+2)
    card = get_card(base)
    identity = card.get("identity") or {}
    scheme = identity.get("scheme")
    ca_cert = identity.get("ca_cert")
    cap = card.get("capabilities", {}).get("identity")
    ok = (scheme == "ed25519+ca" and ca_cert is not None
          and "BEGIN CERTIFICATE" in ca_cert and cap == "ed25519+ca")
    print(f"  scheme=ed25519+ca, ca_cert present: {'✅' if ok else '❌'} (scheme={scheme}, cap={cap}, len={len(ca_cert or '')})")
    results["V3_hybrid_from_file"] = ok
    stop(proc)
finally:
    os.unlink(cert_path)
time.sleep(0.5)

# V4: --identity + --ca-cert inline PEM
print("V4: --identity + --ca-cert (inline PEM)...")
proc, base = start_relay("--identity", f"/tmp/v15-id-{BASE_PORT+3}.json",
                          "--ca-cert", SAMPLE_PEM, port=BASE_PORT+3)
try:
    card = get_card(base)
    identity = card.get("identity") or {}
    scheme = identity.get("scheme")
    ca_cert = identity.get("ca_cert")
    cap = card.get("capabilities", {}).get("identity")
    ok = (scheme == "ed25519+ca" and ca_cert is not None and cap == "ed25519+ca")
    print(f"  inline PEM hybrid: {'✅' if ok else '❌'} (scheme={scheme}, cap={cap})")
    results["V4_hybrid_inline_pem"] = ok
finally:
    stop(proc)
time.sleep(0.5)

# V5+V6: did and public_key preserved in hybrid mode
print("V5+V6: did + public_key preserved in hybrid...")
with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
    f.write(SAMPLE_PEM); cert_path = f.name
try:
    proc, base = start_relay("--identity", f"/tmp/v15-id-{BASE_PORT+4}.json",
                              "--ca-cert", cert_path, port=BASE_PORT+4)
    card = get_card(base)
    identity = card.get("identity") or {}
    did = identity.get("did")
    pubkey = identity.get("public_key")
    did_ok = did is not None and did.startswith("did:acp:")
    pk_ok  = pubkey is not None and len(pubkey) > 10
    print(f"  did preserved: {'✅' if did_ok else '❌'} ({(did or 'MISSING')[:35]}...)")
    print(f"  public_key preserved: {'✅' if pk_ok else '❌'}")
    results["V5_did_preserved_in_hybrid"] = did_ok
    results["V6_pubkey_preserved_in_hybrid"] = pk_ok
    stop(proc)
finally:
    os.unlink(cert_path)

# Summary
passed = sum(1 for v in results.values() if v)
total  = len(results)
print(f"\n{'='*50}")
print(f"ACP v1.5 CA cert: {passed}/{total} PASS")
for k, v in results.items():
    print(f"  {'✅' if v else '❌'} {k}")
