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

    def test_framed_send_parse(self):
        """Framing should work end-to-end"""
        link = PBSLink(device_id="FRAMED", use_framing=True)
        packet = link.send(0, "test")
        # Packet should end with 0x00 delimiter
        self.assertEqual(packet[-1], 0x00)
        # Should parse correctly
        envelope = link.parse(packet)
        self.assertEqual(envelope.payload, b"test")


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
