# Why Now: Context for PBS_LINK

PBS_LINK is the Python reference SDK for the PBS-ENV-01 v1.5 message envelope. The envelope is a fixed, binary, transport-agnostic container: a 44-byte header that identifies the source and carries priority, timestamp, lifetime (TTL), sequence number and a header CRC-32, followed by the payload (PBS-ENV-01 §1, §2, §4).

No current networking failure drives this work. The motivation is the number and diversity of communication paths in planned space architectures.

---

## The Connectivity Model

The [LunaNet Interoperability Specification, Version 5](https://www.nasa.gov/wp-content/uploads/2025/02/lunanet-interoperability-specification-v5-baseline.pdf) (LNIS V005, Baseline, 29 January 2025), written and approved by NASA, ESA and JAXA, envisions LunaNet as "a network of cooperating networks" (§1). In that architecture:

- service providers deliver services over terrestrial interfaces, direct-with-Earth RF or optical links, links with lunar orbiting platforms, and links with lunar surface elements (§1);
- LunaNet 1.0 is planned to include service providers from NASA, ESA and Japan, operated as government systems or by commercial providers under contract to an agency; other commercial or international provider systems can comply with the LunaNet 1.0 specifications, and no single provider is required to meet every user need (§1);
- communications services are real-time or store-and-forward, the latter for long delays, disruption and disconnection (§3.1);
- DTN network services use Bundle Protocol version 7 (§3.1.2).

Continuous end-to-end connectivity is therefore not assumed, and network paths cross organizational boundaries.

---

## Position of the Envelope

PBS envelopes are user-application protocol data (PBS-LNIS-01 §2; PBS-DTN-MAP-02 §1). On LunaNet they are carried over IP or BPv7 network services (PBS-LNIS-01 §2). PBS-ENV-01 does not define transport, routing or physical-layer behavior (PBS-ENV-01 §2). A gateway or endpoint that uses BPv7 carries envelopes in bundles as PBS-DTN-MAP-01 and PBS-DTN-MAP-02 specify.

PBS_LINK builds and parses envelopes, writes them to a local serial port and reads them from it, unframed or COBS-framed. It does not schedule, store or forward them ([DOCS/INTEGRATION.md §2](DOCS/INTEGRATION.md#2-data-path-and-allocation-of-functions)).

---

## Purpose of Publishing Now

PBS_LINK publishes an implementation of the envelope so that independent implementations can test against it. The repository provides:

1. Envelope construction and parsing in `PBS_LINK/core.py`: source identity, priority, timestamp, TTL, sequence number and header CRC-32.
2. A header test vector ([DOCS/SPECIFICATIONS.md §3.1](DOCS/SPECIFICATIONS.md#31-test-vector)) and 68 tests in `TESTS/test_torture.py`.
3. The gateway requirements of PBS-ENV-01, PBS-PRIO-01, PBS-CONFORMANCE-01, PBS-DTN-MAP-01 and PBS-DTN-MAP-02, restated by section in [DOCS/INTEGRATION.md §5](DOCS/INTEGRATION.md#5-pbs-gateway-requirements). No PBS gateway implementation is published.

---

## Summary

Planned lunar networks are heterogeneous, intermittent and shared by independent operators (LNIS V005 §1, §3.1). PBS-ENV-01 envelopes are application protocol data carried over the IP or BPv7 network services of those networks (PBS-LNIS-01 §2). PBS_LINK publishes an implementation of the envelope (source identity, priority, timestamp, TTL, sequence number, header CRC-32) so that independent implementations can test against it.
