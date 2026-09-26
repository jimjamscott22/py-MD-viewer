"""One running window per user: later launches hand their paths over.

The first ``md-viewer`` listens on a ``QLocalServer`` (a Unix socket on
Linux). A second ``md-viewer foo.md`` connects, sends one JSON line
(``{"paths": [...]}`` with absolute paths), waits for an ``ok`` line and
exits; the running window opens the paths in tabs and raises itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

CONNECT_TIMEOUT_MS = 500
REPLY_TIMEOUT_MS = 3000
MAX_MESSAGE_BYTES = 1 << 20


def server_name() -> str:
    uid = os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
    return f"jamielab-md-viewer-{uid}"


def encode_message(paths: list[Path]) -> bytes:
    return (json.dumps({"paths": [str(p.expanduser().absolute()) for p in paths]}) + "\n").encode()


def decode_message(data: bytes) -> list[Path]:
    """Parse a request line; anything malformed yields no paths."""
    try:
        message = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(message, dict) or not isinstance(message.get("paths"), list):
        return []
    return [Path(p) for p in message["paths"] if isinstance(p, str) and os.path.isabs(p)]


def send_to_running(paths: list[Path], name: str | None = None) -> bool:
    """Hand ``paths`` to a running instance. ``False`` if none answered."""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    socket.write(encode_message(paths))
    socket.flush()
    ok = socket.waitForBytesWritten(REPLY_TIMEOUT_MS) or socket.bytesToWrite() == 0
    if ok:
        # The reply may already be buffered; only block when it isn't.
        while not socket.canReadLine() and socket.waitForReadyRead(REPLY_TIMEOUT_MS):
            pass
        ok = bytes(socket.readLine()).strip() == b"ok"
    socket.disconnectFromServer()
    return ok


class InstanceServer(QObject):
    """Listens for later launches and emits the paths they send."""

    pathsReceived = pyqtSignal(list)  # list[Path]; empty → just raise the window

    def __init__(self, name: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.name = name or server_name()
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._on_connection)
        self._buffers: dict[QLocalSocket, bytearray] = {}

    def listen(self) -> bool:
        if self._server.listen(self.name):
            return True
        # Nobody answered send_to_running(), so the socket is stale (a crash).
        QLocalServer.removeServer(self.name)
        return self._server.listen(self.name)

    def close(self) -> None:
        self._server.close()

    def _on_connection(self) -> None:
        while (socket := self._server.nextPendingConnection()) is not None:
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._on_ready_read(s))
            socket.disconnected.connect(lambda s=socket: self._drop(s))

    def _on_ready_read(self, socket: QLocalSocket) -> None:
        buffer = self._buffers.get(socket)
        if buffer is None:
            return
        buffer += bytes(socket.readAll())
        if len(buffer) > MAX_MESSAGE_BYTES:
            socket.abort()
            return
        if b"\n" not in buffer:
            return
        line = bytes(buffer.split(b"\n", 1)[0])
        socket.write(b"ok\n")
        socket.flush()
        self._buffers[socket] = bytearray()
        self.pathsReceived.emit(decode_message(line))

    def _drop(self, socket: QLocalSocket) -> None:
        self._buffers.pop(socket, None)
        socket.deleteLater()
