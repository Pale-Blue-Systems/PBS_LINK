# PBS-ENV-01 v1.3 Envelope Header: PBS_LINK Implementation Reference

This document summarizes the PBS-ENV-01 v1.3 header as PBS_LINK 0.1.1 implements it in `PBS_LINK/core.py`. The normative text is [PBS-ENV-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-ENV-01.md) in PBS-PROTOCOL-OPEN. Where this summary and the specification differ, the specification controls.

## 1. Encoding

- Header length: 44 bytes, fixed. The payload follows immediately; its length is the Size field.
- Byte order: big-endian for every multi-byte field.
- Integers: unsigned.
- Source ID: UTF-8, padded with 0x00 to 16 bytes.
- Reserved bytes: 0x00 on transmission; ignored on reception (PBS-ENV-01 §18).
- Python `struct` format used by PBS_LINK: `'>B B B x H xx 16s Q I I I'` (`HEADER_FORMAT`). The `x` pad bytes encode the reserved fields as 0x00.

## 2. Field Layout

| Offset | Field | Size (bytes) | Type | Content |
| :--- | :--- | :--- | :--- | :--- |
| 0x00 | Magic | 1 | u8 | `0x10` (PBS Core v1.x) |
| 0x01 | Priority | 1 | u8 | `0` CRITICAL, `1` HIGH, `2` NORMAL, `3` LOW, `4` BULK |
| 0x02 | Flags | 1 | u8 | Bit 0 `ACK_REQ` (`0x01`); bits 1–7 reserved, 0 |
| 0x03 | Reserved | 1 | u8 | `0x00` |
| 0x04 | Sequence | 2 | u16 | Per-source counter, 0–65535, wraps to 0 |
| 0x06 | Reserved | 2 | u16 | `0x0000` |
| 0x08 | Source ID | 16 | char[16] | UTF-8, 0x00-padded |
| 0x18 | Timestamp | 8 | u64 | Unix time, microseconds |
| 0x20 | Size | 4 | u32 | Payload length, bytes |
| 0x24 | TTL | 4 | u32 | Time-to-live, seconds; `0` = never expires |
| 0x28 | CRC32 | 4 | u32 | CRC-32 of bytes 0x00–0x2B with bytes 0x28–0x2B set to zero (Section 3) |

Total: 44 bytes.

## 3. CRC-32

| Parameter | Value |
| :--- | :--- |
| Algorithm | IEEE 802.3 CRC-32, as computed by zlib `crc32()` and Python `zlib.crc32` |
| Polynomial | 0x04C11DB7 (normal form); 0xEDB88320 (reflected form) |
| Initial value / final XOR | 0xFFFFFFFF / 0xFFFFFFFF |
| Input and output reflected | Yes |
| Check value, ASCII `123456789` | 0xCBF43926 |
| Input | Header bytes 0x00–0x2B (44 bytes) with bytes 0x28–0x2B set to 0x00 |
| Output | u32, stored big-endian at 0x28–0x2B |
| Coverage | Header only; the payload is not covered (PBS-ENV-01 §16.2) |

Sender (PBS-ENV-01 §13.1):

1. Build the header with bytes 0x28–0x2B set to `0x00000000`.
2. Compute the CRC-32 over all 44 bytes.
3. Write the result big-endian to bytes 0x28–0x2B.

Receiver (PBS-ENV-01 §13.1):

1. Extract the CRC-32 from bytes 0x28–0x2B.
2. Set bytes 0x28–0x2B to `0x00000000`.
3. Compute the CRC-32 over all 44 bytes.
4. Discard the envelope if the computed value differs from the extracted value.

Before the PBS v1.4.1 erratum, the PBS-ENV-01 field table and PBS-SEC-A-01 §4.1 step 3 gave the CRC input as bytes 0x00–0x27. A CRC-32 computed over those 40 bytes does not verify under the rule above. PBS_LINK 0.1.1 implements the 44-byte rule.

The CRC-32 detects corruption. It does not detect deliberate modification (PBS-SEC-A-01 §3.3).

### 3.1 Test Vector

Header-only envelope: Magic `0x10`, Priority `0` (CRITICAL), Flags `0x01`, Sequence `1`, Source ID `"Rover-A"`, Timestamp `1767225600000000` (2026-01-01T00:00:00Z), Size `0`, TTL `30`.

```
0x00  10 00 01 00  00 01 00 00  52 6f 76 65  72 2d 41 00
0x10  00 00 00 00  00 00 00 00  00 06 47 48  46 20 40 00
0x20  00 00 00 00  00 00 00 1e  58 87 21 ed
```

CRC-32 = `0x588721ED`. The same computation over bytes 0x00–0x27 only gives `0x019507AC`; a receiver applying Section 3 discards a header that carries that value. PBS_LINK reproduces the vector:

```python
import zlib
from PBS_LINK import PBSLink, Priority, verify_crc32

link = PBSLink(device_id="Rover-A", clock_source=lambda: 1_767_225_600.0)
header = link.send(Priority.CRITICAL, b"", ttl=30, require_ack=True)

assert header.hex() == (
    "10000100" "00010000" "526f7665722d4100" "0000000000000000"
    "0006474846204000" "00000000" "0000001e" "588721ed"
)
assert zlib.crc32(header[:0x28] + bytes(4)) == 0x588721ED  # 44-byte rule
assert zlib.crc32(header[:0x28]) == 0x019507AC             # 40-byte rule
assert verify_crc32(header)
```

## 4. Priority Classes

| Value | Name | Description |
| :--- | :--- | :--- |
| 0 | CRITICAL | Immediate life- or safety-critical data |
| 1 | HIGH | Mission-critical operational data |
| 2 | NORMAL | Routine mission data |
| 3 | LOW | Opportunistic or deferrable data |
| 4 | BULK | Non-urgent, high-volume data |

Values 5–255 are reserved and MUST NOT be used; receivers MUST discard envelopes that carry them (PBS-ENV-01 §6; PBS-PRIO-01 §4, §5.1). PBS_LINK `send()` raises `ValueError` for a priority outside 0–4; `parse()` raises `PBSPriorityError` for 5–255 unless `validate_priority=False`.

## 5. Layout Properties

- Fixed offsets: the header has no variable-length fields.
- Natural alignment: each multi-byte field starts at an offset that is a multiple of its size (u16 at 0x04 and 0x06; u64 at 0x18; u32 at 0x20, 0x24 and 0x28). A header stored at an 8-byte-aligned address permits a naturally aligned load of every field.
- Loss detection: a gap in the Sequence values from one Source ID identifies lost envelopes (PBS-ENV-01 §8).
- Expiry: an envelope with TTL > 0 is expired when `current_time − Timestamp / 10^6 > TTL`, with `current_time` in Unix seconds (PBS-ENV-01 §12.2).
