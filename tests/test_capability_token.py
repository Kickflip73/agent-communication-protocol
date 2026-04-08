"""
ACP v2.57 — capability_token: SINT-format Ed25519 signed capability tokens

Test suite: CT-1..12
  CT-1   POST /skills/{id}/capability-token — no identity → 403 ERR_IDENTITY_REQUIRED
  CT-2   POST /skills/{id}/capability-token — unknown skill → 404 ERR_SKILL_NOT_FOUND
  CT-3   POST /skills/{id}/capability-token — valid issuance (with identity)
  CT-4   Response token has required SINT fields
  CT-5   GET /capability-tokens — lists issued tokens
  CT-6   GET /capability-tokens?active=1 — non-expired tokens only
  CT-7   GET /capability-tokens?skill_id=X — filter by skill
  CT-8   capabilities.capability_token_issuance: True when --identity loaded
  CT-9   POST /tasks with valid capability_token — accepted (200/201)
  CT-10  POST /tasks with tampered capability_token — 403 ERR_CAPABILITY_TOKEN_INVALID
  CT-11  POST /tasks for capability_token_required skill, no token → 403 ERR_CAPABILITY_TOKEN_REQUIRED
  CT-12  POST /tasks for capability_token_required skill, with valid token → accepted
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import tempfile

_RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _gen_identity_file():
    """Generate a temp Ed25519 identity JSON in the exact format acp_relay.py expects."""
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
    priv = Ed25519PrivateKey.generate()
    pub  = priv.public_key()
    priv_raw = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_raw  = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_b64 = base64.urlsafe_b64encode(priv_raw).rstrip(b"=").decode()
    pub_b64  = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    ident = {"scheme": "ed25519", "private_key": priv_b64, "public_key": pub_b64}
    tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump(ident, tf)
    tf.close()
    return tf.name


def _start_relay(ws_port: int, skills_json: str = None, identity_file: str = None, no_identity: bool = False):
    http_port = ws_port + 100
    cmd = [sys.executable, _RELAY, "--port", str(ws_port), "--name", "CTTestAgent",
           "--local-only", "--test-mode"]
    if skills_json:
        cmd += ["--skills", skills_json]   # --skills accepts JSON array string
    if identity_file:
        cmd += ["--identity", identity_file]
    elif no_identity:
        cmd += ["--no-identity"]  # v2.85 escape hatch: disable Ed25519 default-on
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            time.sleep(0.15)
    proc.terminate()
    raise RuntimeError(f"Relay failed on HTTP port {http_port}")


def _get(hp, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(hp, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


SKILLS_WITH_CT = json.dumps([
    {"id": "read_balance",   "name": "Read Balance",   "authorization_tier": "T1",
     "capability_token_required": False},
    {"id": "transfer_funds", "name": "Transfer Funds",  "authorization_tier": "T3",
     "capability_token_required": True,
     "human_confirmation_required": False},
])


def test_ct_1_to_12():
    # CT-1..2: relay WITHOUT identity (no --identity flag)
    proc_noid, hp_noid = _start_relay(52800, no_identity=True)
    try:
        # CT-1: no identity → 403
        s, b = _post(hp_noid, "/skills/read_balance/capability-token",
                     {"subject": "did:acp:Caller"})
        assert s == 403, f"CT-1 status: {s}"
        assert b.get("error_code") == "ERR_IDENTITY_REQUIRED", f"CT-1 code: {b}"

        # CT-2: unknown skill → 404 (relay has no skills configured)
        # Need identity for this; skip — covered separately in CT-3/CT-4 block
    finally:
        proc_noid.terminate()

    # CT-3..12: relay WITH identity
    ident_file = _gen_identity_file()
    try:
        proc_id, hp_id = _start_relay(52850, skills_json=SKILLS_WITH_CT, identity_file=ident_file)
        try:
            # CT-2b: unknown skill (this relay has skills, but "ghost_skill" is not in it)
            s, b = _post(hp_id, "/skills/ghost_skill/capability-token",
                         {"subject": "did:acp:Caller"})
            assert s == 404, f"CT-2b status: {s}"
            assert b.get("error_code") == "ERR_SKILL_NOT_FOUND", f"CT-2b code: {b}"

            # CT-3: valid issuance
            s, b = _post(hp_id, "/skills/read_balance/capability-token", {
                "subject": "did:acp:CallerAgent",
                "tier":    "T1",
                "ttl":     60,
            })
            assert s == 200,               f"CT-3 status: {s}"
            assert b.get("ok") is True,    f"CT-3 ok: {b}"
            assert "token" in b,           f"CT-3 token key: {b}"
            tok = b["token"]

            # CT-4: required SINT fields present
            for field in ("jti", "iss", "sub", "resource", "actions", "tier",
                          "iat", "exp", "signature", "scheme", "public_key"):
                assert field in tok, f"CT-4 missing field {field}: {tok}"
            assert tok["sub"]    == "did:acp:CallerAgent", f"CT-4 sub: {tok}"
            assert tok["tier"]   == "T1",                  f"CT-4 tier: {tok}"
            assert tok["scheme"] == "sint_ed25519",        f"CT-4 scheme: {tok}"
            assert "read_balance" in tok["resource"],       f"CT-4 resource: {tok}"
            assert tok["exp"] > tok["iat"],                f"CT-4 exp > iat: {tok}"

            # CT-5: GET /capability-tokens lists issued token
            s, b = _get(hp_id, "/capability-tokens")
            assert s == 200,                  f"CT-5 status: {s}"
            assert b.get("ok") is True,       f"CT-5 ok: {b}"
            assert b.get("count") >= 1,       f"CT-5 count: {b}"
            jti_val = tok["jti"]
            jtis = [t["jti"] for t in b.get("tokens", [])]
            assert jti_val in jtis,            f"CT-5 jti in list: {jtis}"

            # CT-6: GET /capability-tokens?active=1 — non-expired only
            s, b = _get(hp_id, "/capability-tokens?active=1")
            assert s == 200,            f"CT-6 status: {s}"
            for t in b.get("tokens", []):
                assert not t.get("expired"), f"CT-6 expired token in active list: {t}"

            # CT-7: GET /capability-tokens?skill_id=read_balance
            s, b = _get(hp_id, "/capability-tokens?skill_id=read_balance")
            assert s == 200,            f"CT-7 status: {s}"
            for t in b.get("tokens", []):
                assert t.get("skill_id") == "read_balance", f"CT-7 skill filter: {t}"

            # CT-8: capabilities.capability_token_issuance = True
            s, b = _get(hp_id, "/.well-known/acp.json")
            assert s == 200,            f"CT-8 status: {s}"
            card = b.get("self") or b
            caps = card.get("capabilities", {})
            assert caps.get("capability_token_issuance") is True, f"CT-8 cap: {caps}"

            # CT-9: POST /tasks with valid capability_token → accepted
            # Issue a token for read_balance
            s_tok, b_tok = _post(hp_id, "/skills/read_balance/capability-token", {
                "subject": "did:acp:TaskCaller",
                "tier":    "T1",
                "ttl":     3600,
            })
            assert s_tok == 200, f"CT-9 token issue: {s_tok}"
            valid_tok = b_tok["token"]

            s, b = _post(hp_id, "/tasks", {
                "role":             "agent",
                "parts":            [{"kind": "text", "text": "check balance"}],
                "skill_id":         "read_balance",
                "capability_token": valid_tok,
            })
            assert s in (200, 201), f"CT-9 task status: {s} body={b}"

            # CT-10: POST /tasks with tampered token → 403
            tampered = dict(valid_tok)
            tampered["sub"] = "did:acp:HACKER"  # tamper sub without re-signing
            s, b = _post(hp_id, "/tasks", {
                "role":             "agent",
                "parts":            [{"kind": "text", "text": "tampered"}],
                "skill_id":         "read_balance",
                "capability_token": tampered,
            })
            assert s == 403, f"CT-10 status: {s}"
            assert b.get("error_code") == "ERR_CAPABILITY_TOKEN_INVALID", f"CT-10 code: {b}"

            # CT-11: POST /tasks for capability_token_required skill, no token → 403
            s, b = _post(hp_id, "/tasks", {
                "role":     "agent",
                "parts":    [{"kind": "text", "text": "transfer 100"}],
                "skill_id": "transfer_funds",
            })
            assert s == 403, f"CT-11 status: {s}"
            assert b.get("error_code") == "ERR_CAPABILITY_TOKEN_REQUIRED", f"CT-11 code: {b}"

            # CT-12: POST /tasks for capability_token_required skill, with valid token → accepted
            s_tok2, b_tok2 = _post(hp_id, "/skills/transfer_funds/capability-token", {
                "subject": "did:acp:AuthorizedAgent",
                "tier":    "T3",
                "ttl":     300,
            })
            assert s_tok2 == 200, f"CT-12 token issue: {s_tok2} {b_tok2}"
            tok_t3 = b_tok2["token"]

            s, b = _post(hp_id, "/tasks", {
                "role":             "agent",
                "parts":            [{"kind": "text", "text": "transfer 100 USD"}],
                "skill_id":         "transfer_funds",
                "capability_token": tok_t3,
            })
            assert s in (200, 201), f"CT-12 task status: {s} body={b}"

        finally:
            proc_id.terminate()
    finally:
        os.unlink(ident_file)
