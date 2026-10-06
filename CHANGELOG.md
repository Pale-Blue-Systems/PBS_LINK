# Changelog

All notable changes to PBS_LINK (pip distribution `pbs-link`, import package `PBS_LINK`) are recorded here. Versions follow semantic versioning.

## [0.1.3] - 2026-10-06

### Fixed

- `receive()` with `use_framing=True` read the stream as an unframed header and raised `PBSMagicError` on the first byte of every COBS frame. It now reads to the 0x00 delimiter, decodes the frame and validates the envelope. Bytes past the delimiter and partial frames are kept for the next call; empty frames are skipped; a frame that fails decoding or validation raises and is consumed, so the next call reads the next frame; a stream with no delimiter within the longest valid frame raises `PBSFramingError` and resynchronizes at the next delimiter. A decoded frame longer or shorter than 44 bytes plus Size raises `PBSValidationError`.
- `receive()` restores the port's `timeout` attribute when a read raises.

### Changed

- README, `DOCS/INTEGRATION.md` §3.3, §3.4 and §4.5, and `WHY-NOW.md` describe framed receive and the 67-test suite.

### Added

- `TESTS/test_torture.py::TestFramedReceive`: 11 tests covering single and consecutive frames, empty frames, partial frames across timeouts, timeout restoration, corrupted and undecodable frames followed by a good frame, an overlong frame, a length mismatch, a payload above `max_payload_size`, and the unchanged unframed path.

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
