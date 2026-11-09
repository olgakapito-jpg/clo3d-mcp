"""Version 1 diagnostic wire contract. Stdlib only; no execution or file IPC."""

import json
import math
import re
import struct

from clo3d_mcp.pattern_contract import PATTERN_COMMANDS, ERROR_CODES, CommandError, validate_params


VERSION = 1
MAX_PAYLOAD = 1024 * 1024
MAX_CHUNK = 64 * 1024
CAPABILITIES = ["ping", "get_pattern_count"]
SERVICE_CAPABILITIES = CAPABILITIES + ["create_test_rectangle"]
PATTERN_CAPABILITIES = SERVICE_CAPABILITIES + PATTERN_COMMANDS
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
KINDS = {
    "HELLO": {"pid", "proof", "capabilities", "build"},
    "HELLO_ACK": {"pid", "proof", "capabilities"},
    "READY": set(),
    "JOB": {"job_id", "command", "params"},
    "RESULT": {"job_id", "result"},
    "ERROR": {"job_id", "code"},
    "STOP": set(),
    "SERVICE_READY": set(),
}


class ProtocolError(ValueError):
    """Intentionally excludes peer payloads/credentials from error messages."""


def validate(message, session_id=None):
    if not isinstance(message, dict):
        raise ProtocolError("Message must be an object")
    kind = message.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ProtocolError("Unknown message kind")
    if set(message) != {"kind", "protocol_version", "session_id"} | KINDS[kind]:
        raise ProtocolError("Invalid message fields")
    if type(message["protocol_version"]) is not int or message["protocol_version"] != VERSION:
        raise ProtocolError("Unsupported protocol version")
    sid = message["session_id"]
    if not isinstance(sid, str) or not IDENTIFIER.fullmatch(sid):
        raise ProtocolError("Invalid session identifier")
    if session_id is not None and sid != session_id:
        raise ProtocolError("Stale or foreign session")
    if "job_id" in message:
        job_id = message["job_id"]
        if not isinstance(job_id, str) or not IDENTIFIER.fullmatch(job_id):
            raise ProtocolError("Invalid job identifier")
    if kind in ("HELLO", "HELLO_ACK"):
        if message["capabilities"] not in (CAPABILITIES, SERVICE_CAPABILITIES, PATTERN_CAPABILITIES):
            raise ProtocolError("Unsupported diagnostic capabilities")
        if type(message["pid"]) is not int or not 0 < message["pid"] <= 0xFFFFFFFF:
            raise ProtocolError("Invalid peer PID")
        if not isinstance(message["proof"], str) or not re.fullmatch(r"[a-f0-9]{64}", message["proof"]):
            raise ProtocolError("Invalid authentication proof")
    if kind == "JOB":
        if not isinstance(message["command"], str) or message["command"] not in PATTERN_CAPABILITIES:
            raise ProtocolError("Command is not allowed")
        if message["command"] in PATTERN_COMMANDS:
            try:
                validate_params(message["command"], message["params"])
            except CommandError:
                raise ProtocolError("Invalid command parameters") from None
        elif message["params"] != {}:
            raise ProtocolError("Diagnostic commands accept no parameters")
    if kind == "RESULT" and not isinstance(message["result"], dict):
        raise ProtocolError("Result must be an object")
    if kind == "ERROR" and message["code"] not in ("command_error", "duplicate_job") + ERROR_CODES:
        raise ProtocolError("Invalid command error code")
    return message


def message(kind, session_id, **fields):
    return validate(dict(kind=kind, session_id=session_id, protocol_version=VERSION, **fields))


def encode(message):
    validate(message)
    try:
        payload = json.dumps(message, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProtocolError("Message is not finite UTF-8 JSON") from None
    if not 0 < len(payload) <= MAX_PAYLOAD:
        raise ProtocolError("Frame exceeds payload limit")
    return struct.pack("<I", len(payload)) + payload


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(_):
    raise ProtocolError("Non-finite JSON number")


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ProtocolError("Non-finite JSON number")
    return number


class Decoder:
    """One partial frame, at most one bounded I/O chunk of completed messages.

    Callers must drain returned messages each tick; this object has no queue.
    A protocol failure poisons the decoder until the connection is replaced.
    """

    def __init__(self, session_id=None):
        self.session_id = session_id
        self.buffer = bytearray()
        self.expected = None
        self.failed = False

    def feed(self, data, max_messages=None):
        if self.failed:
            raise ProtocolError("Decoder requires a new connection")
        if not isinstance(data, bytes) or len(data) > MAX_CHUNK:
            self.failed = True
            raise ProtocolError("Invalid input chunk")
        self.buffer.extend(data)
        messages = []
        try:
            while True:
                if self.expected is None:
                    if len(self.buffer) < 4:
                        break
                    self.expected = struct.unpack_from("<I", self.buffer)[0]
                    del self.buffer[:4]
                    if not 0 < self.expected <= MAX_PAYLOAD:
                        raise ProtocolError("Invalid frame length")
                if len(self.buffer) < self.expected:
                    break
                payload = bytes(self.buffer[:self.expected])
                del self.buffer[:self.expected]
                self.expected = None
                decoded = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                                     parse_constant=_constant, parse_float=_float)
                messages.append(validate(decoded, self.session_id))
                if max_messages is not None and len(messages) > max_messages:
                    raise ProtocolError("Inbound message limit reached")
            return messages
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self.failed = True
            self.buffer.clear()
            raise ProtocolError("Invalid frame or message") from None

    def eof(self):
        if self.failed or self.buffer or self.expected is not None:
            self.failed = True
            raise ProtocolError("Connection ended with incomplete frame")
