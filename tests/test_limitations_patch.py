"""
Tests for v2.21: limitations PATCH support + filter_limitations query param.

LP1:  PATCH /card with limitations[] (replace mode)
LP2:  PATCH /card with limitations[] (merge mode — limitations_merge=true)
LP3:  PATCH /card with limitations[] string backward-compat (auto-promoted)
LP4:  PATCH /card with limitations[] invalid kind → 400
LP5:  PATCH /card with limitations=non-array → 400
LP6:  PATCH /card body has neither availability nor limitations → 400
LP7:  PATCH /card with both availability and limitations → both updated
LP8:  GET /.well-known/acp.json?filter_limitations=permanent → only permanent entries
LP9:  GET /.well-known/acp.json?filter_limitations=transient → only transient entries
LP10: GET /.well-known/acp.json?filter_limitations=capability → only capability kind
LP11: GET /.well-known/acp.json?filter_limitations=<invalid> → 400
LP12: capabilities.limitations_patch=true in AgentCard
LP13: capabilities.limitations_filter=true in AgentCard
"""
import os, sys, time, json, signal, subprocess, urllib.request, urllib.parse

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

# ─── fixture helpers ──────────────────────────────────────────────────────────

_proc = None
_ws_port = 19700
_http_port = 19800


def _start():
    global _proc
    _proc = subprocess.Popen(
        [sys.executable, RELAY,
         "--port", str(_ws_port),
         "--name", "LP-Agent",
         "--limitations-json",
         '[{"kind":"capability","code":"no_video","message":"No video support","permanent":true},'
         ' {"kind":"scale","code":"small_only","message":"Max 10 agents","permanent":false}]'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(4)


def _stop():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.send_signal(signal.SIGTERM)
        try: _proc.wait(timeout=5)
        except: _proc.kill()
    _proc = None


def setup_module(_):
    _start()


def teardown_module(_):
    _stop()


def _get(path):
    url = f"http://127.0.0.1:{_http_port}{path}"
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read())


def _patch(body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{_http_port}/card",
        data=data,
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _card():
    _, data = _get("/.well-known/acp.json")
    return data.get("self", data)


# ─── tests ────────────────────────────────────────────────────────────────────

class TestLimitationsPatch:

    def setup_method(self, _method):
        """Reset limitations to known baseline before each test."""
        _patch({"limitations": [
            {"kind": "capability", "code": "no_video", "message": "No video support", "permanent": True},
            {"kind": "scale", "code": "small_only", "message": "Max 10 agents", "permanent": False},
        ]})

    def test_LP1_patch_replace(self):
        """LP1: PATCH limitations[] replace mode (default)."""
        status, data = _patch({
            "limitations": [
                {"kind": "domain", "code": "no_finance", "message": "Finance excluded", "permanent": True}
            ]
        })
        assert status == 200, f"Expected 200, got {status}: {data}"
        assert data.get("ok") is True
        assert "limitations" in data.get("updated", [])
        lims = data.get("limitations", [])
        assert len(lims) == 1
        assert lims[0]["kind"] == "domain"
        assert lims[0]["code"] == "no_finance"

    def test_LP2_patch_merge(self):
        """LP2: PATCH limitations[] with limitations_merge=true — appends, deduplicates by (kind, code)."""
        # First set a baseline
        _patch({"limitations": [
            {"kind": "capability", "code": "no_video", "message": "No video", "permanent": True}
        ]})
        # Merge a new entry
        status, data = _patch({
            "limitations": [
                {"kind": "scale", "code": "small_only", "message": "Max 5 agents", "permanent": False}
            ],
            "limitations_merge": True
        })
        assert status == 200
        lims = data.get("limitations", [])
        codes = {lim["code"] for lim in lims}
        assert "no_video" in codes, f"no_video should be retained after merge: {lims}"
        assert "small_only" in codes, f"small_only should be added after merge: {lims}"

    def test_LP3_patch_string_backward_compat(self):
        """LP3: PATCH limitations[] with plain strings — auto-promoted to LimitationObject."""
        status, data = _patch({"limitations": ["rate limited", "no gpu"]})
        assert status == 200
        lims = data.get("limitations", [])
        assert len(lims) == 2
        for lim in lims:
            # _parse_limitation promotes strings to kind="capability" (design choice)
            assert lim.get("kind") in ("capability", "other")
            assert isinstance(lim.get("message"), str)
            assert isinstance(lim.get("code"), str)

    def test_LP4_patch_invalid_kind(self):
        """LP4: PATCH limitations[] with invalid kind → 400."""
        status, data = _patch({"limitations": [
            {"kind": "INVALID_KIND", "code": "x", "message": "bad"}
        ]})
        assert status == 400, f"Expected 400, got {status}: {data}"

    def test_LP5_patch_non_array(self):
        """LP5: PATCH limitations=non-array → 400."""
        status, data = _patch({"limitations": "should be array"})
        assert status == 400

    def test_LP6_patch_empty_body(self):
        """LP6: PATCH body has neither availability nor limitations → 400."""
        status, data = _patch({"unrelated_key": "value"})
        assert status == 400

    def test_LP7_patch_both_fields(self):
        """LP7: PATCH with both availability and limitations → both updated."""
        status, data = _patch({
            "availability": {"mode": "heartbeat"},
            "limitations": [
                {"kind": "access", "code": "auth_required", "message": "Auth needed", "permanent": True}
            ]
        })
        assert status == 200
        updated = data.get("updated", [])
        assert "availability" in updated
        assert "limitations" in updated
        assert data.get("availability", {}).get("mode") == "heartbeat"
        assert any(lim["code"] == "auth_required" for lim in data.get("limitations", []))

    def test_LP8_filter_permanent(self):
        """LP8: GET ?filter_limitations=permanent → only permanent=true entries."""
        # Set a known state
        _patch({"limitations": [
            {"kind": "capability", "code": "no_video", "message": "perm", "permanent": True},
            {"kind": "scale", "code": "tmp", "message": "transient", "permanent": False},
        ]})
        _, data = _get("/.well-known/acp.json?filter_limitations=permanent")
        card = data.get("self", data)
        lims = card.get("limitations", [])
        assert all(lim.get("permanent") is True for lim in lims), f"Non-permanent found: {lims}"
        assert any(lim["code"] == "no_video" for lim in lims)
        assert not any(lim["code"] == "tmp" for lim in lims)

    def test_LP9_filter_transient(self):
        """LP9: GET ?filter_limitations=transient → only permanent!=true entries."""
        _patch({"limitations": [
            {"kind": "capability", "code": "no_video", "message": "perm", "permanent": True},
            {"kind": "scale", "code": "tmp", "message": "transient", "permanent": False},
        ]})
        _, data = _get("/.well-known/acp.json?filter_limitations=transient")
        card = data.get("self", data)
        lims = card.get("limitations", [])
        assert all(lim.get("permanent") is not True for lim in lims), f"Permanent found: {lims}"
        assert any(lim["code"] == "tmp" for lim in lims)
        assert not any(lim["code"] == "no_video" for lim in lims)

    def test_LP10_filter_by_kind(self):
        """LP10: GET ?filter_limitations=capability → only capability kind."""
        _patch({"limitations": [
            {"kind": "capability", "code": "no_video", "message": "perm", "permanent": True},
            {"kind": "scale", "code": "tmp", "message": "scale issue", "permanent": False},
            {"kind": "domain", "code": "no_finance", "message": "domain", "permanent": True},
        ]})
        _, data = _get("/.well-known/acp.json?filter_limitations=capability")
        card = data.get("self", data)
        lims = card.get("limitations", [])
        assert all(lim.get("kind") == "capability" for lim in lims), f"Non-capability found: {lims}"
        assert any(lim["code"] == "no_video" for lim in lims)

    def test_LP11_filter_invalid_value(self):
        """LP11: GET ?filter_limitations=<invalid> → 400."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{_http_port}/.well-known/acp.json?filter_limitations=NOTVALID",
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                status = r.status
        except urllib.error.HTTPError as e:
            status = e.code
        assert status == 400

    def test_LP12_capability_limitations_patch(self):
        """LP12: capabilities.limitations_patch=true declared in AgentCard."""
        card = _card()
        caps = card.get("capabilities", {})
        assert caps.get("limitations_patch") is True, f"capabilities.limitations_patch not set: {caps}"

    def test_LP13_capability_limitations_filter(self):
        """LP13: capabilities.limitations_filter=true declared in AgentCard."""
        card = _card()
        caps = card.get("capabilities", {})
        assert caps.get("limitations_filter") is True, f"capabilities.limitations_filter not set: {caps}"
