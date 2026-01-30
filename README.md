# PBS-LINK: Lunar Surface Communication SDK

![Version](https://img.shields.io/badge/version-v0.1.1-blue)
![Status](https://img.shields.io/badge/status-Beta-orange)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

**pbs-link** is the official Python Reference SDK for the **Pale Blue Systems (PBS)** network.

It allows any device—from a university rover to a commercial mining drill—to package telemetry and alerts into the **PBS-ENV-01** standard. This ensures your data can be routed, prioritized, and delivered reliably across the high-latency Lunar/Deep Space environment.

> **Note:** This is the *Client SDK* (Python). It connects to any standard-compliant PBS Gateway.

---

## 🚀 Features

* **PBS-ENV-01 Compliance:** Generates the standard 44-byte binary header required by PBS Gateways.
* **Space-Grade Reliability:** Includes CRC32 Integrity Checks and Sequence Tracking (0-65535) to detect packet loss and radiation corruption.
* **Priority Management:** Native support for P0 (Critical) through P4 (Bulk) traffic classes.
* **Transport Agnostic:** Designed to work over any serial stream (UART, RS-422, USB) that connects to a PBS Gateway.

---

## 📦 Installation

This package is currently in **v0.1.1 Beta**. You can install it directly from the source:

```bash
git clone [https://github.com/pale-blue-systems/pbs-link.git](https://github.com/pale-blue-systems/pbs-link.git)
cd pbs-link
pip install .
```

---

## ⚡ Quick Start

### 1. Sending an Emergency Alert (Priority 0)
Critical messages (P0) bypass all other traffic in the buffer.

```python
from pbs_link import PBSLink

# Initialize connection to the gateway (e.g., UART on /dev/ttyS0)
# For testing, you can omit the port to print bytes to console.
link = PBSLink(device_id="Rover-Alpha", serial_port=None)

# Send a "Critical" alert. 
# ttl=0 means "Never Expire" (Keep trying forever).
link.send(priority=0, payload="ERR: WHEEL_MOTOR_STALL", ttl=0, require_ack=True)
```

### 2. Sending Bulk Science Data (Priority 4)
Bulk data (P4) is sent only when bandwidth is free. It includes a TTL so old data doesn't clog the pipe.

```python
# Send a temperature log.
# ttl=60 means "If not sent within 60 seconds, drop this packet."
link.send(priority=4, payload="Temp: -40C, Rad: 12mSv", ttl=60)
```

---

## 🏗️ Architecture

The PBS Ecosystem bridges the gap between simple local code and complex NASA Deep Space protocols.

1.  **Your Code (Python):** Generates a simple packet using this SDK.
2.  **The Physical Link:** The SDK wraps the data in the **PBS-ENV-01** header and transmits it over a serial connection (UART/USB) to the Gateway.
3.  **The PBS Gateway:** The gateway device buffers the packet locally. It handles:
    * **Fragmentation:** Slicing large packets to fit into radio frames.
    * **Preemption:** Pausing "Bulk" uploads when "Critical" alerts arrive.
    * **Storage:** Persisting data during link outages.
4.  **The Uplink:** The Gateway encapsulates the message into a **CCSDS Bundle Protocol (BPv7)** packet and routes it via the Lunar Gateway to Earth.

---

## 📚 Documentation

Detailed guides for system integrators and developers:

*   **[System Integration Guide](DOCS/INTEGRATION.md):**  
    Deep dive into the **Data Pipeline**, **NASA DSN Compatibility**, and how data flows from your user application through the PBS Gateway to Earth.

*   **[Specification (PBS-ENV-01)](DOCS/SPECIFICATIONS.md):**  
    Byte-level breakdown of the binary header, including endianness, alignment, and CRC calculation.

---

## 📖 The Standard (PBS-ENV-01)

This SDK implements the open **PBS-ENV-01 v1.3** specification. All fields are **Big-Endian**.

| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| **0x00** | Magic | `u8` | Fixed `0x10` |
| **0x01** | Priority | `u8` | `0`=Critical ... `4`=Bulk |
| **0x02** | Flags | `u8` | `0x01`=ACK Requested |
| **0x04** | Sequence | `u16` | Rolling Counter (0-65535) |
| **0x08** | Source ID | `16s` | Device ID (e.g. "Drill-01") |
| **0x18** | Timestamp | `u64` | Unix Micros |
| **0x20** | Size | `u32` | Payload Size |
| **0x24** | TTL | `u32` | Time-to-Live (Seconds) |
| **0x28** | CRC32 | `u32` | Header Checksum |

*See [DOCS/SPECIFICATIONS.md](DOCS/SPECIFICATIONS.md) for the full byte-level layout.*

---

## 🛠️ Building Your Own Gateway

The PBS-ENV-01 standard is **Open Source**. You are encouraged to build your own implementations.

To be compliant, your custom Gateway must:
1.  Accept the 44-byte Header defined in `SPECIFICATION.md`.
2.  Respect the `TTL` field (drop expired packets).
3.  Map the `Priority` field to your underlying transport (e.g., TCP/IP or ION).

---

## 📄 License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.

Copyright © 2026 **Pale Blue Systems**.