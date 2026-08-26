"""
ACP v3.5 Extension Tests — V35-01 ~ V35-06

Tests for:
  - governance.proof_suite (P1: ANP eddsa-jcs-2022 interop, A2A #1717)
  - transport_bindings.experimental (P2: pre-SlimRPC extension point, #1723)
  - capabilities.transport_bindings flag
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


# V35-01: governance 包含 proof_suite
def test_v35_01_governance_proof_suite(relay_url):
    g = _get(relay_url, "/status")["governance"]
    assert "proof_suite" in g
    ps = g["proof_suite"]
    assert "supported" in ps
    assert isinstance(ps["supported"], list)
    assert len(ps["supported"]) > 0


# V35-02: proof_suite.default 为字符串
def test_v35_02_proof_suite_default(relay_url):
    ps = _get(relay_url, "/status")["governance"]["proof_suite"]
    assert isinstance(ps.get("default"), str)


# V35-03: proof_suite.interop_refs 为列表
def test_v35_03_proof_suite_interop_refs(relay_url):
    ps = _get(relay_url, "/status")["governance"]["proof_suite"]
    assert isinstance(ps.get("interop_refs"), list)


# V35-04: /status 包含 transport_bindings
def test_v35_04_transport_bindings_present(relay_url):
    s = _get(relay_url, "/status")
    assert "transport_bindings" in s


# V35-05: transport_bindings 包含 supported 和 experimental
def test_v35_05_transport_bindings_fields(relay_url):
    tb = _get(relay_url, "/status")["transport_bindings"]
    assert "supported" in tb
    assert "experimental" in tb
    assert isinstance(tb["supported"], list)
    assert isinstance(tb["experimental"], list)


# V35-06: capabilities.transport_bindings 为 bool
def test_v35_06_capabilities_transport_bindings(relay_url):
    s = _get(relay_url, "/status")
    assert isinstance(s["capabilities"].get("transport_bindings"), bool)
