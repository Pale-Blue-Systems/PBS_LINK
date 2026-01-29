"""
Pale Blue Systems - Reference SDK (v0.1.1 Beta)
Implements: PBS-ENV-01 v1.3 (44-Byte Header)
License: Apache 2.0
Copyright 2026 Pale Blue Systems
"""
import struct
import time
import zlib
import threading
from dataclasses import dataclass
from typing import Optional, Union, Tuple
from enum import IntEnum


# =============================================================================
# Constants
# =============================================================================

# Layout: Magic(B), Prio(B), Flags(B), Pad(x), Seq(H), Pad(xx), Src(16s), Time(Q), Size(I), TTL(I), CRC(I)
HEADER_FORMAT = '>B B B x H xx 16s Q I I I'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 44 Bytes

# Protocol constants
MAGIC_BYTE = 0x10
MAX_PAYLOAD_SIZE_DEFAULT = 65536  # 64KB default, configurable
MAX_SEQUENCE = 65536

# Field offsets (for parsing)
OFFSET_MAGIC = 0x00
OFFSET_PRIORITY = 0x01
OFFSET_FLAGS = 0x02
OFFSET_SEQUENCE = 0x04
OFFSET_SOURCE_ID = 0x08
OFFSET_TIMESTAMP = 0x18
OFFSET_SIZE = 0x20
OFFSET_TTL = 0x24
OFFSET_CRC32 = 0x28


class Priority(IntEnum):
    """PBS Priority Classes (PBS-PRIO-01)"""
    CRITICAL = 0  # Immediate life- or safety-critical data
    HIGH = 1      # Mission-critical operational data
    NORMAL = 2    # Routine mission data
    LOW = 3       # Opportunistic or deferrable data
    BULK = 4      # Non-urgent, high-volume data


class Flags(IntEnum):
    """PBS Envelope Flags"""
    NONE = 0x00
    ACK_REQ = 0x01  # Acknowledgement requested


# =============================================================================
# Exceptions
# =============================================================================

class PBSError(Exception):
    """Base exception for PBS errors"""
    pass


class PBSValidationError(PBSError):
    """Envelope validation failed"""
    pass


class PBSCRCError(PBSValidationError):
    """CRC32 verification failed"""
    pass


class PBSMagicError(PBSValidationError):
    """Invalid magic byte"""
    pass


class PBSPriorityError(PBSValidationError):
    """Invalid priority value"""
    pass


class PBSTTLError(PBSValidationError):
    """TTL expired"""
    pass


class PBSSerialError(PBSError):
    """Serial port communication error"""
    pass


class PBSFramingError(PBSError):
    """Framing/sync error"""
    pass


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class PBSEnvelope:
    """Parsed PBS Envelope"""
    magic: int
    priority: int
    flags: int
    sequence: int
    source_id: str
    timestamp: int
    size: int
    ttl: int
    crc32: int
    payload: bytes
    raw_header: bytes

    @property
    def priority_name(self) -> str:
        """Human-readable priority name"""
        try:
            return Priority(self.priority).name
        except ValueError:
            return f"RESERVED({self.priority})"

    @property
    def ack_requested(self) -> bool:
        """Check if ACK is requested"""
        return bool(self.flags & Flags.ACK_REQ)

    @property
    def timestamp_seconds(self) -> float:
        """Timestamp as Unix seconds"""
        return self.timestamp / 1_000_000


# =============================================================================
# Framing (Optional)
# =============================================================================

class COBSFraming:
    """
    Consistent Overhead Byte Stuffing (COBS) framing.
    Provides packet delimiting for stream transports (serial, TCP).
    Frame format: [COBS-encoded data] [0x00 delimiter]
    """

    @staticmethod
    def encode(data: bytes) -> bytes:
        """Encode data using COBS, append 0x00 delimiter"""
        if not data:
            # Empty data: just a code byte of 1 (0 literal bytes, end of data)
            return bytes([0x01, 0x00])

        output = bytearray()
        idx = 0
        while idx < len(data):
            # Find next zero or end
            block_start = idx
            while idx < len(data) and data[idx] != 0x00 and (idx - block_start) < 254:
                idx += 1
            block_len = idx - block_start
            output.append(block_len + 1)
            output.extend(data[block_start:idx])
            if idx < len(data) and data[idx] == 0x00:
                idx += 1

        # If data ended with a zero, add terminating code byte
        # This tells decoder "no implicit zero after this"
        if data[-1] == 0x00:
            output.append(0x01)

        output.append(0x00)  # Delimiter
        return bytes(output)

    @staticmethod
    def decode(data: bytes) -> bytes:
        """Decode COBS-encoded data (without trailing 0x00 delimiter)"""
        if not data:
            return b""
        output = bytearray()
        idx = 0
        while idx < len(data):
            code = data[idx]
            if code == 0:
                break  # End of frame
            idx += 1
            for _ in range(code - 1):
                if idx >= len(data):
                    raise PBSFramingError("COBS decode error: unexpected end of data")
                output.append(data[idx])
                idx += 1
            if code < 255 and idx < len(data) and data[idx] != 0:
                output.append(0x00)
        return bytes(output)


# =============================================================================
# CRC32 Utilities
# =============================================================================

def calculate_crc32(header_with_zero_crc: bytes) -> int:
    """
    Calculate CRC32 over 44-byte header with CRC field zeroed.
    Uses IEEE 802.3 polynomial (standard zlib.crc32).
    """
    if len(header_with_zero_crc) != HEADER_SIZE:
        raise ValueError(f"Header must be {HEADER_SIZE} bytes, got {len(header_with_zero_crc)}")
    return zlib.crc32(header_with_zero_crc) & 0xFFFFFFFF


def verify_crc32(header: bytes) -> bool:
    """
    Verify CRC32 of a 44-byte header.
    Returns True if valid, False if corrupted.
    """
    if len(header) != HEADER_SIZE:
        return False
    # Extract embedded CRC
    embedded_crc = struct.unpack('>I', header[OFFSET_CRC32:OFFSET_CRC32 + 4])[0]
    # Zero the CRC field and recalculate
    header_zeroed = header[:OFFSET_CRC32] + b'\x00\x00\x00\x00'
    calculated_crc = calculate_crc32(header_zeroed)
    return embedded_crc == calculated_crc


# =============================================================================
# Main SDK Class
# =============================================================================

class PBSLink:
    """
    PBS-LINK Reference SDK

    Implements PBS-ENV-01 v1.3 for sending and receiving PBS envelopes.
    Thread-safe, with optional COBS framing for stream transports.

    Example:
        link = PBSLink(device_id="Rover-Alpha")

        # Send critical alert
        link.send(Priority.CRITICAL, "EMERGENCY: Motor stall", ttl=0, require_ack=True)

        # Parse received data
        envelope = link.parse(received_bytes)
        print(f"From: {envelope.source_id}, Priority: {envelope.priority_name}")
    """

    def __init__(
        self,
        device_id: str,
        serial_port=None,
        max_payload_size: int = MAX_PAYLOAD_SIZE_DEFAULT,
        use_framing: bool = False,
        clock_source=None
    ):
        """
        Initialize PBSLink.

        Args:
            device_id: 16-character device identifier (truncated if longer)
            serial_port: Optional serial port object with read()/write() methods
            max_payload_size: Maximum allowed payload size in bytes (default 64KB)
            use_framing: If True, use COBS framing for packet delimiting
            clock_source: Optional callable returning Unix timestamp in seconds
                         (default: time.time). Use for custom clocks (GPS, MET).
        """
        self.device_id = str(device_id)[:16]
        self.serial_port = serial_port
        self.max_payload_size = max_payload_size
        self.use_framing = use_framing
        self.clock_source = clock_source or time.time

        self._sequence = 0
        self._sequence_lock = threading.Lock()
        self._receive_buffer = bytearray()

    def _get_next_sequence(self) -> int:
        """Thread-safe sequence number generation"""
        with self._sequence_lock:
            self._sequence = (self._sequence + 1) % MAX_SEQUENCE
            return self._sequence

    @property
    def sequence(self) -> int:
        """Current sequence number (for testing)"""
        return self._sequence

    @sequence.setter
    def sequence(self, value: int):
        """Set sequence number (for testing)"""
        with self._sequence_lock:
            self._sequence = value % MAX_SEQUENCE

    def send(
        self,
        priority: int,
        payload: Union[str, bytes],
        ttl: int = 0,
        require_ack: bool = False
    ) -> Union[bytes, int]:
        """
        Build and send a PBS envelope.

        Args:
            priority: Priority class (0-4 or Priority enum)
            payload: Message payload (str or bytes)
            ttl: Time-to-live in seconds (0 = never expires)
            require_ack: If True, set ACK_REQ flag

        Returns:
            If serial_port is set: number of bytes written
            If serial_port is None: raw packet bytes (for testing)

        Raises:
            ValueError: Invalid priority or payload
            PBSSerialError: Serial port write failed
        """
        # Input validation
        if isinstance(payload, str):
            data = payload.encode('utf-8')
        elif isinstance(payload, bytes):
            data = payload
        else:
            raise ValueError(f"Payload must be str or bytes, got {type(payload)}")

        if not (0 <= priority <= 4):
            raise ValueError("Priority must be 0-4 (CRITICAL=0, HIGH=1, NORMAL=2, LOW=3, BULK=4)")

        if len(data) > self.max_payload_size:
            raise ValueError(f"Payload size {len(data)} exceeds maximum {self.max_payload_size}")

        if ttl < 0:
            raise ValueError("TTL must be non-negative")

        # Build envelope
        sequence = self._get_next_sequence()
        src = self.device_id.encode('utf-8')[:16].ljust(16, b'\0')
        timestamp = int(self.clock_source() * 1_000_000)
        flags = Flags.ACK_REQ if require_ack else Flags.NONE

        # Build header with CRC32 = 0
        pre_header = struct.pack(
            HEADER_FORMAT,
            MAGIC_BYTE, priority, flags, sequence,
            src, timestamp, len(data), int(ttl), 0
        )

        # Calculate CRC32 over all 44 bytes (with CRC field zeroed)
        checksum = calculate_crc32(pre_header)

        # Final header with CRC32
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC_BYTE, priority, flags, sequence,
            src, timestamp, len(data), int(ttl), checksum
        )

        packet = header + data

        # Apply framing if enabled
        if self.use_framing:
            packet = COBSFraming.encode(packet)

        # Send or return
        if self.serial_port:
            try:
                bytes_written = self.serial_port.write(packet)
                return bytes_written if bytes_written is not None else len(packet)
            except Exception as e:
                raise PBSSerialError(f"Serial write failed: {e}") from e
        else:
            return packet

    def parse(
        self,
        data: bytes,
        validate_crc: bool = True,
        validate_priority: bool = True,
        check_ttl: bool = False,
        current_time: Optional[float] = None
    ) -> PBSEnvelope:
        """
        Parse a PBS envelope from raw bytes.

        Args:
            data: Raw packet bytes (header + payload)
            validate_crc: If True, verify CRC32 (raises PBSCRCError if invalid)
            validate_priority: If True, reject reserved priority values 5-255
            check_ttl: If True, verify TTL hasn't expired (requires timestamp comparison)
            current_time: Current time for TTL check (default: now)

        Returns:
            PBSEnvelope with parsed fields

        Raises:
            PBSValidationError: Validation failed (CRC, magic, priority, TTL)
        """
        # Remove framing if present
        if self.use_framing and data and data[-1] == 0x00:
            try:
                data = COBSFraming.decode(data[:-1])
            except PBSFramingError:
                pass  # Try parsing anyway

        if len(data) < HEADER_SIZE:
            raise PBSValidationError(f"Data too short: {len(data)} bytes, need at least {HEADER_SIZE}")

        header = data[:HEADER_SIZE]

        # 1. Magic validation
        magic = header[OFFSET_MAGIC]
        if magic != MAGIC_BYTE:
            raise PBSMagicError(f"Invalid magic byte: 0x{magic:02X}, expected 0x{MAGIC_BYTE:02X}")

        # 2. CRC32 validation
        if validate_crc and not verify_crc32(header):
            raise PBSCRCError("CRC32 verification failed - data corrupted")

        # 3. Unpack header
        unpacked = struct.unpack(HEADER_FORMAT, header)
        magic, priority, flags, sequence, source_id_bytes, timestamp, size, ttl, crc32 = unpacked

        # 4. Priority validation
        if validate_priority and priority > 4:
            raise PBSPriorityError(f"Reserved priority value: {priority}")

        # 5. Extract payload
        if len(data) < HEADER_SIZE + size:
            raise PBSValidationError(f"Incomplete payload: expected {size} bytes, got {len(data) - HEADER_SIZE}")

        payload = data[HEADER_SIZE:HEADER_SIZE + size]

        # 6. TTL check (optional)
        if check_ttl and ttl > 0:
            current = current_time or time.time()
            message_time = timestamp / 1_000_000
            age = current - message_time
            if age > ttl:
                raise PBSTTLError(f"TTL expired: message age {age:.1f}s > TTL {ttl}s")

        # 7. Decode source ID
        source_id = source_id_bytes.rstrip(b'\x00').decode('utf-8', errors='replace')

        return PBSEnvelope(
            magic=magic,
            priority=priority,
            flags=flags,
            sequence=sequence,
            source_id=source_id,
            timestamp=timestamp,
            size=size,
            ttl=ttl,
            crc32=crc32,
            payload=payload,
            raw_header=header
        )

    def receive(self, timeout: Optional[float] = None) -> Optional[PBSEnvelope]:
        """
        Receive and parse a PBS envelope from serial port.

        Args:
            timeout: Read timeout in seconds (None = blocking)

        Returns:
            PBSEnvelope if successful, None if timeout or incomplete

        Raises:
            PBSSerialError: Serial read failed
            PBSValidationError: Received data failed validation
        """
        if not self.serial_port:
            raise PBSError("No serial port configured")

        try:
            # Read header
            if hasattr(self.serial_port, 'timeout'):
                old_timeout = self.serial_port.timeout
                self.serial_port.timeout = timeout

            header_data = self.serial_port.read(HEADER_SIZE)

            if hasattr(self.serial_port, 'timeout'):
                self.serial_port.timeout = old_timeout

            if len(header_data) < HEADER_SIZE:
                return None  # Timeout or incomplete

            # Validate magic before reading more
            if header_data[OFFSET_MAGIC] != MAGIC_BYTE:
                raise PBSMagicError(f"Invalid magic: 0x{header_data[OFFSET_MAGIC]:02X}")

            # Extract payload size
            size = struct.unpack('>I', header_data[OFFSET_SIZE:OFFSET_SIZE + 4])[0]

            if size > self.max_payload_size:
                raise PBSValidationError(f"Payload size {size} exceeds maximum {self.max_payload_size}")

            # Read payload
            payload_data = b''
            if size > 0:
                payload_data = self.serial_port.read(size)
                if len(payload_data) < size:
                    return None  # Incomplete

            return self.parse(header_data + payload_data)

        except PBSError:
            raise
        except Exception as e:
            raise PBSSerialError(f"Serial read failed: {e}") from e

    def find_sync(self, data: bytes) -> Tuple[int, Optional[bytes]]:
        """
        Find the start of a valid PBS envelope in a byte stream.
        Useful for resynchronizing after data loss.

        Args:
            data: Byte buffer to search

        Returns:
            Tuple of (offset, remaining_data) where offset is position of
            first valid envelope, or (-1, data) if none found.
        """
        for i in range(len(data) - HEADER_SIZE + 1):
            if data[i] == MAGIC_BYTE:
                # Check if we have enough data for a header
                if i + HEADER_SIZE <= len(data):
                    header = data[i:i + HEADER_SIZE]
                    if verify_crc32(header):
                        return (i, data[i:])
        return (-1, data)


# =============================================================================
# Convenience Functions
# =============================================================================

def build_envelope(
    source_id: str,
    priority: int,
    payload: Union[str, bytes],
    ttl: int = 0,
    sequence: int = 0,
    require_ack: bool = False
) -> bytes:
    """
    Standalone function to build a PBS envelope.

    For simple use cases where a full PBSLink instance isn't needed.
    """
    link = PBSLink(device_id=source_id)
    link.sequence = sequence - 1  # Will be incremented by send()
    return link.send(priority, payload, ttl=ttl, require_ack=require_ack)


def parse_envelope(data: bytes, validate: bool = True) -> PBSEnvelope:
    """
    Standalone function to parse a PBS envelope.

    For simple use cases where a full PBSLink instance isn't needed.
    """
    link = PBSLink(device_id="parser")
    return link.parse(data, validate_crc=validate, validate_priority=validate)
