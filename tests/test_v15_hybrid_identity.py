"""
ACP v1.5 CA certificate / hybrid identity tests.

These tests intentionally start real relay subprocesses so they exercise the
same command-line path users run. Keep all process startup inside test
functions so pytest collection stays portable and side-effect free.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests


RELAY_PATH = Path(__file__).resolve().parents[1] / "relay" / "acp_relay.py"

SAMPLE_PEM = """\
-----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2a2rwplBQLzHPZe5TNJF
FAKE_CERT_FOR_TESTING_ONLY_NOT_VALID_ACP_V15_TEST
-----END CERTIFICATE-----"""


def _free_port_pair() -> tuple[int, int]:
    """Return a free relay port pair where the HTTP port is WS + 100."""
    for _ in range(200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ws_sock:
            ws_sock.bind(("127.0.0.1", 0))
            ws_port = ws_sock.getsockname()[1]

        http_port = ws_port + 100
        if http_port > 65535:
            continue

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as http_sock:
                http_sock.bind(("127.0.0.1", http_port))
            return ws_port, http_port
        except OSError:
            continue

    raise RuntimeError("Could not find a free port pair (ws + 100)")


def _start_relay(*extra_args: str, identity_path: Path | None = None) -> tuple[subprocess.Popen, str]:
    ws_port, http_port = _free_port_pair()
    cmd = [
        sys.executable,
        str(RELAY_PATH),
        "--name",
        f"TestV15p{ws_port}",
        f"--port={ws_port}",
        f"--http-port={http_port}",
        "--http-host",
        "127.0.0.1",
        "--local-only",
        "--test-mode",
    ]
    if identity_path is not None:
        cmd.extend(["--identity", str(identity_path)])
    cmd.extend(extra_args)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{http_port}"
    for _ in range(35):
        try:
            response = requests.get(f"{base}/status", timeout=0.5)
            if response.status_code == 200:
                return proc, base
        except requests.RequestException:
            pass
        time.sleep(0.2)

    proc.kill()
    out, err = proc.communicate(timeout=2)
    raise RuntimeError(
        f"relay not ready on port {http_port}\n"
        f"OUT:{out[:300]!r}\nERR:{err[:300]!r}"
    )


def _get_card(base: str) -> dict:
    return requests.get(f"{base}/status", timeout=3).json().get("agent_card", {}) or {}


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_ca_cert_without_identity_is_ignored() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as cert_file:
        cert_file.write(SAMPLE_PEM)
        cert_path = Path(cert_file.name)

    try:
        proc, base = _start_relay("--ca-cert", str(cert_path), "--no-identity")
        try:
            card = _get_card(base)
            assert card.get("identity") is None
            assert card.get("capabilities", {}).get("identity", "none") == "none"
        finally:
            _stop(proc)
    finally:
        os.unlink(cert_path)


def test_identity_without_ca_cert_uses_ed25519(tmp_path: Path) -> None:
    proc, base = _start_relay(identity_path=tmp_path / "identity.json")
    try:
        card = _get_card(base)
        identity = card.get("identity") or {}
        assert identity.get("scheme") == "ed25519"
        assert identity.get("ca_cert") is None
        assert card.get("capabilities", {}).get("identity") == "ed25519"
    finally:
        _stop(proc)


def test_identity_with_ca_cert_file_uses_hybrid_scheme(tmp_path: Path) -> None:
    cert_path = tmp_path / "test-ca.pem"
    cert_path.write_text(SAMPLE_PEM, encoding="utf-8")

    proc, base = _start_relay(
        "--ca-cert",
        str(cert_path),
        identity_path=tmp_path / "identity.json",
    )
    try:
        card = _get_card(base)
        identity = card.get("identity") or {}
        assert identity.get("scheme") == "ed25519+ca"
        assert "BEGIN CERTIFICATE" in identity.get("ca_cert", "")
        assert card.get("capabilities", {}).get("identity") == "ed25519+ca"
    finally:
        _stop(proc)


def test_identity_with_inline_ca_cert_uses_hybrid_scheme(tmp_path: Path) -> None:
    proc, base = _start_relay(
        "--ca-cert",
        SAMPLE_PEM,
        identity_path=tmp_path / "identity.json",
    )
    try:
        card = _get_card(base)
        identity = card.get("identity") or {}
        assert identity.get("scheme") == "ed25519+ca"
        assert identity.get("ca_cert")
        assert card.get("capabilities", {}).get("identity") == "ed25519+ca"
    finally:
        _stop(proc)


def test_hybrid_identity_preserves_did_and_public_key(tmp_path: Path) -> None:
    cert_path = tmp_path / "test-ca.pem"
    cert_path.write_text(SAMPLE_PEM, encoding="utf-8")

    proc, base = _start_relay(
        "--ca-cert",
        str(cert_path),
        identity_path=tmp_path / "identity.json",
    )
    try:
        identity = _get_card(base).get("identity") or {}
        assert identity.get("did", "").startswith("did:acp:")
        assert len(identity.get("public_key", "")) > 10
    finally:
        _stop(proc)
