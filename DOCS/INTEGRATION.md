# PBS_LINK System Integration Guide

**Applies to:** PBS_LINK 0.1.4 (pip distribution `pbs-link`, import package `PBS_LINK`), PBS-ENV-01 v1.5 (PBS v1.5.0)

This guide details how data flows from your user application, through the PBS Hardware, and into the Deep Space Network (DSN). Pale Blue Systems is building the PBS Hardware, the PBS-FRU-01 PBS Gateway module: section 2.1 describes its planned architecture, sections 4.2 and 4.3 its concept of operations, and section 5.5.1 its planned DSN compatibility.

This guide describes the interface between an application that uses PBS_LINK and a PBS gateway. Sections 2 and 3 describe what the SDK does. Section 4 shows application patterns. Section 5 restates, by reference to the PBS specifications, the requirements that apply to a conformant PBS gateway.

No PBS gateway implementation is published. [PBS-EDGE-ADAPTER-MV](https://github.com/Pale-Blue-Systems/PBS-EDGE-ADAPTER-MV) contains a worked example that encodes one PBS envelope as the payload block of a BPv7 bundle; it does not schedule, store or forward traffic.

---

## 1. Referenced Documents

PBS specifications are published in [PBS-PROTOCOL-OPEN/PBS-RFC-LIB](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/tree/main/PBS-RFC-LIB). The versions below are those of PBS v1.5.0 (2026-10-06).

| ID | Title | Version |
|----|-------|---------|
| [PBS-ENV-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-ENV-01.md) | Core Message Envelope | 1.5 |
| [PBS-PRIO-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-PRIO-01.md) | Priority Classification and Deterministic Handling | 1.4 |
| [PBS-SEC-A-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-SEC-A-01.md) | Integrity Verification and Security Boundaries | 1.5 |
| [PBS-CONFORMANCE-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-CONFORMANCE-01.md) | Conformance, Interoperability, and Mandatory Baselines | 1.5 |
| [PBS-DTN-MAP-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-DTN-MAP-01.md) | Mapping to Delay/Disruption Tolerant Networking (DTN) | 1.5 |
| [PBS-DTN-MAP-02](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-DTN-MAP-02.md) | Mapping to BPv7 Delay/Disruption Tolerant Networking | 1.5 |
| [PBS-SVC-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-SVC-01.md) | Mission Service Intent | 1.4 |
| [PBS-SEC-B-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-SEC-B-01.md) | Authenticated Mission Messaging | 1.5 |
| [PBS-MUX-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-MUX-01.md) | Payload Multiplexing and Semantic Framing | 1.4 |
| [RFC 9171](https://www.rfc-editor.org/rfc/rfc9171) | Bundle Protocol Version 7 (IETF, January 2022) | — |

---

## 2. Data Path and Allocation of Functions

```
application --PBSLink.send()--> envelope bytes --serial_port.write()--> link --> PBS gateway --> BPv7 bundle
                                (optional COBS)                                  (not published)
```

| Function | PBS_LINK 0.1.4 | PBS gateway (requirement source) |
|----------|----------------|----------------------------------|
| Build envelope (44-byte header + payload) | `send()`, `build_envelope()` | — |
| Header CRC-32 | Computed on send; verified by `parse()` and `receive()` | Verify before processing and before forwarding (PBS-ENV-01 §13, §15) |
| Sequence number | Incremented on each `send()` | Track per Source ID for gap detection (PBS-ENV-01 §8, SHOULD) |
| TTL expiry | Checked on receipt by `receive()` (unless `check_ttl=False`) and by `parse(check_ttl=True)` | Check on receipt, before forwarding stored envelopes and periodically while stored; discard expired envelopes; never discard an envelope with TTL 0 as TTL-expired (PBS-ENV-01 §12.1, §12.2) |
| Priority scheduling | None | PBS-PRIO-01 §6; PBS-CONFORMANCE-01 §6 |
| Storage through link outages | None | PBS-PRIO-01 §7 |
| Acknowledgement | Sets Flags bit 0 only | PBS-ENV-01 §7 defines the flag only; PBS-SVC-01 §8 defines acknowledgement policy for Service Intent |
| Header forwarding | None | Forward the 44 header bytes as received; modify no header field, TTL and CRC-32 included (PBS-ENV-01 §12.3, §15; PBS-CONFORMANCE-01 §8) |
| BPv7 encapsulation | None | PBS-DTN-MAP-01 or PBS-DTN-MAP-02 at DTN boundaries |

### 2.1 Planned Architecture (in development)

Pale Blue Systems is building the PBS Gateway as a hardware module, PBS-FRU-01, that each rover carries on its serial link. The module hosts the rover's own ION bundle protocol agent node, which creates the bundles that carry the rover's envelopes (section 5.5.1).

#### System Architecture

The Pale Blue Systems network uses a "Store-and-Forward" architecture designed for high-latency, disrupted environments (DTN).

#### The Data Pipeline

1.  **User Space (Python SDK):** Your rover code generates a data payload and assigns it a Priority (P0-P4).
2.  **The Physical Link (UART):** The SDK wraps the data in the **PBS-ENV-01** header and transmits it over serial to the PBS-FRU-01 Module.
3.  **The PBS Gateway:** The module buffers the packet locally. It handles:
    * **Fragmentation:** Slicing large packets to fit into radio frames, in the bundle and radio-link layers below PBS; each PBS envelope is carried whole in one bundle (PBS-DTN-MAP-01 §5.1).
    * **Preemption:** Pausing "Bulk" uploads when "Critical" alerts arrive.
    * **Data Durability:** Storing data in non-volatile memory during radiation events.
4.  **The Uplink (NASA ION):** The Gateway encapsulates the message into a **CCSDS Bundle Protocol (BPv7)** packet and routes it via the Lunar Gateway to Earth.

---

## 3. PBS_LINK Functions

All behavior below is implemented in `PBS_LINK/core.py`.

### 3.1 Building an Envelope: `PBSLink.send()`

`PBSLink(device_id, serial_port=None, max_payload_size=65536, use_framing=False, clock_source=None)` holds the source identity, sequence counter and output port.

`send(priority, payload, ttl=0, require_ack=False)` executes these steps:

1. Validates the input. `payload` is `str` (encoded as UTF-8) or `bytes`; `priority` is 0–4; the payload length does not exceed `max_payload_size`; `ttl` is not negative. A violation raises `ValueError`. A `ttl` above 4,294,967,295 or a non-integer `priority` passes these checks and raises `struct.error` when the header is packed (step 5).
2. Increments the sequence number under a lock. The first envelope from a `PBSLink` instance carries sequence 1. The counter wraps from 65535 to 0.
3. Encodes the first 16 characters of `device_id` as UTF-8, truncates the result to 16 bytes and pads it with 0x00 to 16 bytes.
4. Sets Timestamp to `int(clock_source() * 1_000_000)`. `clock_source` defaults to `time.time`; any callable that returns Unix time in seconds replaces it.
5. Packs the header with the CRC-32 field set to zero, computes `zlib.crc32` over the 44 bytes, and writes the result big-endian at offset 0x28.
6. Appends the payload. With `use_framing=True`, COBS-encodes header and payload and appends a 0x00 delimiter.
7. With `serial_port=None`, returns the bytes. Otherwise calls `serial_port.write(packet)` and returns its result, or `len(packet)` when `write()` returns `None`. An exception raised by `write()` is re-raised as `PBSSerialError`.

`serial_port` accepts any object with a `write(bytes)` method. pySerial's `serial.Serial.write()` returns the number of bytes written ([pySerial API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html)).

`build_envelope(source_id, priority, payload, ttl=0, sequence=0, require_ack=False)` builds one unframed envelope with an explicit sequence number and returns its bytes.

### 3.2 Parsing: `PBSLink.parse()` and `parse_envelope()`

`parse(data, validate_crc=True, validate_priority=True, check_ttl=False, current_time=None)` applies these checks in order:

| Step | Check | Exception on failure |
|-----:|-------|----------------------|
| 1 | With `use_framing=True` and a trailing 0x00, COBS-decode the frame | None; on a decode error the raw bytes are parsed |
| 2 | Length ≥ 44 bytes | `PBSValidationError` |
| 3 | Magic = 0x10 | `PBSMagicError` |
| 4 | Header CRC-32 matches (if `validate_crc`) | `PBSCRCError` |
| 5 | Priority ≤ 4 (if `validate_priority`) | `PBSPriorityError` |
| 6 | Length ≥ 44 + Size | `PBSValidationError` |
| 7 | `current_time − Timestamp / 10^6 ≤ TTL` (if `check_ttl` and TTL > 0) | `PBSTTLError` |

`PBSMagicError`, `PBSCRCError`, `PBSPriorityError` and `PBSTTLError` subclass `PBSValidationError`, which subclasses `PBSError`. `current_time` is Unix time in seconds and defaults to `clock_source()`; `current_time=0.0` is used as given.

`parse()` returns a `PBSEnvelope` holding every header field, the payload (exactly Size bytes), `raw_header`, and the properties `priority_name`, `ack_requested` and `timestamp_seconds`.

`parse()` does not check TTL by default. PBS-ENV-01 §12.2 and §14 require a receiver to check TTL on receipt. `receive()` does (section 3.3); code that receives envelopes by other means calls `parse(..., check_ttl=True)`.

`parse_envelope(data, validate=True)` parses an unframed envelope. `validate` switches the CRC-32 and priority checks together; TTL is not checked.

### 3.3 Reading a Serial Port: `receive()` and `find_sync()`

Unframed (`use_framing=False`), `receive(timeout=None, check_ttl=True)` reads 44 bytes from `serial_port`, checks Magic, rejects a Size larger than `max_payload_size` with `PBSValidationError`, reads Size payload bytes, and applies the `parse()` checks of section 3.2. It returns `None` when a read returns fewer bytes than requested. If the port object has a `timeout` attribute, `receive()` applies `timeout` to the header read only and then restores the previous value.

Framed (`use_framing=True`), `receive()` reads from `serial_port` until a 0x00 delimiter, COBS-decodes the frame and parses it. It reads the bytes the port reports in `in_waiting`, at least one per read. Bytes read past the delimiter are kept for the next call. When a read returns no bytes, `receive()` returns `None` and keeps any partial frame for the next call. Empty frames (consecutive 0x00 bytes) are skipped. A frame that fails COBS decoding raises `PBSFramingError`; a frame that fails validation raises the `parse()` exception, and a frame whose decoded length differs from 44 bytes plus Size raises `PBSValidationError`. The frame is consumed in each case, so the next call continues with the next frame. While the receive buffer holds more than the longest valid encoded frame (44 bytes plus `max_payload_size`, plus COBS overhead) and no delimiter, `receive()` raises `PBSFramingError` and discards bytes up to the next delimiter; it raises again each time the discarded run exceeds that length. If the delimiter arrives in the read that takes the buffer past that length (possible when the port reports `in_waiting`), the overlong frame is decoded like any other frame and raises the COBS or validation exception it produces. If the port has a `timeout` attribute, `receive()` applies `timeout` for the whole call and restores the previous value.

On both paths `receive()` applies the PBS-ENV-01 §12.2 expiry check on receipt: an envelope with TTL > 0 is expired when `clock_source() − Timestamp / 10^6 > TTL` and raises `PBSTTLError`. An envelope with TTL 0 never expires (PBS-ENV-01 §12.1). The exception is raised after the envelope has been read in full, so the unframed stream stays aligned and an expired frame is consumed like any other invalid frame; the next call reads the next envelope. `receive(check_ttl=False)` skips the check and returns expired envelopes. The check reads the `clock_source` that stamps outgoing envelopes; an error in that clock shifts each expiry decision by the same amount.

`find_sync(data)` returns `(offset, data[offset:])` for the first offset at which byte 0x10 starts a 44-byte header with a valid CRC-32, or `(-1, data)` if there is none. It restores envelope alignment in an unframed byte stream after data loss.

### 3.4 Limitations of PBS_LINK 0.1.4

- No scheduling, queuing, preemption, storage or retransmission.
- `require_ack=True` sets Flags bit 0 (0x01). PBS_LINK does not wait for, match or retransmit on acknowledgements.
- No segmentation or reassembly. `send()` rejects a payload larger than `max_payload_size` (default 65,536 bytes).
- The CRC-32 covers the 44-byte header only. Payload integrity is an application function (PBS-ENV-01 §16.2).
- No cryptographic authentication: neither the PBS-SEC-A-01 §7 extensions nor PBS-SEC-B-01.
- No PBS-SVC-01 Service Intent, PBS-MUX-01 frames or BPv7 encapsulation.
- Source ID truncation is byte-based. A multi-byte UTF-8 character that crosses byte 16 is cut and leaves invalid UTF-8 in the field; `parse()` decodes it with replacement characters. Source IDs of at most 16 ASCII characters avoid this.
- The sequence counter belongs to one `PBSLink` instance and is held in memory only. The first envelope from each new instance carries sequence 1. A process restart, or two instances with the same `device_id`, therefore breaks the per-source monotonic sequence that PBS-ENV-01 §8 and PBS-CONFORMANCE-01 §7 require, and a receiver that tracks sequence numbers reports false gaps or duplicates. Use one `PBSLink` instance per Source ID. To continue the sequence after a restart, store the last sequence number sent and assign it to `link.sequence` before the first `send()`; the next envelope carries that value plus 1, modulo 65,536.
- `parse()` checks payload length (step 6) before TTL (step 7); PBS-ENV-01 §14 orders TTL validation before payload extraction. An expired envelope with a short payload therefore raises `PBSValidationError` instead of `PBSTTLError`, from `parse()` and from framed `receive()`. Both exceptions reject the envelope.

---

## 4. Application Patterns

The examples run as written, in order, in one interpreter session against the installed package (`pip install .`); sections 4.2–4.4 reuse `link` from section 4.1. With `serial_port=None`, `send()` returns the envelope bytes instead of writing them.

### 4.1 Periodic Telemetry

PBS-ENV-01 §12.1 and §12.2 require a gateway to discard an envelope once more than TTL seconds have elapsed since its Timestamp, regardless of priority (PBS-PRIO-01 §7). TTL therefore bounds how long a stale sample occupies the storage of a conformant gateway. Consecutive sequence numbers let the receiver detect lost envelopes (PBS-ENV-01 §8).

```python
import time
from PBS_LINK import PBSLink, Priority

link = PBSLink(device_id="Rover-Alpha", serial_port=None)

PERIOD_S = 1.0
for _ in range(3):  # flight software runs this loop until shutdown
    packet = link.send(Priority.NORMAL, "Battery: 98%", ttl=60)
    time.sleep(PERIOD_S)

print("last sequence number:", link.sequence)  # 3
```

**Concept of operations (PBS Gateway, in development).** For routine health checks, use a standard loop. Set a short TTL so old health data doesn't clog the buffer if the link goes down.

```
from PBS_LINK import PBSLink
import time

link = PBSLink("/dev/ttyS0")

while True:
    # TTL=60s: If this packet sits in the buffer for >1 min, drop it.
    link.send(2, "Battery: 98%", ttl=60)
    time.sleep(10)
```

```python
# TTL=60s: if more than 1 min has passed since its Timestamp, the gateway drops it.
link.send(2, "Battery: 98%", ttl=60)
```

### 4.2 Critical Alert

CRITICAL (0) is the highest class (PBS-PRIO-01 §4). `ttl=0` means the envelope never expires (PBS-ENV-01 §12.1). `require_ack=True` sets Flags bit 0. Forwarding order is a gateway function: higher-priority envelopes SHOULD be forwarded first (PBS-PRIO-01 §6), and a gateway MAY preempt a lower-priority transmission (PBS-PRIO-01 §6.1).

```python
alert = link.send(Priority.CRITICAL, "WHEEL_STUCK_ERROR", ttl=0, require_ack=True)
assert alert[0x01] == 0 and alert[0x02] == 0x01  # Priority byte, Flags byte
```

**Concept of operations (PBS Gateway, in development).** For safety-critical events (P0), use `ttl=0` (Never Expire) and request an ACK.

```python
# P0 = Critical. This will jump to the front of the queue immediately.
# ttl=0 means "Keep trying forever until confirmed."
link.send(0, "WHEEL_STUCK_ERROR", ttl=0, require_ack=True)
```

### 4.3 Bulk Data Segmentation

PBS-ENV-01 §16.3 recommends segmenting bulk transfers into multiple envelopes and 1–4 KB payloads for memory-constrained embedded devices. PBS_LINK does not segment. The application defines the segment format; the example below carries no reassembly metadata, which a real transfer adds (for example object identifier, byte offset and total length).

```python
image = bytes(range(256)) * 40  # stand-in for a 10,240-byte image
SEGMENT_BYTES = 4096

segments = [image[i:i + SEGMENT_BYTES] for i in range(0, len(image), SEGMENT_BYTES)]
packets = [link.send(Priority.BULK, seg, ttl=86_400) for seg in segments]

assert [len(p) - 44 for p in packets] == [4096, 4096, 2048]
```

**Concept of operations (PBS Gateway, in development).** When sending images or logs (P4), allow the SDK to handle the packet. The PBS Hardware will automatically "drip feed" this data to the Gateway when bandwidth is available.

* **Warning:** Do not send large files as a single string. Chunk them into 4KB segments.
* **Note:** The PBS Gateway enforces a "Fair Use" policy. P4 traffic may be paused for hours during high-traffic windows (e.g., Crewed Missions).

### 4.4 Payload Integrity

The header CRC-32 does not cover the payload. PBS-ENV-01 §16.2 lists a trailing CRC-32, HMAC-SHA256 or AES-GCM as application-level options. A trailing CRC-32:

```python
import zlib

data = b"SPECTROMETER FRAME 0001"
payload = data + zlib.crc32(data).to_bytes(4, "big")
packet = link.send(Priority.NORMAL, payload, ttl=3600)

env = link.parse(packet)
body, trailer = env.payload[:-4], env.payload[-4:]
assert zlib.crc32(body) == int.from_bytes(trailer, "big")
```

### 4.5 Serial Output with COBS Framing

With `use_framing=True`, each envelope is COBS-encoded and terminated by 0x00. No other 0x00 byte occurs in the frame, so a receiver restores alignment at the next delimiter after a byte error. Both ends of the link use the same framing setting; PBS specifications do not define link framing. `io.BytesIO` stands in for a serial port here.

```python
import io

port = io.BytesIO()  # stands in for serial.Serial("/dev/ttyS0", 115200)
tx = PBSLink(device_id="Rover-Alpha", serial_port=port, use_framing=True)
written = tx.send(Priority.HIGH, "MODE: SAFE", ttl=30)

frame = port.getvalue()
assert written == len(frame) and frame[-1] == 0x00 and 0x00 not in frame[:-1]

env = tx.parse(frame)  # parse() decodes COBS when use_framing=True
assert env.payload == b"MODE: SAFE"

rx = PBSLink(device_id="Ground", serial_port=io.BytesIO(frame), use_framing=True)
env = rx.receive()  # reads to the 0x00 delimiter, decodes and validates
assert env.payload == b"MODE: SAFE" and env.source_id == "Rover-Alpha"
```

### 4.6 Expiry Check on Receipt

PBS-ENV-01 §12.2 requires every receiver to check TTL on receipt. `receive()` applies the check with the receiver's `clock_source` (section 3.3). Both clocks are fixed below: the HIGH command expires 30 s after its Timestamp; the CRITICAL alert has TTL 0 and never expires (PBS-ENV-01 §12.1).

```python
import io
from PBS_LINK import PBSTTLError

T = 1_767_225_600.0  # 2026-01-01T00:00:00Z
sender = PBSLink(device_id="Rover-Alpha", clock_source=lambda: T)
stream = sender.send(Priority.HIGH, "CMD: HOLD", ttl=30) + sender.send(Priority.CRITICAL, "ALERT", ttl=0)

rx = PBSLink(device_id="Ground", serial_port=io.BytesIO(stream), clock_source=lambda: T + 31)
try:
    rx.receive()  # 31 s after Timestamp, TTL 30: expired
except PBSTTLError as exc:
    print("discarded:", exc)

env = rx.receive()  # the next envelope; TTL 0 never expires
assert env.payload == b"ALERT" and env.ttl == 0

late = PBSLink(device_id="Ground", serial_port=io.BytesIO(stream), clock_source=lambda: T + 31)
assert late.receive(check_ttl=False).payload == b"CMD: HOLD"  # check skipped
```

---

## 5. PBS Gateway Requirements

PBS Core conformance requires every MUST and MUST NOT in the PBS Core specifications (PBS-CONFORMANCE-01 §2). The tables below restate the clauses that govern a gateway, with their original keywords; the cited specification text controls.

### 5.1 Envelope Validation

| Requirement | Source |
|-------------|--------|
| Receivers MUST process in this order: Magic, CRC-32, Priority, TTL, payload extraction. Failure at any step MUST result in discard. | PBS-ENV-01 §14 |
| Receivers MUST reject envelopes with unrecognized Magic values. PBS Core v1.x sets Magic to 0x10. | PBS-ENV-01 §5 |
| Receivers MUST verify the CRC-32 before processing and MUST discard envelopes that fail. The CRC-32 is IEEE 802.3 (reflected polynomial 0xEDB88320) over header bytes 0x00–0x2B with bytes 0x28–0x2B set to zero. | PBS-ENV-01 §13, §13.1 |
| Receivers MUST discard envelopes with Priority 5–255. | PBS-ENV-01 §6; PBS-PRIO-01 §5.1 |
| Gateways MUST discard expired envelopes. An envelope with TTL > 0 is expired when `current_time − Timestamp / 10^6 > TTL`. TTL 0 never expires: nodes MUST NOT discard an envelope with TTL 0 as TTL-expired. | PBS-ENV-01 §12.1, §12.2 |
| Implementations MUST continue processing subsequent envelopes after a discard. | PBS-ENV-01 §17 |

### 5.2 Scheduling

| Requirement | Source |
|-------------|--------|
| Higher-priority envelopes SHOULD be forwarded before lower-priority envelopes. | PBS-PRIO-01 §6 |
| A conformant implementation MUST apply priority to scheduling decisions. The scheduling algorithm is implementation-defined. | PBS-CONFORMANCE-01 §6 |
| Implementations MAY apply fair-use, aging or predictive mechanisms within a class. Lower-priority envelopes MAY be delayed or dropped under sustained congestion. | PBS-PRIO-01 §6 |
| Implementations MAY preempt a lower-priority transmission, provided link-layer integrity is maintained. | PBS-PRIO-01 §6.1 |
| Relays MUST NOT modify the Priority field. | PBS-PRIO-01 §5.1 |

### 5.3 Storage, Retention and Forwarding

| Requirement | Source |
|-------------|--------|
| Higher-priority envelopes SHOULD receive preferential storage. Lower-priority envelopes MAY be discarded when storage is exhausted. TTL expiry applies regardless of priority. | PBS-PRIO-01 §7 |
| Receivers MUST check TTL on receipt, before forwarding stored envelopes, and periodically for stored envelopes awaiting transmission. | PBS-ENV-01 §12.2 |
| Relays and gateways MUST NOT modify TTL; every node evaluates expiry against the unchanged Timestamp and TTL, and an envelope with TTL 0 is never discarded as TTL-expired. | PBS-ENV-01 §12.1, §12.3 |
| Gateways and relays MUST verify the CRC-32 before forwarding, MUST check TTL expiration against the unchanged Timestamp and TTL, MUST maintain a clock synchronized to Unix epoch time for that check, MUST discard expired envelopes, and MUST forward the 44 header bytes as received, including TTL and the CRC-32. | PBS-ENV-01 §15; PBS-CONFORMANCE-01 §8 |
| Relays MUST NOT forward envelopes with an invalid CRC-32. | PBS-SEC-A-01 §5 |
| Relays and gateways MUST NOT modify any header field, including TTL and the CRC-32, and MUST NOT forward envelopes with invalid structure. | PBS-CONFORMANCE-01 §8; PBS-SEC-A-01 §5 |

PBS v1.4.1 and earlier permitted, and in PBS-ENV-01 §15 required, a relay to decrement TTL by its storage duration and recompute the CRC-32. An envelope forwarded by such a relay is valid, and a receiver cannot distinguish the reduced TTL from the originator's. Later nodes expire it earlier than its originator set, by the total interval subtracted, and the decrement method discarded every envelope with TTL 0 (PBS-ENV-01 §12.3).

### 5.4 BPv7 Encapsulation

PBS-DTN-MAP-01 (v1.5, status "Optional (Interoperability)") and PBS-DTN-MAP-02 (v1.5, status "Optional Interoperability Profile") both define carriage of PBS over BPv7. Neither document states that it replaces the other. PBS-DTN-MAP-01 §6.1, §6.1.1 and §6.3 refer to PBS-DTN-MAP-02 §4 and §5. PBS-CONFORMANCE-01 §3.1 lists PBS-DTN-MAP-01 and PBS-DTN-MAP-02 as optional and requires an optional specification to be implemented fully if claimed.

| Topic | PBS-DTN-MAP-01 v1.5 | PBS-DTN-MAP-02 v1.5 |
|-------|---------------------|---------------------|
| Scope | DTN boundaries only; DTN wrapping is not required within PBS-native domains (§2) | PBS gateways and endpoints using BPv7 |
| Envelope to bundle | Each envelope SHALL map to exactly one bundle and MUST NOT be fragmented across bundles (§5.1) | One PBS protocol data unit SHOULD map to one BP application data unit unless a registered segmentation profile applies (§2) |
| Payload block | The complete envelope (44-byte header + payload) SHALL be placed in a single BPv7 payload block, unaltered; the PBS CRC-32 MUST be preserved (§6.2, §6.4) | PBS envelope and semantic frames are carried as BPv7 payload (§2) |
| Endpoint IDs | Source ID to EID mapping MUST be deterministic within a gateway; the destination EID is configured at the gateway (§8) | The mapping SHALL be deterministic, stable for the mission transaction and SHALL preserve authority scope (§3) |
| Lifetime | For TTL > 0 at most the interval remaining until the envelope expires, and an envelope with less than 1 ms remaining is not encapsulated (§6.1); for TTL 0 the documented no-expiry lifetime, unless a PBS-DTN-MAP-02 §4 finite limit applies (§6.1.1); DTN lifetime expiry, as the BP agent determines it, MUST result in envelope discard, and PBS TTL MUST NOT be modified (§7.3) | Bundle lifetime SHALL be selected so that network delivery cannot extend the message beyond its deadline or expiry; for a finite limit the adapter SHALL bound it by the interval remaining at bundle creation; when no finite limit applies, the documented no-expiry lifetime (§4) |
| Priority | No primary block field carries priority, and reserved or unassigned bundle processing control flags MUST NOT convey it. A gateway that requests network treatment on the basis of priority SHALL document a PBS-DTN-MAP-02 §5 mapping profile that defines the treatment of all five classes; with other inputs equal, it SHALL NOT request a more favorable treatment for a class than for any higher-priority class; when it requests DTN classes, it maps CRITICAL and HIGH to Expedited, NORMAL to Normal, LOW and BULK to Bulk (§6.1, §6.3) | Priority is preserved unchanged; the mapping profile SHALL document the BP QoS mechanism, queue treatment, congestion behavior and unavailable-treatment behavior (§5) |
| Inbound | DTN-layer validation first; the envelope is extracted verbatim and not modified (§7.1, §7.2); PBS expiry is evaluated against Timestamp, and time spent in the DTN domain counts (§7.3) | PBS application acceptance SHALL evaluate PBS freshness independently of BP delivery status (§4); translation of a BP status event into a PBS service-status result SHALL keep network status, PBS receipt, application acceptance and transaction result distinct (§9) |
| Security | BPSec MAY be added and does not replace the PBS CRC-32 (§6.4) | BPSec SHALL be applied when the network-security profile requires it (§7) |

Notes for implementers:

- PBS-DTN-MAP-01 v1.3, the version before v1.5, gave LOW (3) no class of service; mapped Priority to a class of service, for which the BPv7 primary block has no field (RFC 9171 §4.3.1, §9.3); mapped Sequence to the creation timestamp sequence number, which RFC 9171 §4.2.7 assigns to the source node's bundle protocol agent; converted TTL seconds to a bundle lifetime (TTL × 1000 ms), which counts from bundle creation rather than from Timestamp; and defined no bundle lifetime for TTL 0. PBS-DTN-MAP-01 v1.5 §6.1, §6.1.1 and §6.3 replace those rules.
- PBS v1.5.0 records one known issue, in PBS-DTN-MAP-01 §8 (PBS-PROTOCOL-CHANGELOG.md, [1.5.0]). RFC 9171 §5.2 requires the source node ID of a bundle to be the null endpoint ID or the EID of a singleton endpoint whose only member is the node of which the bundle protocol agent is a component. A Source ID mapped to an EID of another node produces bundles that do not conform to RFC 9171.

Example Source ID to EID mapping, with the illustrative values of PBS-DTN-MAP-01 §8:

```
Source ID       ->  DTN source EID (example)
"Rover-Alpha"   ->  ipn:99.1
"Drill-01"      ->  ipn:99.2
```

In the planned PBS architecture each rover's PBS-FRU-01 module hosts the rover's own ION bundle protocol agent node, so the source EID is an endpoint of that rover's own node (sections 2.1 and 5.5.1; RFC 9171 §5.2).

#### 5.4.1 Lifetime Bound

RFC 9171 expresses bundle creation time as DTN time, in milliseconds since 2000-01-01T00:00:00Z (§4.2.6, §4.2.7), and lifetime in milliseconds past the creation time (§4.3.1). PBS-ENV-01 expresses Timestamp in Unix microseconds and TTL in seconds. For TTL > 0 the bundle lifetime SHALL NOT exceed the PBS-DTN-MAP-01 §6.1 bound, the interval remaining until the envelope expires:

```
lifetime_ms <= floor((TTL_s * 1_000_000 - max(0, c_us - Timestamp_us)) / 1000)
c_us = (creation_dtn_ms + 946_684_800_000) * 1000
```

946,684,800 s is the Unix time of the DTN epoch, and `c_us` is the bundle creation time in Unix microseconds. A bundle with this lifetime expires no later than the envelope, as PBS-DTN-MAP-02 §4 requires for a finite limit. An envelope for which the bound is less than 1 has expired or has less than 1 ms remaining, and SHALL NOT be encapsulated (PBS-DTN-MAP-01 §6.1).

The bound requires a known bundle creation time. DTN time 0 means that the time is unknown (RFC 9171 §4.2.6), and RFC 9171 §4.2.7 recommends creation time 0 for nodes that lack accurate clocks. With creation time 0, `c_us` is the gateway's Unix time in microseconds at bundle creation (PBS-DTN-MAP-01 §6.1), and the bundle MUST carry exactly one Bundle Age block (RFC 9171 §4.4.2).

For TTL 0 the envelope never expires. The gateway SHALL set the bundle lifetime to its no-expiry lifetime, unless it also implements PBS-DTN-MAP-02 and a PBS-DTN-MAP-02 §4 finite limit applies (PBS-DTN-MAP-01 §6.1.1). The no-expiry lifetime SHALL be greater than 0 ms, SHALL NOT be less than any lifetime the gateway assigns to an envelope with TTL > 0 or under a finite limit, SHALL NOT exceed 4,294,967,295,000 ms (TTL 4,294,967,295 s), and SHALL be a value that the bundle protocol agent accepts and for which the expiration time it computes, creation time plus lifetime (RFC 9171 §5.5), does not overflow. The gateway SHALL document the value and the bundle protocol agent for which it was selected, and SHOULD use the largest value that meets these conditions: 4,294,967,295,000 ms for an agent that holds DTN time and expiration time in 64-bit integers. PBS-DTN-MAP-02 §4 sets the same bounds for an adapter when no finite limit applies.

```python
DTN_EPOCH_UNIX_MS = 946_684_800_000  # 2000-01-01T00:00:00Z in Unix milliseconds

def max_bundle_lifetime_ms(timestamp_us: int, ttl_s: int, creation_dtn_ms: int) -> int:
    """PBS-DTN-MAP-01 section 6.1 lifetime bound for an envelope with TTL > 0."""
    if creation_dtn_ms == 0:
        raise ValueError("creation time unknown (RFC 9171 4.2.6); use the gateway clock for c_us")
    c_us = (creation_dtn_ms + DTN_EPOCH_UNIX_MS) * 1000
    return (ttl_s * 1_000_000 - max(0, c_us - timestamp_us)) // 1000

stamped_us = 1_767_225_600_000_000  # 2026-01-01T00:00:00Z
created = (1_767_225_605 * 1000) - DTN_EPOCH_UNIX_MS  # 5 s after Timestamp

assert max_bundle_lifetime_ms(stamped_us, 60, created) == 55_000
# Created 60 s after Timestamp: no time remains; the envelope is not encapsulated.
assert max_bundle_lifetime_ms(stamped_us, 60, created + 55_000) < 1
# Creation time 10 s before Timestamp (clock offset): the bound is TTL in milliseconds.
assert max_bundle_lifetime_ms(stamped_us, 60, created - 15_000) == 60_000
```

### 5.5 NASA Deep Space Network

PBS-PRIO-01 §14 distinguishes DSN antenna scheduling (ground-scheduled, hours to days ahead) from PBS packet scheduling within an allocated link. Its §14.2 table relating DSN scheduling priority levels 1–7 to PBS classes 0–4 is informative, and implementations MAY define mission-specific mappings. PBS priority values MUST remain as defined in PBS-PRIO-01 §4 (§14.2).

#### 5.5.1 NASA DSN Compatibility (planned, in development)

Pale Blue Systems is building the PBS Gateway to these design targets.

All data egressing the PBS Gateway is compliant with **CCSDS Blue Book 734.2-B-1**.

All data egressing the PBS Gateway is compliant with **BPv7 ([RFC 9171](https://www.rfc-editor.org/rfc/rfc9171))**; the design target is the CCSDS profile of BPv7, **CCSDS 734.2-P-1.1** (draft Recommended Standard), which LNIS V005 §3.1.2 cites as applicable document [AD19].

* **Source EID:** `ipn:99.[Your_Rover_ID]`
* **Dest EID:** `ipn:23.1` (Mission Control Earth)

Each rover runs its own ION bundle protocol agent node, hosted by its PBS-FRU-01 module (section 2.1). The source EID is therefore an endpoint of the node whose bundle protocol agent creates the bundle, as RFC 9171 §5.2 requires.

You do not need to implement the Bundle Protocol. The PBS Hardware handles the encapsulation.
