---
name: windows-named-pipe
description: Implement or review Python Windows Named Pipe transport, ctypes ABI declarations, message framing, overlapped I/O, access control and resource cleanup.
---

# Python Windows Named Pipe transport

Read `AGENTS.md` and P1 of `docs/PYTHON_TRANSPORT_PLAN.md` from repository root.
Load `clo-python-runtime` as well if touching CLO callbacks.

## Design constraints

- External MCP owns the pipe server; CLO connects as client. Commands and
  results remain bidirectional. Follow the agreed plan unless it is revised.
- No files for requests, results, discovery, queue or heartbeat.
- Pure-Python/stdlib transport modules imported in CLO must not import MCP.
- UI-side I/O is an explicit nonblocking state machine; background Python
  scheduling inside CLO is not assumed reliable.

## Win32 correctness checklist

1. Verify each used function in Microsoft documentation; declare argtypes,
   restype and pointer-width types. Use WinDLL with use_last_error=True and
   read the error immediately. Never truncate HANDLEs to 32-bit integers.
2. Distinguish INVALID_HANDLE_VALUE from NULL. Handle expected statuses such
   as ERROR_IO_PENDING, ERROR_PIPE_CONNECTED and broken pipe deliberately.
3. Keep the OVERLAPPED structure, event and data buffer alive until the
   operation has completed. Track how many bytes actually transferred.
4. Support partial reads/writes and backpressure. Never assume one ReadFile
   equals one complete JSON frame. Avoid busy-wait loops and UI-thread waits.
5. Cancel pending operations on stop and observe completion before freeing
   buffers/closing events. CancelIoEx alone is not completion acknowledgement.
6. Use an explicit DACL for the current user and reject remote pipe clients.
   An obscure pipe name is not access control. Verify peer/session identity.
7. Use a fresh session identity and random session credential passed in memory
   to the child process. Do not log or embed that credential in source files.

## Protocol

- Four-byte unsigned little-endian byte length, then JSON encoded as UTF-8.
- Initially limit payloads to 1 MiB; reject oversized/invalid frames before
  allocating arbitrarily large buffers. No pickle or remote code execution.
- Require a JSON object and validate field types, protocol_version, session_id,
  job_id and message kind before dispatch. A valid JSON list is not a request.
- Define HELLO/handshake, READY, JOB, RESULT, ERROR and STOP semantics. Distinguish
  transport receipt from execution completion; an ACK is not an operation result.
- Pair replies by job/session IDs; reject stale sessions and unknown IDs.
- Keep bounded receive buffers and result caches. Specify disconnect behavior
  for partially sent frames and unknown command outcomes.

## Required evidence

Test codec independently; then two real Windows endpoints without CLO; finally
the same exchange against CLO. Cover fragmented/coalesced messages, Unicode,
invalid JSON/length/types, abrupt disconnect mid-frame, pending I/O shutdown,
slow readers, authentication failure, reconnect and handle cleanup.

Use events and bounded waits in tests, not arbitrary long sleeps. Report mocked
Win32 tests separately from tests that actually opened a Windows pipe.

## Primary references

- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipes
- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/fileio/synchronous-and-asynchronous-i-o
- https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex
