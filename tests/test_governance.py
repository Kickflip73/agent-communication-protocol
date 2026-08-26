"""
test_governance.py — ACP v3.4.0 AgentCard.governance field tests.

GOV-01 ~ GOV-06: Verify the governance block in /status and POST /governance/policy.
Aligns with A2A #1717 CredentialLifecyclePolicy (scan35 P1).
"""
import pytest, json, time, os, socket, subprocess, urllib.request


@pytest.fixture(scope="module")
def relay_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        ws_port = s.getsockname()[1]
    http_port = ws_port + 100
    relay_dir = os.path.join(os.path.dirname(__file__), "..", "relay")
    relay_script = os.path.join(relay_dir, "acp_relay.py")
    cmd = ["python3", relay_script, "--port", str(ws_port), "--local-only"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{http_port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{url}/status", timeout=2)
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.terminate()
        pytest.skip(f"relay failed to start on {http_port}")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def _get(url, path):
    with urllib.request.urlopen(f"{url}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(url, path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"{url}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


# GOV-01: /status 包含 governance 字段
def test_gov01_status_has_governance(relay_url):
    s = _get(relay_url, "/status")
    assert "governance" in s, f"Expected 'governance' in /status, got keys: {list(s.keys())}"


# GOV-02: governance 包含必要子字段
def test_gov02_governance_fields(relay_url):
    g = _get(relay_url, "/status")["governance"]
    assert "framework" in g, "'framework' missing from governance"
    assert "credential_lifecycle" in g, "'credential_lifecycle' missing from governance"
    cl = g["credential_lifecycle"]
    assert "ttl_seconds" in cl, "'ttl_seconds' missing from credential_lifecycle"
    assert isinstance(cl["ttl_seconds"], int), f"ttl_seconds must be int, got {type(cl['ttl_seconds'])}"


# GOV-03: audit_mode 为有效值
def test_gov03_audit_mode(relay_url):
    g = _get(relay_url, "/status")["governance"]
    assert g.get("audit_mode") in ("static", "live"), \
        f"audit_mode must be 'static' or 'live', got: {g.get('audit_mode')!r}"


# GOV-04: capabilities.governance 为 bool
def test_gov04_capabilities_flag(relay_url):
    s = _get(relay_url, "/status")
    assert isinstance(s["capabilities"].get("governance"), bool), \
        f"capabilities.governance must be bool, got: {type(s['capabilities'].get('governance'))}"


# GOV-05: POST /governance/policy 返回治理对象
def test_gov05_policy_endpoint(relay_url):
    r = _post(relay_url, "/governance/policy")
    assert "framework" in r or "credential_lifecycle" in r, \
        f"POST /governance/policy must return governance object, got: {list(r.keys())}"


# GOV-06: governance.framework 包含 ACP 标识
def test_gov06_framework_identifier(relay_url):
    g = _get(relay_url, "/status")["governance"]
    assert "ACP" in str(g.get("framework", "")), \
        f"governance.framework must contain 'ACP', got: {g.get('framework')!r}"
