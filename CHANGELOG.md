# Changelog

All notable changes to PBS_LINK (pip distribution `pbs-link`, import package `PBS_LINK`) are recorded here. Versions follow semantic versioning.

## [0.1.2] - 2026-10-06

### Fixed

- `COBSFraming.encode()` consumed the 0x00 byte that follows a full 254-byte block (code 0xFF). Code 0xFF carries no implicit zero, so the byte was lost, the decoded envelope was one byte short per occurrence, and `parse()` rejected it ("Incomplete payload"). The encoder now leaves that 0x00 to start the next block. Regression test: `TESTS/test_torture.py::TestCOBSFraming::test_cobs_zero_after_full_block`. Unframed transport was not affected.

### Changed

- README, `DOCS/INTEGRATION.md`, `DOCS/SPECIFICATIONS.md` and `WHY-NOW.md` describe what the SDK does, verified against `PBS_LINK/core.py` and PBS-ENV-01 v1.3 as corrected by the PBS v1.4.1 errata. Code examples use the real import package, `PBS_LINK`; `import pbs_link` fails on every platform.
- `python_requires` is `>=3.8`, the oldest version tested.
- Copyright notices and package author name the Pale Blue Systems Foundation, matching `LICENSE`.

### Added

- GitHub Actions workflow `.github/workflows/tests.yml`: tests, example and documentation code blocks on Python 3.8–3.12.

## [0.1.1] - 2026-01-29

Initial public release. Implements the PBS-ENV-01 v1.3 44-byte envelope: build and parse, CRC-32 header integrity, 16-bit sequence numbering, priority classes 0–4, TTL, and optional COBS framing.
