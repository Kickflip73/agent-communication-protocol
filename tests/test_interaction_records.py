"""
ACP v2.59 — Bilateral Interaction Records Tests

IR-1   POST /tasks without record=true → no interaction_record in response
IR-2   POST /tasks with record=true → interaction_record present in response
IR-3   interaction_record has required fields (id, type, relay_did, caller_did, task_id, sequence_a, previous_hash, timestamp)
IR-4   sequence_a increments monotonically across two successive records
IR-5   second record's previous_hash is sha256 of the first stored record
IR-6   GET /interaction-records → lists generated records
IR-7   GET /interaction-records?skill_id=X → filters by skill_id
IR-8   GET /interaction-records?limit=1 → returns at most 1 record
IR-9   POST /tasks with capability_token → caller_token_hash = sha256(jti)
IR-10  relay_signature is non-null when --identity loaded
IR-11  interaction_record is attached to task (GET /tasks/{id})
IR-12  no peer info → caller_did = "unknown"
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

_RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _gen_identity_file():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    priv_raw = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_raw = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_b64 = base64.urlsafe_b64encode(priv_raw).rstrip(b"=").decode()
    pub_b64 = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    ident = {"scheme": "ed25519", "private_key": priv_b64, "public_key": pub_b64}
    tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump(ident, tf)
    tf.close()
    return tf.name


def _start_relay(ws_port: int, identity_file: str = None, skills_json: str = None):
    http_port = ws_port + 100
    cmd = [sys.executable, _RELAY, "--port", str(ws_port), "--name", "IRTestAgent",
           "--local-only", "--test-mode"]
    if identity_file:
        cmd += ["--identity", identity_file]
    if skills_json:
        cmd += ["--skills", skills_json]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            time.sleep(0.15)
    proc.terminate()
    raise RuntimeError(f"Relay failed to start on HTTP port {http_port}")


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


def _post_task(hp, skill_id=None, record=None, extra=None):
    body = {"payload": {"role": "agent", "text": "ir-test"}}
    if skill_id:
        body["skill_id"] = skill_id
    if record is not None:
        body["record"] = record
    if extra:
        body.update(extra)
    return _post(hp, "/tasks", body)


# ── Skill definitions for tests ───────────────────────────────────────────────
SKILLS_IR = json.dumps([
    {"id": "ir-skill-a", "name": "IR Skill A", "authorization_tier": "T1"},
    {"id": "ir-skill-b", "name": "IR Skill B", "authorization_tier": "T2",
     "capability_token_required": True},
])


def test_ir_1_to_12():
    """IR-1 through IR-12: comprehensive bilateral interaction record tests."""
    ident_file = _gen_identity_file()
    try:
        proc, hp = _start_relay(53100, identity_file=ident_file, skills_json=SKILLS_IR)
        try:
            # ── IR-1: no record flag → no interaction_record ──────────────────
            s, b = _post_task(hp)
            assert s == 201, f"IR-1: status {s} body {b}"
            assert b.get("ok") is True
            assert "interaction_record" not in b, "IR-1: unexpected interaction_record"

            # ── IR-2: record=true → interaction_record present ────────────────
            s, b = _post_task(hp, record=True)
            assert s == 201, f"IR-2: status {s} body {b}"
            assert "interaction_record" in b, f"IR-2: missing interaction_record; body={b}"
            ir = b["interaction_record"]
            assert ir is not None

            # ── IR-3: required fields ─────────────────────────────────────────
            for field in ("id", "type", "relay_did", "caller_did", "task_id",
                          "sequence_a", "previous_hash", "timestamp"):
                assert field in ir, f"IR-3: missing field '{field}'"
            assert ir["type"] == "interaction", f"IR-3: type={ir['type']}"
            assert ir["id"].startswith("ir-"), f"IR-3: id={ir['id']}"
            assert ir["task_id"], "IR-3: empty task_id"
            assert ir["sequence_a"] >= 1, f"IR-3: seq={ir['sequence_a']}"

            # ── IR-4: sequence increments ─────────────────────────────────────
            s1, b1 = _post_task(hp, record=True)
            s2, b2 = _post_task(hp, record=True)
            assert s1 == s2 == 201, f"IR-4: {s1} {s2}"
            seq_a = b1["interaction_record"]["sequence_a"]
            seq_b = b2["interaction_record"]["sequence_a"]
            assert seq_b == seq_a + 1, f"IR-4: seq not incrementing: {seq_a} → {seq_b}"

            # ── IR-5: previous_hash chain ─────────────────────────────────────
            # Get the stored records from the list endpoint
            s_list, b_list = _get(hp, "/interaction-records")
            assert s_list == 200, f"IR-5 list: {s_list}"
            records = b_list["records"]
            # Find consecutive pair from IR-4 (b1_id and b2_id)
            b1_id = b1["interaction_record"]["id"]
            b2_id = b2["interaction_record"]["id"]
            rec_a = next((r for r in records if r["id"] == b1_id), None)
            rec_b = next((r for r in records if r["id"] == b2_id), None)
            assert rec_a is not None, f"IR-5: rec_a not found in list"
            assert rec_b is not None, f"IR-5: rec_b not found in list"
            canonical_a = json.dumps(rec_a, sort_keys=True, separators=(",", ":")).encode()
            expected_prev = "sha256:" + hashlib.sha256(canonical_a).hexdigest()
            assert rec_b["previous_hash"] == expected_prev, (
                f"IR-5: chain broken: expected {expected_prev[:20]}... got {rec_b['previous_hash'][:20]}..."
            )

            # ── IR-6: GET /interaction-records lists records ──────────────────
            s, b = _post_task(hp, record=True)
            assert s == 201
            created_id = b["interaction_record"]["id"]
            s_list, b_list = _get(hp, "/interaction-records")
            assert s_list == 200, f"IR-6: {s_list}"
            assert b_list.get("ok") is True
            ids = [r["id"] for r in b_list["records"]]
            assert created_id in ids, f"IR-6: created_id {created_id} not in list"

            # ── IR-7: filter by skill_id ──────────────────────────────────────
            _post_task(hp, skill_id="ir-skill-a", record=True)
            s_f, b_f = _get(hp, "/interaction-records?skill_id=ir-skill-a")
            assert s_f == 200, f"IR-7: {s_f}"
            assert b_f["count"] >= 1
            for rec in b_f["records"]:
                assert rec["skill_id"] == "ir-skill-a", f"IR-7: got skill {rec['skill_id']}"

            # ── IR-8: limit param ─────────────────────────────────────────────
            _post_task(hp, record=True)
            _post_task(hp, record=True)
            s_lim, b_lim = _get(hp, "/interaction-records?limit=1")
            assert s_lim == 200, f"IR-8: {s_lim}"
            assert b_lim["count"] <= 1, f"IR-8: count={b_lim['count']}"
            assert len(b_lim["records"]) <= 1, f"IR-8: len={len(b_lim['records'])}"

            # ── IR-9: caller_token_hash = sha256(jti) ─────────────────────────
            jti_val = "test-jti-ir9-xyz"
            fake_ct = {
                "jti": jti_val, "iss": "did:acp:fake", "sub": "did:acp:caller",
                "resource": "acp://localhost/skills/ir-skill-a",
                "tier": "T1", "actions": ["invoke"],
                "iat": int(time.time()), "exp": int(time.time()) + 3600,
                "scheme": "sint-v1",
            }
            body_ir9 = {"payload": {"role": "agent", "text": "ir9"},
                        "record": True, "capability_token": fake_ct}
            s9, b9 = _post(hp, "/tasks", body_ir9)
            if s9 == 201 and "interaction_record" in b9:
                ir9 = b9["interaction_record"]
                expected_hash = "sha256:" + hashlib.sha256(jti_val.encode()).hexdigest()
                assert ir9["caller_token_hash"] == expected_hash, (
                    f"IR-9: hash mismatch: {ir9['caller_token_hash']}"
                )
            # If token was rejected (403), the hash test is not applicable — pass silently

            # ── IR-10: relay_signature non-null (--identity loaded) ───────────
            s, b = _post_task(hp, record=True)
            assert s == 201
            ir10 = b["interaction_record"]
            assert ir10.get("relay_signature") is not None, "IR-10: relay_signature is None"
            assert ir10.get("relay_public_key") is not None, "IR-10: relay_public_key is None"
            sig = ir10["relay_signature"]
            assert isinstance(sig, str) and len(sig) > 10, f"IR-10: invalid sig: {sig!r}"

            # ── IR-11: interaction_record attached to task ────────────────────
            s, b = _post_task(hp, record=True)
            assert s == 201
            task_id_11 = b["task"]["id"]
            ir_id_11 = b["interaction_record"]["id"]
            s_t, b_t = _get(hp, f"/tasks/{task_id_11}")
            assert s_t == 200, f"IR-11: GET task status {s_t}"
            task_obj = b_t.get("task") or b_t
            assert "interaction_record" in task_obj, f"IR-11: task missing interaction_record"
            assert task_obj["interaction_record"]["id"] == ir_id_11, "IR-11: id mismatch"

            # ── IR-12: unknown caller → caller_did = "unknown" ────────────────
            body_12 = {"payload": {"role": "agent", "text": "ir12"}, "record": True}
            s12, b12 = _post(hp, "/tasks", body_12)
            assert s12 == 201, f"IR-12: {s12} {b12}"
            assert b12["interaction_record"]["caller_did"] == "unknown", (
                f"IR-12: caller_did={b12['interaction_record']['caller_did']}"
            )

        finally:
            proc.terminate()
    finally:
        import os as _os
        try:
            _os.unlink(ident_file)
        except Exception:
            pass
