"""Bounded framed duplex channel. One poll does at most one read + write chunk."""

from collections import deque

from clo3d_mcp.protocol import Decoder, ProtocolError, encode
from clo3d_mcp.transport.winpipe import CHUNK_SIZE


class Channel:
    def __init__(self, pipe, session_id):
        self.pipe = pipe
        self.decoder = Decoder(session_id)
        self.outgoing = deque()
        self.read_op = None
        self.write_op = None
        self.offset = 0

    @property
    def drained(self):
        return not self.outgoing and self.write_op is None

    def send(self, message):
        if len(self.outgoing) >= 4:
            raise ProtocolError("Outbound frame limit reached")
        self.outgoing.append(encode(message))

    def poll(self):
        messages = []
        if self.read_op is None:
            self.read_op = self.pipe.read()
        data = self.read_op.poll()
        if data is not None:
            self.read_op = None
            if not data:
                self.decoder.eof()
                raise BrokenPipeError(109, "Pipe closed")
            messages = self.decoder.feed(data, max_messages=4)
        if self.write_op is None and self.outgoing:
            self.write_op = self.pipe.write(self.outgoing[0][self.offset:self.offset + CHUNK_SIZE])
        if self.write_op is not None:
            count = self.write_op.poll()
            if count is not None:
                if not 0 < count <= min(CHUNK_SIZE, len(self.outgoing[0]) - self.offset):
                    raise ProtocolError("Invalid write completion count")
                self.offset += count
                self.write_op = None
                if self.offset == len(self.outgoing[0]):
                    self.outgoing.popleft()
                    self.offset = 0
        return messages
