# Why Now — Context for PBS Link

PBS Link exists to explore **how independent systems can exchange data predictably across disrupted, delayed, or heterogeneous networks** in future space environments.

This work is not driven by a current networking failure.  
It is motivated by the increasing complexity and diversity of future space communication paths.

---

## The Emerging Connectivity Model

Future space networks are expected to include:

- planetary surface networks,
- cislunar relays,
- deep-space links,
- intermittent commercial and governmental infrastructure,
- dynamically changing topologies.

In this environment, **continuous connectivity cannot be assumed**, and network boundaries will often cross organizational lines.

---

## The Architectural Challenge

As connectivity becomes more fragmented:

- assumptions about latency, availability, and control diverge,
- tightly coupled systems become brittle,
- link behavior becomes an implicit policy decision rather than an explicit design choice.

Without clear abstraction at the link layer, complexity migrates upward into applications and operations.

---

## Why Link Semantics Need Early Attention

Explicit link semantics allow systems to:

- reason about disruption and delay,
- remain robust across variable transport conditions,
- decouple application logic from connectivity assumptions,
- interoperate across independently managed infrastructure.

Exploring these ideas early reduces the risk of brittle coupling later.

---

## Purpose of Publishing Now

This repository exists to:

1. Clarify link-level assumptions before they are encoded into higher layers.
2. Support experimentation with disruption-tolerant connectivity models.
3. Enable collaboration across organizations facing similar future constraints.

---

## Summary

PBS Link is published now because future space networks will be **heterogeneous, intermittent, and shared**.

Addressing link behavior early helps ensure that higher-level systems remain adaptable as the space communication environment evolves.
