# PBS-LINK: Lunar Surface Communication SDK

![Version](https://img.shields.io/badge/version-v0.1.1-blue)
![Status](https://img.shields.io/badge/status-Beta-orange)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

**pbs-link** is the official Python Reference SDK for the **Pale Blue Systems (PBS)** network.

It allows any device—from a university rover to a commercial mining drill—to package telemetry and alerts into the **PBS-ENV-01** standard. This ensures your data can be routed, prioritized, and delivered reliably across high-latency, disruption-prone lunar and deep-space environments.

> **Note:** This is the *Client SDK* (Python). It connects to any standard-compliant PBS Gateway.

---

## Context and Intent

Pale Blue Systems publishes `pbs-link` in anticipation of a future space environment that includes multiple space agencies, commercial operators, scientific missions, and privately operated systems sharing off-Earth infrastructure.

This SDK does not address a current operational failure. It exists to support early experimentation, integration, and interoperability using an open, inspectable envelope standard—before future connectivity assumptions and conventions become fixed.

Additional context on why this work is published now is available in [`WHY-NOW.md`](WHY-NOW.md).

---

## Features

* **PBS-ENV-01 Compliance:** Generates the standard 44-byte binary header required by PBS Gateways.
* **Space-Grade Reliability:** Includes CRC32 integrity checks and sequence tracking (0–65535) to detect packet loss and radiation-related corruption.
* **Priority Management:** Native support for P0 (Critical) through P4 (Bulk) traffic classes.
* **Transport Agnostic:** Designed to operate over any serial stream (UART, RS-422, USB) connected to a PBS Gateway.

---

## Installation

This package is currently in **v0.1.1 Beta**. You can install it directly from the source:

```bash
git clone https://github.com/Pale-Blue-Systems/PBS_LINK.git
cd PBS_LINK
pip install .
```

---

## Quick Start

### 1. Sending an Emergency Alert (Priority 0)

Critical messages (P0) bypass all other traffic in the buffer.

```python
from PBS_LINK import PBSLink

# Initialize connection to the gateway (e.g., UART on /dev/ttyS0)
# For testing, you can omit the port to print bytes to console.
link = PBSLink(device_id="Rover-Alpha", serial_port=None)

# Send a "Critical" alert.
# ttl=0 means "Never Expire" (keep retrying indefinitely).
link.send(priority=0, payload="ERR: WHEEL_MOTOR_STALL", ttl=0, require_ack=True)
```

---

### 2. Sending Bulk Science Data (Priority 4)

Bulk data (P4) is sent only when bandwidth is available. A TTL ensures outdated data does not consume capacity indefinitely.

```python
# Send a temperature log.
# ttl=60 means "If not sent within 60 seconds, drop this packet."
link.send(priority=4, payload="Temp: -40C, Rad: 12mSv", ttl=60)
```

---

## Architecture

The PBS ecosystem bridges the gap between simple local application code and deep-space communication protocols.

1. **Your Code (Python)**  
   Generates a PBS-ENV-01–compliant packet using this SDK.

2. **The Physical Link**  
   The SDK wraps the payload in the PBS-ENV-01 header and transmits it over a serial interface (UART, USB, etc.) to a PBS Gateway.

3. **The PBS Gateway**  
   The gateway buffers and manages packets locally, handling:
   * Fragmentation to fit radio frames
   * Preemption when higher-priority traffic arrives
   * Storage during link outages

4. **The Uplink**  
   The gateway encapsulates messages into **CCSDS Bundle Protocol (BPv7)** packets and routes them through lunar, cislunar, or deep-space infrastructure toward Earth.

---

## Documentation

Detailed guides for integrators and developers:

* **[System Integration Guide](DOCS/INTEGRATION.md)**  
  Covers data flow, gateway behavior, and compatibility with NASA deep-space communication architectures.

* **[Specification (PBS-ENV-01)](DOCS/SPECIFICATIONS.md)**  
  Byte-level definition of the envelope header, including endianness, alignment, and CRC calculation.

---

## The Standard (PBS-ENV-01)

This SDK implements the open **PBS-ENV-01 v1.3** specification. All fields are **big-endian**.

| Offset | Field | Type | Description |
|------:|------|------|-------------|
| 0x00 | Magic | `u8` | Fixed `0x10` |
| 0x01 | Priority | `u8` | `0`=Critical … `4`=Bulk |
| 0x02 | Flags | `u8` | `0x01` = ACK Requested |
| 0x04 | Sequence | `u16` | Rolling Counter (0–65535) |
| 0x08 | Source ID | `16s` | Device Identifier |
| 0x18 | Timestamp | `u64` | Unix Time (microseconds) |
| 0x20 | Size | `u32` | Payload Size |
| 0x24 | TTL | `u32` | Time-to-Live (seconds) |
| 0x28 | CRC32 | `u32` | Header Checksum |

*See [DOCS/SPECIFICATIONS.md](DOCS/SPECIFICATIONS.md) for the complete layout.*

---

## Building Your Own Gateway

The PBS-ENV-01 standard is **open**, and `pbs-link` is the reference Python client implementation.

You are encouraged to build your own gateway or client implementations.

### Compliance Requirements

To ensure interoperability, implementations must satisfy:

1. **Bit-Level Compliance**  
   Strict adherence to the PBS-ENV-01 specification.

2. **Behavioral Compliance**
   * MUST drop packets with expired TTL.
   * MUST validate CRC32 before processing.
   * MUST NOT modify reserved fields.

3. **Conformance**  
   Refer to `PBS-CONFORMANCE-01` in the [PBS Open Protocol Repository](https://github.com/pale-blue-systems/PBS-PROTOCOL-OPEN) for the official checklist.

---

## License

This project is licensed under the **Apache License 2.0**.  
See the [LICENSE](LICENSE) file for details.

Copyright © 2026 **Pale Blue Systems**
