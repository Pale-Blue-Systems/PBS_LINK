# Why Now: Context for PBS_LINK

PBS_LINK is the Python reference SDK for the PBS-ENV-01 message envelope: a fixed, binary, transport-agnostic container that identifies the source and carries lifetime, sequence number, priority and a header CRC-32 (PBS-ENV-01 §1, §2). The envelope gives independently operated systems a common format for data exchanged across disrupted, delayed and heterogeneous space networks.

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

## The Architectural Problem

When connectivity is fragmented:

- assumptions about latency, availability and control differ between systems;
- tightly coupled systems fail when those assumptions do not hold;
- link behavior becomes an implicit policy decision instead of an explicit design choice.

Without a defined abstraction at the link layer, this complexity moves into applications and operations.

---

## Why Link Semantics Need Explicit Definition

Explicit link semantics let systems:

- represent disruption and delay explicitly;
- operate across variable transport conditions;
- separate application logic from connectivity assumptions;
- interoperate across independently managed infrastructure.

---

## Purpose of Publishing Now

This repository exists to:

1. State link-level assumptions before higher layers encode them.
2. Support experimentation with disruption-tolerant connectivity models.
3. Support collaboration among organizations that face the same constraints.

---

## Summary

Planned space networks are heterogeneous, intermittent and shared by independent operators (LNIS V005 §1, §3.1). Pale Blue Systems publishes PBS_LINK now so that link-level assumptions are explicit before higher layers depend on them.
