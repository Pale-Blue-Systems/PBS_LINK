# System Integration Guide

This guide details how data flows from your user application, through the PBS Hardware, and into the Deep Space Network (DSN).

## System Architecture

The Pale Blue Systems network uses a "Store-and-Forward" architecture designed for high-latency, disrupted environments (DTN).

### The Data Pipeline

1.  **User Space (Python SDK):** Your rover code generates a data payload and assigns it a Priority (P0-P4).
2.  **The Physical Link (UART):** The SDK wraps the data in the **PBS-ENV-01** header and transmits it over serial to the PBS-FRU-01 Module.
3.  **The PBS Gateway:** The module buffers the packet locally. It handles:
    * **Fragmentation:** Slicing large packets to fit into radio frames.
    * **Preemption:** Pausing "Bulk" uploads when "Critical" alerts arrive.
    * **Data Durability:** Storing data in non-volatile memory during radiation events.
4.  **The Uplink (NASA ION):** The Gateway encapsulates the message into a **CCSDS Bundle Protocol (BPv7)** packet and routes it via the Lunar Gateway to Earth.

## Software Integration Strategy

### 1. Basic Telemetry (Polling)
For routine health checks, use a standard loop. Set a short TTL so old health data doesn't clog the buffer if the link goes down.

```python
from pbs_link import PBSLink
import time

link = PBSLink("/dev/ttyS0")

while True:
    # TTL=60s: If this packet sits in the buffer for >1 min, drop it.
    link.send(2, "Battery: 98%", ttl=60)
    time.sleep(10)
```

### 2. Critical Alerts (Interrupts)
For safety-critical events (P0), use `ttl=0` (Never Expire) and request an ACK.

```python
# P0 = Critical. This will jump to the front of the queue immediately.
# ttl=0 means "Keep trying forever until confirmed."
link.send(0, "WHEEL_STUCK_ERROR", ttl=0, require_ack=True)
```

### 3. Bulk Data (File Transfer)
When sending images or logs (P4), allow the SDK to handle the packet. The PBS Hardware will automatically "drip feed" this data to the Gateway when bandwidth is available.

* **Warning:** Do not send large files as a single string. Chunk them into 4KB segments.
* **Note:** The PBS Gateway enforces a "Fair Use" policy. P4 traffic may be paused for hours during high-traffic windows (e.g., Crewed Missions).

## NASA DSN Compatibility
All data egressing the PBS Gateway is compliant with **CCSDS Blue Book 734.2-B-1**.

* **Source EID:** `ipn:99.[Your_Rover_ID]`
* **Dest EID:** `ipn:23.1` (Mission Control Earth)

You do not need to implement the Bundle Protocol. The PBS Hardware handles the encapsulation.