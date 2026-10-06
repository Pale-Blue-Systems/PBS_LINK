"""
PBS_LINK Torture Tests
Validates PBS-ENV-01 v1.3 conformance

Run with: python -m pytest TESTS/test_torture.py -v
"""
import unittest
import struct
import zlib
import time
import threading
from io import BytesIO

from PBS_LINK import (
    PBSLink,
    PBSEnvelope,
    Priority,
    Flags,
    PBSError,
    PBSValidationError,
    PBSCRCError,
    PBSMagicError,
    PBSPriorityError,
    PBSTTLError,
    PBSSerialError,
    PBSFramingError,
    COBSFraming,
    calculate_crc32,
    verify_crc32,
    build_envelope,
    parse_envelope,
    HEADER_FORMAT,
    HEADER_SIZE,
    MAGIC_BYTE,
)


class TestHeaderStructure(unittest.TestCase):
    """Test PBS-ENV-01 v1.3 header structure"""

    def setUp(self):
        self.link = PBSLink(device_id="TEST_UNIT")

    def test_header_size_constant(self):
        """HEADER_SIZE must be 44 bytes"""
        self.assertEqual(HEADER_SIZE, 44)

    def test_header_size_actual(self):
        """Actual header must be 44 bytes"""
        packet = self.link.send(0, "test")
        self.assertEqual(len(packet[:44]), 44)

    def test_struct_format_size(self):
        """Struct format must produce 44 bytes"""
        self.assertEqual(struct.calcsize(HEADER_FORMAT), 44)

    def test_magic_byte_position(self):
        """Magic byte at offset 0x00"""
        packet = self.link.send(0, "test")
        self.assertEqual(packet[0x00], MAGIC_BYTE)

    def test_priority_position(self):
        """Priority at offset 0x01"""
        packet = self.link.send(3, "test")
        self.assertEqual(packet[0x01], 3)

    def test_flags_position(self):
        """Flags at offset 0x02"""
        packet = self.link.send(0, "test", require_ack=True)
        self.assertEqual(packet[0x02], Flags.ACK_REQ)

    def test_sequence_position(self):
        """Sequence at offset 0x04 (big-endian u16)"""
        self.link.sequence = 0x1234 - 1
        packet = self.link.send(0, "test")
        seq = struct.unpack('>H', packet[0x04:0x06])[0]
        self.assertEqual(seq, 0x1234)

    def test_source_id_position(self):
        """Source ID at offset 0x08 (16 bytes)"""
        link = PBSLink(device_id="ABCDEFGH")
        packet = link.send(0, "test")
        source_id = packet[0x08:0x18]
        self.assertEqual(source_id[:8], b"ABCDEFGH")
        self.assertEqual(source_id[8:], b"\x00" * 8)

    def test_timestamp_position(self):
        """Timestamp at offset 0x18 (big-endian u64)"""
        packet = self.link.send(0, "test")
        timestamp = struct.unpack('>Q', packet[0x18:0x20])[0]
        # Should be within last minute (in microseconds)
        now_us = int(time.time() * 1_000_000)
        self.assertLess(abs(timestamp - now_us), 60_000_000)

    def test_size_position(self):
        """Size at offset 0x20 (big-endian u32)"""
        packet = self.link.send(0, "ABCD")  # 4 bytes
        size = struct.unpack('>I', packet[0x20:0x24])[0]
        self.assertEqual(size, 4)

    def test_ttl_position(self):
        """TTL at offset 0x24 (big-endian u32)"""
        packet = self.link.send(0, "test", ttl=3600)
        ttl = struct.unpack('>I', packet[0x24:0x28])[0]
        self.assertEqual(ttl, 3600)

    def test_crc32_position(self):
        """CRC32 at offset 0x28 (big-endian u32)"""
        packet = self.link.send(0, "test")
        crc = struct.unpack('>I', packet[0x28:0x2C])[0]
        self.assertIsInstance(crc, int)
        self.assertGreater(crc, 0)


class TestCRC32(unittest.TestCase):
    """Test CRC32 calculation and verification"""

    def setUp(self):
        self.link = PBSLink(device_id="CRC_TEST")

    def test_crc32_valid(self):
        """CRC32 verification should pass for valid packets"""
        packet = self.link.send(1, "integrity")
        header = packet[:44]
        self.assertTrue(verify_crc32(header))

    def test_crc32_bitflip_detected(self):
        """CRC32 should detect single bit-flip"""
        packet = self.link.send(1, "radiation")
        header = bytearray(packet[:44])

        # Flip a bit in Priority field
        header[1] ^= 0x01

        self.assertFalse(verify_crc32(bytes(header)))

    def test_crc32_calculation(self):
        """CRC32 calculated over 44 bytes with CRC field zeroed"""
        packet = self.link.send(1, "test")
        header = packet[:44]

        # Extract embedded CRC
        embedded_crc = struct.unpack('>I', header[40:44])[0]

        # Zero the CRC field and recalculate
        header_zeroed = header[:40] + b'\x00\x00\x00\x00'
        calculated_crc = calculate_crc32(header_zeroed)

        self.assertEqual(embedded_crc, calculated_crc)

    def test_crc32_wrong_size_rejected(self):
        """calculate_crc32 should reject non-44-byte input"""
        with self.assertRaises(ValueError):
            calculate_crc32(b"too short")


class TestPriority(unittest.TestCase):
    """Test priority validation"""

    def setUp(self):
        self.link = PBSLink(device_id="PRIO_TEST")

    def test_priority_valid_range(self):
        """Priority values 0-4 should be accepted"""
        for priority in range(5):
            packet = self.link.send(priority, f"priority {priority}")
            self.assertEqual(packet[1], priority)

    def test_priority_invalid_rejected(self):
        """Priority values 5-255 should be rejected"""
        for priority in [5, 100, 255]:
            with self.assertRaises(ValueError):
                self.link.send(priority, "invalid")

    def test_priority_enum(self):
        """Priority enum values should work"""
        packet = self.link.send(Priority.CRITICAL, "critical")
        self.assertEqual(packet[1], 0)

        packet = self.link.send(Priority.BULK, "bulk")
        self.assertEqual(packet[1], 4)


class TestSequence(unittest.TestCase):
    """Test sequence number handling"""

    def setUp(self):
        self.link = PBSLink(device_id="SEQ_TEST")

    def test_sequence_increments(self):
        """Sequence should increment with each send"""
        self.link.sequence = 0
        self.link.send(0, "first")
        self.assertEqual(self.link.sequence, 1)
        self.link.send(0, "second")
        self.assertEqual(self.link.sequence, 2)

    def test_sequence_rollover(self):
        """Sequence should roll over from 65535 to 0"""
        self.link.sequence = 65535
        packet = self.link.send(0, "rollover")
        seq = struct.unpack('>H', packet[4:6])[0]
        self.assertEqual(seq, 0)
        self.assertEqual(self.link.sequence, 0)

    def test_sequence_thread_safety(self):
        """Sequence generation should be thread-safe"""
        sequences = []
        errors = []

        def send_many():
            try:
                for _ in range(100):
                    packet = self.link.send(0, "threaded")
                    seq = struct.unpack('>H', packet[4:6])[0]
                    sequences.append(seq)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=send_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        # All sequences should be unique
        self.assertEqual(len(sequences), len(set(sequences)))


class TestSourceID(unittest.TestCase):
    """Test Source ID handling"""

    def test_source_id_truncation(self):
        """Source ID longer than 16 bytes should be truncated"""
        link = PBSLink(device_id="ThisIsAVeryLongDeviceNameThatExceeds16Bytes")
        packet = link.send(0, "test")
        source_id = packet[0x08:0x18]
        self.assertEqual(len(source_id), 16)
        self.assertEqual(source_id, b"ThisIsAVeryLongD")

    def test_source_id_padding(self):
        """Source ID shorter than 16 bytes should be null-padded"""
        link = PBSLink(device_id="Short")
        packet = link.send(0, "test")
        source_id = packet[0x08:0x18]
        self.assertEqual(source_id, b"Short" + b"\x00" * 11)

    def test_source_id_exact_16(self):
        """Source ID exactly 16 bytes should not be modified"""
        link = PBSLink(device_id="Exactly16Bytes!!")
        packet = link.send(0, "test")
        source_id = packet[0x08:0x18]
        self.assertEqual(source_id, b"Exactly16Bytes!!")


class TestPayload(unittest.TestCase):
    """Test payload handling"""

    def setUp(self):
        self.link = PBSLink(device_id="PAYLOAD_TEST")

    def test_empty_payload(self):
        """Empty payload (Size=0) should be valid"""
        packet = self.link.send(2, b"")
        size = struct.unpack('>I', packet[0x20:0x24])[0]
        self.assertEqual(size, 0)
        self.assertEqual(len(packet), 44)

    def test_string_payload(self):
        """String payload should be UTF-8 encoded"""
        packet = self.link.send(0, "Hello")
        self.assertEqual(packet[44:], b"Hello")

    def test_bytes_payload(self):
        """Bytes payload should be preserved"""
        data = b"\x00\x01\x02\x03"
        packet = self.link.send(0, data)
        self.assertEqual(packet[44:], data)

    def test_max_payload_size(self):
        """Payload exceeding max size should be rejected"""
        link = PBSLink(device_id="TEST", max_payload_size=100)
        with self.assertRaises(ValueError):
            link.send(0, b"x" * 101)

    def test_payload_with_zeros(self):
        """Payload containing null bytes should work"""
        data = b"hello\x00world\x00"
        packet = self.link.send(0, data)
        self.assertEqual(packet[44:], data)


class TestFlags(unittest.TestCase):
    """Test flags handling"""

    def setUp(self):
        self.link = PBSLink(device_id="FLAGS_TEST")

    def test_ack_flag_off(self):
        """ACK flag should be 0x00 when not requested"""
        packet = self.link.send(0, "test", require_ack=False)
        self.assertEqual(packet[2], 0x00)

    def test_ack_flag_on(self):
        """ACK flag should be 0x01 when requested"""
        packet = self.link.send(0, "test", require_ack=True)
        self.assertEqual(packet[2], 0x01)


class TestTTL(unittest.TestCase):
    """Test TTL handling"""

    def setUp(self):
        self.link = PBSLink(device_id="TTL_TEST")

    def test_ttl_zero(self):
        """TTL=0 should mean never expires"""
        packet = self.link.send(0, "test", ttl=0)
        ttl = struct.unpack('>I', packet[0x24:0x28])[0]
        self.assertEqual(ttl, 0)

    def test_ttl_positive(self):
        """Positive TTL should be preserved"""
        packet = self.link.send(0, "test", ttl=3600)
        ttl = struct.unpack('>I', packet[0x24:0x28])[0]
        self.assertEqual(ttl, 3600)

    def test_ttl_negative_rejected(self):
        """Negative TTL should be rejected"""
        with self.assertRaises(ValueError):
            self.link.send(0, "test", ttl=-1)


class TestParsing(unittest.TestCase):
    """Test envelope parsing"""

    def setUp(self):
        self.link = PBSLink(device_id="PARSE_TEST")

    def test_parse_valid_packet(self):
        """Valid packet should parse successfully"""
        packet = self.link.send(Priority.HIGH, "test message", ttl=60, require_ack=True)
        envelope = self.link.parse(packet)

        self.assertEqual(envelope.magic, MAGIC_BYTE)
        self.assertEqual(envelope.priority, Priority.HIGH)
        self.assertEqual(envelope.flags, Flags.ACK_REQ)
        self.assertEqual(envelope.source_id, "PARSE_TEST")
        self.assertEqual(envelope.ttl, 60)
        self.assertEqual(envelope.payload, b"test message")
        self.assertTrue(envelope.ack_requested)
        self.assertEqual(envelope.priority_name, "HIGH")

    def test_parse_invalid_magic(self):
        """Invalid magic byte should raise PBSMagicError"""
        packet = bytearray(self.link.send(0, "test"))
        packet[0] = 0xFF  # Invalid magic
        with self.assertRaises(PBSMagicError):
            self.link.parse(bytes(packet))

    def test_parse_invalid_crc(self):
        """Invalid CRC should raise PBSCRCError"""
        packet = bytearray(self.link.send(0, "test"))
        packet[1] ^= 0x01  # Corrupt priority (doesn't update CRC)
        with self.assertRaises(PBSCRCError):
            self.link.parse(bytes(packet))

    def test_parse_invalid_priority(self):
        """Reserved priority should raise PBSPriorityError"""
        packet = bytearray(self.link.send(0, "test"))
        packet[1] = 5  # Reserved priority
        # Recalculate CRC
        packet[40:44] = b'\x00\x00\x00\x00'
        crc = zlib.crc32(bytes(packet[:44])) & 0xFFFFFFFF
        packet[40:44] = struct.pack('>I', crc)
        with self.assertRaises(PBSPriorityError):
            self.link.parse(bytes(packet))

    def test_parse_too_short(self):
        """Data shorter than header should raise PBSValidationError"""
        with self.assertRaises(PBSValidationError):
            self.link.parse(b"too short")

    def test_parse_incomplete_payload(self):
        """Incomplete payload should raise PBSValidationError"""
        packet = self.link.send(0, "hello world")
        truncated = packet[:48]  # Header + partial payload
        with self.assertRaises(PBSValidationError):
            self.link.parse(truncated)

    def test_parse_ttl_expired(self):
        """Expired TTL should raise PBSTTLError when check_ttl=True"""
        # Create packet with TTL=1 and old timestamp
        link = PBSLink(device_id="TTL_TEST", clock_source=lambda: time.time() - 100)
        packet = link.send(0, "old message", ttl=1)

        # Parse with TTL checking
        with self.assertRaises(PBSTTLError):
            self.link.parse(packet, check_ttl=True)

    def test_parse_without_validation(self):
        """Parsing without validation should skip checks"""
        packet = bytearray(self.link.send(0, "test"))
        packet[1] ^= 0x01  # Corrupt
        # Should not raise
        envelope = self.link.parse(bytes(packet), validate_crc=False, validate_priority=False)
        self.assertIsInstance(envelope, PBSEnvelope)


class TestCOBSFraming(unittest.TestCase):
    """Test COBS framing for stream transports"""

    def test_cobs_roundtrip(self):
        """COBS encode/decode should be lossless"""
        data = b"Hello\x00World\x00\x00Test"
        encoded = COBSFraming.encode(data)
        decoded = COBSFraming.decode(encoded[:-1])  # Remove delimiter
        self.assertEqual(decoded, data)

    def test_cobs_no_zeros(self):
        """Data without zeros should encode correctly"""
        data = b"NoZerosHere"
        encoded = COBSFraming.encode(data)
        decoded = COBSFraming.decode(encoded[:-1])
        self.assertEqual(decoded, data)

    def test_cobs_all_zeros(self):
        """All-zero data should encode correctly"""
        data = b"\x00\x00\x00"
        encoded = COBSFraming.encode(data)
        decoded = COBSFraming.decode(encoded[:-1])
        self.assertEqual(decoded, data)

    def test_cobs_zero_after_full_block(self):
        """A 0x00 after a full 254-byte block (code 0xFF) must survive"""
        for run in (253, 254, 255, 508, 762):
            for tail in (b"", b"\x00", b"\x00\x07", b"\x07"):
                data = bytes([0x01]) * run + tail
                encoded = COBSFraming.encode(data)
                self.assertNotIn(0x00, encoded[:-1])
                self.assertEqual(COBSFraming.decode(encoded[:-1]), data)

    def test_framed_send_parse(self):
        """Framing should work end-to-end"""
        link = PBSLink(device_id="FRAMED", use_framing=True)
        packet = link.send(0, "test")
        # Packet should end with 0x00 delimiter
        self.assertEqual(packet[-1], 0x00)
        # Should parse correctly
        envelope = link.parse(packet)
        self.assertEqual(envelope.payload, b"test")


class ChunkedPort:
    """Serial-port stand-in that returns at most the bytes queued so far.

    read() returns b"" when nothing is queued, as a timed-out serial read
    does. feed() queues more bytes.
    """

    def __init__(self, data=b""):
        self._data = bytearray(data)
        self.timeout = 5.0

    def feed(self, data):
        self._data.extend(data)

    def read(self, n):
        out = bytes(self._data[:n])
        del self._data[:n]
        return out


class TestFramedReceive(unittest.TestCase):
    """receive() with use_framing=True"""

    def frames(self, *payloads):
        tx = PBSLink(device_id="TX", use_framing=True)
        return [tx.send(2, p) for p in payloads]

    def test_receive_single_frame(self):
        frame, = self.frames(b"hello")
        rx = PBSLink(device_id="RX", serial_port=BytesIO(frame), use_framing=True)
        env = rx.receive()
        self.assertEqual(env.payload, b"hello")
        self.assertEqual(env.source_id, "TX")
        self.assertIsNone(rx.receive())

    def test_receive_consecutive_frames_in_order(self):
        payloads = [b"a", b"\x00" * 5, bytes([1]) * 254 + b"\x00\x07", b"", b"end\x00"]
        stream = b"".join(self.frames(*payloads))
        rx = PBSLink(device_id="RX", serial_port=BytesIO(stream), use_framing=True)
        for p in payloads:
            self.assertEqual(rx.receive().payload, p)
        self.assertIsNone(rx.receive())

    def test_empty_frames_are_skipped(self):
        frame, = self.frames(b"x")
        rx = PBSLink(device_id="RX", serial_port=BytesIO(b"\x00\x00" + frame), use_framing=True)
        self.assertEqual(rx.receive().payload, b"x")

    def test_partial_frame_is_kept_across_timeouts(self):
        frame, = self.frames(b"split across reads")
        port = ChunkedPort(frame[:20])
        rx = PBSLink(device_id="RX", serial_port=port, use_framing=True)
        self.assertIsNone(rx.receive(timeout=0.1))
        port.feed(frame[20:])
        self.assertEqual(rx.receive(timeout=0.1).payload, b"split across reads")

    def test_timeout_attribute_is_restored(self):
        frame, = self.frames(b"t")
        port = ChunkedPort(frame)
        rx = PBSLink(device_id="RX", serial_port=port, use_framing=True)
        rx.receive(timeout=0.25)
        self.assertEqual(port.timeout, 5.0)

    def test_corrupted_frame_raises_then_next_frame_parses(self):
        bad, good = self.frames(b"corrupt me", b"good")
        bad = bytearray(bad)
        bad[10] ^= 0x01  # inside the Source ID; never creates or removes a 0x00
        self.assertNotIn(0x00, bad[:-1])
        rx = PBSLink(device_id="RX", serial_port=BytesIO(bytes(bad) + good), use_framing=True)
        with self.assertRaises(PBSCRCError):
            rx.receive()
        self.assertEqual(rx.receive().payload, b"good")

    def test_undecodable_frame_raises_framing_error(self):
        good, = self.frames(b"after")
        rx = PBSLink(device_id="RX", serial_port=BytesIO(b"\x05\x01\x00" + good), use_framing=True)
        with self.assertRaises(PBSFramingError):
            rx.receive()
        self.assertEqual(rx.receive().payload, b"after")

    def test_overlong_frame_raises_then_resynchronizes(self):
        good, = self.frames(b"ok")
        rx = PBSLink(device_id="RX", serial_port=None, max_payload_size=64, use_framing=True)
        limit = rx._max_encoded_frame_length()
        rx.serial_port = BytesIO(b"\x01" * (limit + 5) + b"\x00" + good)
        with self.assertRaises(PBSFramingError):
            rx.receive()
        self.assertEqual(rx.receive().payload, b"ok")

    def test_trailing_bytes_after_envelope_are_rejected(self):
        tx = PBSLink(device_id="TX")
        envelope = tx.send(1, b"abc") + b"\xAA"  # one byte more than Size
        frame = COBSFraming.encode(envelope)
        rx = PBSLink(device_id="RX", serial_port=BytesIO(frame), use_framing=True)
        with self.assertRaises(PBSValidationError):
            rx.receive()

    def test_payload_above_maximum_is_rejected(self):
        # 301-byte payload against a 300-byte maximum. The 0x00 keeps the
        # encoded frame within the delimiter search limit, so the frame is
        # decoded and the Size check, not the overlong-frame check, rejects it.
        frame, = self.frames(b"x" * 200 + b"\x00" + b"x" * 100)
        rx = PBSLink(device_id="RX", serial_port=BytesIO(frame), max_payload_size=300, use_framing=True)
        self.assertLessEqual(len(frame) - 1, rx._max_encoded_frame_length())
        with self.assertRaises(PBSValidationError) as cm:
            rx.receive()
        self.assertIn("exceeds maximum", str(cm.exception))

    def test_timeout_restored_when_read_raises(self):
        class RaisingPort:
            timeout = 5.0

            def read(self, n):
                raise OSError("read failed")

        for use_framing in (False, True):
            with self.subTest(use_framing=use_framing):
                port = RaisingPort()
                rx = PBSLink(device_id="RX", serial_port=port, use_framing=use_framing)
                with self.assertRaises(PBSSerialError):
                    rx.receive(timeout=0.25)
                self.assertEqual(port.timeout, 5.0)

    def test_unframed_receive_unchanged(self):
        packet = PBSLink(device_id="TX").send(0, b"raw")
        rx = PBSLink(device_id="RX", serial_port=BytesIO(packet))
        self.assertEqual(rx.receive().payload, b"raw")


class TestClockSource(unittest.TestCase):
    """Test custom clock source"""

    def test_custom_clock(self):
        """Custom clock source should be used for timestamp"""
        fixed_time = 1234567890.123456
        link = PBSLink(device_id="CLOCK_TEST", clock_source=lambda: fixed_time)
        packet = link.send(0, "test")
        timestamp = struct.unpack('>Q', packet[0x18:0x20])[0]
        expected = int(fixed_time * 1_000_000)
        self.assertEqual(timestamp, expected)


class TestConvenienceFunctions(unittest.TestCase):
    """Test standalone convenience functions"""

    def test_build_envelope(self):
        """build_envelope should create valid packet"""
        packet = build_envelope("MyDevice", Priority.NORMAL, "payload", ttl=30)
        self.assertEqual(len(packet), 44 + 7)  # Header + "payload"
        self.assertTrue(verify_crc32(packet[:44]))

    def test_parse_envelope(self):
        """parse_envelope should parse valid packet"""
        packet = build_envelope("MyDevice", Priority.NORMAL, "payload")
        envelope = parse_envelope(packet)
        self.assertEqual(envelope.source_id, "MyDevice")
        self.assertEqual(envelope.priority, Priority.NORMAL)
        self.assertEqual(envelope.payload, b"payload")


class TestSerialPort(unittest.TestCase):
    """Test serial port integration"""

    def test_send_to_mock_serial(self):
        """Send should write to serial port"""
        mock_serial = BytesIO()
        link = PBSLink(device_id="SERIAL_TEST", serial_port=mock_serial)
        result = link.send(0, "test")
        self.assertEqual(result, 48)  # 44 header + 4 payload
        mock_serial.seek(0)
        self.assertEqual(len(mock_serial.read()), 48)

    def test_serial_error_handling(self):
        """Serial errors should raise PBSSerialError"""
        class FailingSerial:
            def write(self, data):
                raise IOError("Write failed")

        link = PBSLink(device_id="FAIL_TEST", serial_port=FailingSerial())
        with self.assertRaises(PBSSerialError):
            link.send(0, "test")


class TestFindSync(unittest.TestCase):
    """Test stream resynchronization"""

    def test_find_sync_at_start(self):
        """Should find sync at start of valid packet"""
        link = PBSLink(device_id="SYNC_TEST")
        packet = link.send(0, "test")
        offset, data = link.find_sync(packet)
        self.assertEqual(offset, 0)

    def test_find_sync_with_garbage(self):
        """Should find sync after garbage bytes"""
        link = PBSLink(device_id="SYNC_TEST")
        packet = link.send(0, "test")
        garbage = b"\xFF\xFE\xFD\xFC\xFB"
        stream = garbage + packet
        offset, data = link.find_sync(stream)
        self.assertEqual(offset, 5)

    def test_find_sync_no_valid(self):
        """Should return -1 if no valid packet found"""
        link = PBSLink(device_id="SYNC_TEST")
        garbage = b"\xFF" * 100
        offset, data = link.find_sync(garbage)
        self.assertEqual(offset, -1)


if __name__ == '__main__':
    unittest.main()
