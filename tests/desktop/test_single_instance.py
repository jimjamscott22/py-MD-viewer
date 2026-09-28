"""Second launches hand their paths to the running instance."""

import uuid
from pathlib import Path

import pytest

from md_viewer_desktop.single_instance import (
    InstanceServer,
    decode_message,
    encode_message,
    send_to_running,
)


@pytest.fixture
def name():
    return f"md-viewer-test-{uuid.uuid4().hex[:8]}"


def test_message_round_trip(tmp_path):
    paths = [tmp_path / "a.md", tmp_path / "dir"]
    assert decode_message(encode_message(paths).strip()) == paths


@pytest.mark.parametrize("raw", [b"", b"nope", b"[]", b'{"paths": "x"}', b'{"paths": ["relative.md", 3]}', b"\xff"])
def test_malformed_messages_yield_nothing(raw):
    assert decode_message(raw) == []


def test_no_server_means_not_sent(qapp, name):
    assert send_to_running([Path("/tmp/x.md")], name) is False


def test_paths_reach_running_instance(qapp, name, tmp_path, helpers):
    server = InstanceServer(name)
    assert server.listen()
    received = []
    server.pathsReceived.connect(received.append)
    try:
        # The client blocks until the server replies, so the server's socket
        # has to be served by the event loop: run the send from a timer.
        from PyQt6.QtCore import QThread

        class Sender(QThread):
            ok = None

            def run(self):
                self.ok = send_to_running([tmp_path / "a.md"], name)

        sender = Sender()
        sender.start()
        assert helpers.wait_until(lambda: sender.isFinished())
        assert sender.ok is True
        assert received == [[tmp_path / "a.md"]]
    finally:
        server.close()


def test_stale_socket_is_replaced(qapp, name):
    first = InstanceServer(name)
    assert first.listen()
    # Simulate a crashed instance: the name is taken but nobody will answer.
    second = InstanceServer(name)
    try:
        assert second.listen()
    finally:
        first.close()
        second.close()
