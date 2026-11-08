"""Pure wire contract tests; no CLO imports or Windows handles."""

import json
import struct

import pytest

from clo3d_mcp.protocol import Decoder, MAX_CHUNK, MAX_PAYLOAD, ProtocolError, encode, message, validate


def frame(payload):
    return struct.pack("<I", len(payload)) + payload


def test_fragmentation_at_every_boundary_and_unicode():
    value = message("RESULT", "session", job_id="job", result={"ткань": "日本語😀"})
    data = encode(value)
    for split in range(len(data) + 1):
        decoder = Decoder("session")
        assert decoder.feed(data[:split]) + decoder.feed(data[split:]) == [value]
        decoder.eof()
    decoder = Decoder()
    results = []
    for byte in data:
        results.extend(decoder.feed(bytes([byte])))
    assert results == [value]


def test_coalesced_and_partial_following_header():
    value = message("READY", "session")
    data = encode(value)
    decoder = Decoder()
    assert decoder.feed(data + data + data[:2]) == [value, value]
    assert decoder.feed(data[2:]) == [value]


@pytest.mark.parametrize("length", [0, MAX_PAYLOAD + 1, 0xFFFFFFFF])
def test_invalid_length_poison_decoder(length):
    decoder = Decoder()
    with pytest.raises(ProtocolError):
        decoder.feed(struct.pack("<I", length))
    assert decoder.failed and not decoder.buffer
    with pytest.raises(ProtocolError):
        decoder.feed(encode(message("READY", "session")))


@pytest.mark.parametrize("payload", [b"\xff", b"[]", b"null", b"{", b'{"kind":"READY","kind":"STOP"}',
                                     b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b"[" * 1500])
def test_invalid_json_and_types(payload):
    with pytest.raises(ProtocolError):
        Decoder().feed(frame(payload))


@pytest.mark.parametrize("change", [
    {"protocol_version": True}, {"protocol_version": 2}, {"session_id": ""},
    {"session_id": []}, {"kind": []}, {"extra": "secret"},
])
def test_schema_rejects_invalid_fields(change):
    value = dict(kind="READY", session_id="session", protocol_version=1)
    value.update(change)
    with pytest.raises(ProtocolError):
        validate(value)


def test_stale_session_and_eof_mid_frame():
    data = encode(message("READY", "old"))
    with pytest.raises(ProtocolError):
        Decoder("new").feed(data)
    for count in (1, 3, 4, len(data) - 1):
        decoder = Decoder()
        decoder.feed(data[:count])
        with pytest.raises(ProtocolError):
            decoder.eof()


def test_input_chunk_and_payload_limits():
    with pytest.raises(ProtocolError):
        Decoder().feed(b"x" * (MAX_CHUNK + 1))
    with pytest.raises(ProtocolError):
        encode(message("RESULT", "s", job_id="j", result={"x": "y" * MAX_PAYLOAD}))
    data = encode(message("RESULT", "s", job_id="j", result={"x": "y" * (MAX_PAYLOAD - 150)}))
    decoder = Decoder()
    output = []
    for offset in range(0, len(data), MAX_CHUNK):
        output.extend(decoder.feed(data[offset:offset + MAX_CHUNK]))
        assert len(decoder.buffer) <= MAX_PAYLOAD
    assert len(output) == 1


@pytest.mark.parametrize("result", [{"x": float("nan")}, {"x": object()}, {"x": "\ud800"}])
def test_encoding_rejects_non_json(result):
    with pytest.raises(ProtocolError):
        encode(message("RESULT", "s", job_id="j", result=result))


@pytest.mark.parametrize("fields", [
    {"command": "exec", "params": {}}, {"command": [], "params": {}},
    {"command": "ping", "params": []}, {"command": "ping", "params": {"x": 1}},
])
def test_only_whitelisted_parameterless_jobs(fields):
    with pytest.raises(ProtocolError):
        message("JOB", "s", job_id="job", **fields)
