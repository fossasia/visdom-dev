# Copyright 2017-present, The Visdom Authors
import http.server
import json
import shutil
import ssl
import subprocess
import threading

import pytest

from app.admin import activity

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="needs openssl")


def _self_signed(directory, name, days):
    cert, key = directory / f"{name}.crt", directory / f"{name}.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", str(days),
            "-subj", "/CN=visdom-internal", "-keyout", str(key), "-out", str(cert),
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


class _Activity(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"workspaces": [{"workspace_id": "ws-a", "viewers": 1}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def instance(tmp_path, monkeypatch):
    cert, key = _self_signed(tmp_path, "internal", days=1)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Activity)
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_PORT", server.server_address[1])
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_CA", str(cert))
    yield tmp_path
    server.shutdown()
    server.server_close()


def test_an_instance_with_the_pinned_certificate_is_read(instance):
    assert activity._ask("127.0.0.1:8097", 2.0) == (True, [{"workspace_id": "ws-a", "viewers": 1}])


def test_an_instance_with_any_other_certificate_is_refused(instance, monkeypatch):
    other, _key = _self_signed(instance, "other", days=1)
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_CA", str(other))

    assert activity._ask("127.0.0.1:8097", 2.0) == (False, [])


def test_the_days_left_on_the_certificate_are_read(instance):
    days = activity.certificate_days_left("127.0.0.1:8097", 2.0)

    assert 0 < days <= 1
