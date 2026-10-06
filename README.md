# PBS_LINK: Python Reference SDK for the PBS Envelope

[![tests](https://github.com/Pale-Blue-Systems/PBS_LINK/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Pale-Blue-Systems/PBS_LINK/actions/workflows/tests.yml?query=branch%3Amain)
![Version](https://img.shields.io/badge/version-v0.1.2-blue)
![Status](https://img.shields.io/badge/status-Beta-orange)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

PBS_LINK is the Python reference implementation of the PBS-ENV-01 v1.3 message envelope of the Pale Blue Systems (PBS) Open Standard ([PBS-PROTOCOL-OPEN](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN)). It builds and parses envelopes, optionally frames them with COBS, and writes them to a serial port object.

| Item | Value |
|------|-------|
| Version | 0.1.2 (Beta) |
| pip distribution name | `pbs-link` |
| Import package | `PBS_LINK` |
| Implements | PBS-ENV-01 v1.3 |
| Python | 3.8 or later |
| Dependencies | Python standard library only |

`pbs-link` is the name pip uses for the distribution. Python code imports `PBS_LINK`: `from PBS_LINK import PBSLink`. `import pbs_link` raises `ModuleNotFoundError`.

PBS_LINK is an endpoint library. It does not schedule, store, retransmit or forward envelopes; [DOCS/INTEGRATION.md](DOCS/INTEGRATION.md) allocates those functions to a gateway.

---

## Context

The Pale Blue Systems Foundation publishes PBS_LINK for planned architectures in which space agencies, commercial operators, science missions and private systems share off-Earth communication infrastructure. No current operational failure motivates it. It provides a published envelope implementation for experimentation, integration and interoperability testing before connectivity conventions are fixed. [WHY-NOW.md](WHY-NOW.md) gives the rationale for publishing now.

---

## Features

- **Envelope:** PBS-ENV-01 v1.3 fixed 44-byte big-endian header followed by the payload.
- **Header integrity:** IEEE 802.3 CRC-32 over all 44 header bytes with the CRC field (0x28–0x2B) set to zero. The CRC does not cover the payload.
- **Loss detection:** 16-bit sequence number per `PBSLink` instance, incremented on each `send()` under a lock; wraps from 65535 to 0.
- **Priority:** classes 0 (CRITICAL) to 4 (BULK) of PBS-PRIO-01. `send()` rejects other values; `parse()` rejects 5–255 by default.
- **Lifetime:** TTL in seconds (u32); 0 means the envelope never expires. `parse(check_ttl=True)` rejects expired envelopes.
- **Timestamp:** Unix microseconds from `time.time()` or a caller-supplied clock.
- **Validation:** `parse()` checks length, Magic, CRC-32, priority, payload length and, optionally, TTL. Magic, CRC-32, priority and TTL failures raise `PBSMagicError`, `PBSCRCError`, `PBSPriorityError` and `PBSTTLError`; length failures raise their base class, `PBSValidationError`.
- **Framing:** optional COBS framing (`use_framing=True`) with a 0x00 frame delimiter for byte-stream links.
- **Resynchronization:** `find_sync()` locates the next header with a valid CRC-32 in an unframed byte stream.
- **Dependencies:** none outside the Python standard library.

[DOCS/INTEGRATION.md §3.4](DOCS/INTEGRATION.md#34-limitations-of-pbs_link-012) lists the limitations of 0.1.2, including the per-instance sequence counter. Version 0.1.2 corrects a COBS encoder defect present in 0.1.1 (see [CHANGELOG.md](CHANGELOG.md)).

---

## Installation

PBS_LINK is not published on PyPI. Install from source:

```bash
git clone https://github.com/Pale-Blue-Systems/PBS_LINK.git
cd PBS_LINK
pip install .
```

---

## Quick Start

With `serial_port=None`, `send()` returns the envelope bytes instead of writing them.

### 1. Critical Alert (Priority 0)

```python
from PBS_LINK import PBSLink, Priority, parse_envelope

link = PBSLink(device_id="Rover-Alpha", serial_port=None)

# CRITICAL, never expires (TTL 0), acknowledgement requested (Flags 0x01).
alert = link.send(priority=Priority.CRITICAL, payload="ERR: WHEEL_MOTOR_STALL", ttl=0, require_ack=True)

env = parse_envelope(alert)
print(env.source_id, env.priority_name, env.sequence, env.ack_requested, len(alert))
# Rover-Alpha CRITICAL 1 True 66
```

PBS_LINK does not buffer or reorder envelopes. Forwarding order is a gateway function: PBS-PRIO-01 §6 states that higher-priority envelopes SHOULD be forwarded before lower-priority envelopes. `require_ack=True` sets the flag only; PBS_LINK does not wait for an acknowledgement.

### 2. Bulk Science Data (Priority 4)

```python
# BULK: PBS-ENV-01 §12.1 requires a gateway to discard it once more than 60 s have elapsed since its Timestamp.
telemetry = link.send(priority=Priority.BULK, payload="Temp: -40C, Rad: 12mSv", ttl=60)
```

Under sustained congestion a gateway MAY delay or drop lower-priority envelopes (PBS-PRIO-01 §6). TTL expiry (PBS-ENV-01 §12.2) bounds how long stale data occupies gateway storage.

### 3. Writing to a Serial Port

```python
import io

port = io.BytesIO()  # stands in for serial.Serial("/dev/ttyS0", 115200)
link = PBSLink(device_id="Rover-Alpha", serial_port=port)

written = link.send(Priority.NORMAL, "Battery: 98%", ttl=60)
assert written == 44 + 12  # header + payload bytes
```

`serial_port` accepts any object with a `write(bytes)` method, such as a pySerial `serial.Serial`. `send()` then returns the number of bytes written.

### 4. Detecting Header Corruption

```python
from PBS_LINK import PBSCRCError

damaged = bytearray(alert)
damaged[0x01] ^= 0x01  # one bit flipped in the Priority byte
try:
    link.parse(bytes(damaged))
except PBSCRCError as exc:
    print("discarded:", exc)
```

---

## Run the Tests

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install . pytest
pytest -q TESTS
python EXAMPLES/rover_alert.py
python TESTS/doc_examples.py README.md DOCS/INTEGRATION.md DOCS/SPECIFICATIONS.md
```

`pytest -q TESTS` runs the 55 tests in `TESTS/test_torture.py`. `TESTS/doc_examples.py` executes every Python block in the listed documents. The [tests workflow](.github/workflows/tests.yml) runs the same steps on Python 3.8, 3.9, 3.10, 3.11 and 3.12 for every push and pull request.

---

## System Context

1. **Application.** Calls `PBSLink.send()`, which builds the PBS-ENV-01 envelope.
2. **Link.** PBS_LINK writes the envelope to `serial_port`. The physical link (UART, RS-422, USB) is outside the SDK.

No PBS gateway implementation is published. The PBS specifications assign these functions to a gateway:

3. **Validation, scheduling and storage.** Validate each envelope (PBS-ENV-01 §14), forward by priority (PBS-PRIO-01 §6), store through link outages (PBS-PRIO-01 §7) and discard expired envelopes (PBS-ENV-01 §12).
4. **DTN boundary.** Encapsulate each envelope in a Bundle Protocol Version 7 bundle ([RFC 9171](https://www.rfc-editor.org/rfc/rfc9171)) as specified by PBS-DTN-MAP-01 or PBS-DTN-MAP-02.

---

## Documentation

- **[DOCS/INTEGRATION.md](DOCS/INTEGRATION.md):** SDK behavior and limitations, application patterns, and the gateway requirements of PBS-ENV-01, PBS-PRIO-01, PBS-CONFORMANCE-01, PBS-DTN-MAP-01 and PBS-DTN-MAP-02.
- **[DOCS/SPECIFICATIONS.md](DOCS/SPECIFICATIONS.md):** header byte layout, CRC-32 parameters and a test vector.
- **[WHY-NOW.md](WHY-NOW.md):** rationale for publishing now.

---

## The Standard (PBS-ENV-01 v1.3)

All multi-byte fields are big-endian.

| Offset | Field | Type | Content |
|------:|------|------|-------------|
| 0x00 | Magic | `u8` | `0x10` |
| 0x01 | Priority | `u8` | `0` CRITICAL … `4` BULK |
| 0x02 | Flags | `u8` | `0x01` = ACK requested |
| 0x03 | Reserved | `u8` | `0x00` |
| 0x04 | Sequence | `u16` | Counter, 0–65535 |
| 0x06 | Reserved | `u16` | `0x0000` |
| 0x08 | Source ID | `char[16]` | UTF-8, 0x00-padded |
| 0x18 | Timestamp | `u64` | Unix time, microseconds |
| 0x20 | Size | `u32` | Payload length, bytes |
| 0x24 | TTL | `u32` | Time-to-live, seconds; `0` = never expires |
| 0x28 | CRC32 | `u32` | CRC-32 of bytes 0x00–0x2B with 0x28–0x2B set to zero |

[DOCS/SPECIFICATIONS.md](DOCS/SPECIFICATIONS.md) gives the CRC-32 parameters and a test vector. The normative text is [PBS-ENV-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-ENV-01.md) v1.3 as corrected by the PBS v1.4.1 errata (2026-10-06).

---

## Conformance

[PBS-CONFORMANCE-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-CONFORMANCE-01.md) §2 defines a PBS Core conformant implementation as one that satisfies every MUST and MUST NOT in the PBS Core specifications. Four specifications carry Status Core: PBS-ENV-01 v1.3, PBS-PRIO-01 v1.4 and PBS-SEC-A-01 v1.3, which PBS-CONFORMANCE-01 §3 lists as mandatory, and PBS-CONFORMANCE-01 v1.3 itself, whose §4–§9 and §12 state further MUST requirements, such as "Apply priority to scheduling decisions" (§6). Requirements on receivers and relays include:

- Verify Magic `0x10`, the CRC-32, priority 0–4 and TTL before processing; discard on failure (§4.2, §9).
- Recompute the CRC-32 after modifying TTL (§5.2).
- Do not modify Priority, Flags, Sequence, Source ID, Timestamp or Size when relaying (§8).

---

## License

This project is licensed under the **Apache License 2.0**.  
See the [LICENSE](LICENSE) file for details.

Copyright © 2026 **Pale Blue Systems Foundation**
