# PBS-ENV-01 Specification (v1.3)

All integers are Unsigned, Big-Endian. Strings are UTF-8, null-padded.
Total Header Size: 44 Bytes.
Alignment: 4-Byte Aligned.

| Offset | Field | Size | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| 0x00 | Magic | 1 | u8 | Fixed `0x10` (Protocol ID v1.x) |
| 0x01 | Priority | 1 | u8 | `0`=Critical, `1`=High, `2`=Normal, `3`=Low, `4`=Bulk |
| 0x02 | Flags | 1 | u8 | `0x01`=ACK Requested |
| 0x03 | Reserved | 1 | u8 | Padding (Must be `0x00`) |
| 0x04 | Sequence | 2 | u16 | Rolling Counter (0-65535) |
| 0x06 | Reserved | 2 | u16 | Padding (Must be `0x0000`) |
| 0x08 | Source ID | 16 | char[16] | Device Name (null-padded) |
| 0x18 | Timestamp | 8 | u64 | Unix Epoch in Microseconds |
| 0x20 | Size | 4 | u32 | Payload Size in Bytes |
| 0x24 | TTL | 4 | u32 | Time-to-Live in Seconds (`0` = Forever) |
| 0x28 | CRC32 | 4 | u32 | Header Checksum (all 44 bytes, CRC field zeroed) |

**Total: 44 Bytes**

## Design Rationale

- **Aligned Access:** All 4-byte integers (Size, TTL, CRC32) start on 4-byte boundaries. This prevents alignment faults on strict embedded processors (ARM Cortex-M, RISC-V).
- **Safety:** CRC32 allows receivers to validate header integrity before trusting routing instructions.
- **Traceability:** Sequence numbers enable detection of lost packets ("Packet #502 was lost").
- **Simplicity:** Fixed 44-byte header with no variable-length fields enables efficient parsing.

## CRC32 Calculation

- Polynomial: IEEE 802.3 (0xEDB88320, reflected)
- Input: Header bytes 0x00–0x2B (44 bytes) with CRC32 field set to zero
- Output: 32-bit unsigned integer, big-endian

### Calculation Procedure

**Sender:**
1. Build header with CRC32 field (bytes 0x28–0x2B) set to `0x00000000`
2. Compute CRC32 over all 44 bytes
3. Write result to CRC32 field (big-endian)

**Receiver:**
1. Save CRC32 value from header
2. Set CRC32 field to `0x00000000`
3. Compute CRC32 over all 44 bytes
4. Compare with saved value; discard if mismatch

## Priority Classes

| Value | Name | Description |
| :--- | :--- | :--- |
| 0 | CRITICAL | Immediate life- or safety-critical data |
| 1 | HIGH | Mission-critical operational data |
| 2 | NORMAL | Routine mission data |
| 3 | LOW | Opportunistic or deferrable data |
| 4 | BULK | Non-urgent, high-volume data |

Values 5–255 are reserved and MUST NOT be used.
