# Changelog

All notable changes to PBS_LINK (pip distribution `pbs-link`, import package `PBS_LINK`) are recorded here. Versions follow semantic versioning.

## [0.1.4] - 2026-10-06

### Fixed

- `receive()` returned expired envelopes. PBS-ENV-01 v1.5 Section 12.2 requires every receiver to check TTL expiration on receipt. `receive()` now applies the check on the unframed and framed paths: an envelope with TTL > 0 for which `clock_source() − Timestamp / 10^6 > TTL` raises `PBSTTLError`. The envelope has been read in full when the exception is raised, so the unframed stream stays aligned and an expired frame is consumed like any other invalid frame. An envelope with TTL 0 never expires (Section 12.1).
- The TTL check read `time.time()` when no `current_time` was passed and ignored the `clock_source` given to `PBSLink`. It now reads `clock_source()`.
- `parse(check_ttl=True, current_time=0.0)` treated 0.0 as unset and read the clock. It now uses 0.0.

### Changed

- `receive()` raises `PBSTTLError` for an expired envelope. Code that needs expired envelopes calls `receive(check_ttl=False)`. The check compares the link's `clock_source` with Timestamp; an error in that clock shifts each expiry decision by the same amount.
- Documentation follows PBS v1.5.0 (2026-10-06): PBS-ENV-01, PBS-SEC-A-01, PBS-CONFORMANCE-01, PBS-DTN-MAP-01, PBS-DTN-MAP-02 and PBS-SEC-B-01 are v1.5. README and `DOCS/INTEGRATION.md` §5.1 and §5.3 state the v1.5 relay and gateway rules: no header field, TTL and CRC-32 included, is modified in transit; the 44 header bytes are forwarded as received; expiry is checked against the unchanged Timestamp and TTL; an envelope with TTL 0 is never discarded as TTL-expired. `DOCS/INTEGRATION.md` §5.4 and §5.4.1 state the PBS-DTN-MAP-01 v1.5 lifetime (Sections 6.1 and 6.1.1), priority (Section 6.3) and TTL (Section 7.3) rules and the PBS-DTN-MAP-02 v1.5 Section 4 no-expiry lifetime.

### Added

- `receive(check_ttl=True)` parameter.
- `TESTS/test_torture.py::TestReceiveExpiry`: 8 tests covering expired unframed and framed receive, `check_ttl=False`, an unexpired envelope at an age equal to TTL, the receiver's `clock_source`, `current_time=0.0`, TTL 0, and the PBS-ENV-01 Section 12.5 TTL 30 case. Each fails with its fix reverted. 76 tests.
- `DOCS/INTEGRATION.md` §4.6 and `DOCS/SPECIFICATIONS.md` §6: executable examples of the expiry check; §6 reproduces the PBS-ENV-01 Section 12.5 test cases (CRC-32 `0x588721ED`, `0xCDE710AF`, `0x8757080E`).

## [0.1.3] - 2026-10-06

### Fixed

- `receive()` with `use_framing=True` read the stream as an unframed header and raised `PBSMagicError` on the first byte of every COBS frame. It now reads to the 0x00 delimiter, decodes the frame and validates the envelope. Bytes past the delimiter and partial frames are kept for the next call; empty frames are skipped; a frame that fails decoding or validation raises and is consumed, so the next call reads the next frame; a receive buffer that exceeds the longest valid encoded frame without a delimiter raises `PBSFramingError` and resynchronizes at the next delimiter. A decoded frame longer or shorter than 44 bytes plus Size raises `PBSValidationError`.
- `receive()` restores the port's `timeout` attribute when a read raises.

### Changed

- README, `DOCS/INTEGRATION.md` §3.3, §3.4 and §4.5, and `WHY-NOW.md` describe framed receive and the 68-test suite.

### Added

- `TESTS/test_torture.py::TestFramedReceive`: 12 tests covering single and consecutive frames, empty frames, partial frames across timeouts, timeout restoration after a completed read and after a read that raises (unframed and framed), corrupted and undecodable frames followed by a good frame, an overlong frame, a length mismatch, a payload above `max_payload_size`, and the unchanged unframed path.

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
