"""
Pale Blue Systems - Reference SDK (v0.1.4 Beta)
Implements: PBS-ENV-01 v1.5 (44-Byte Header)
License: Apache 2.0
Copyright 2026 Pale Blue Systems Foundation
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
            # Code 0xFF (a full 254-byte block) carries no implicit zero, so
            # a 0x00 that follows it starts the next block and is not consumed.
            if block_len < 254 and idx < len(data) and data[idx] == 0x00:
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
    PBS_LINK Reference SDK

    Implements PBS-ENV-01 v1.5 for sending and receiving PBS envelopes.
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
            device_id: Source identifier. The first 16 characters are encoded
                       as UTF-8 and truncated to 16 bytes (Source ID field).
            serial_port: Optional object with write() (and read() for
                         receive()). If None, send() returns the packet bytes.
            max_payload_size: Maximum allowed payload size in bytes
                              (default 65536)
            use_framing: If True, use COBS framing for packet delimiting
            clock_source: Optional callable returning Unix time in seconds
                         (default: time.time). PBS-ENV-01 defines Timestamp
                         as Unix epoch time; convert other time scales
                         (GPS time, mission elapsed time) before returning.
        """
        self.device_id = str(device_id)[:16]
        self.serial_port = serial_port
        self.max_payload_size = max_payload_size
        self.use_framing = use_framing
        self.clock_source = clock_source or time.time

        self._sequence = 0
        self._sequence_lock = threading.Lock()
        self._receive_buffer = bytearray()
        self._discard_to_delimiter = False

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
            check_ttl: If True, raise PBSTTLError when the envelope has expired
                       (PBS-ENV-01 Section 12.2). An envelope with TTL 0
                       never expires.
            current_time: Unix time in seconds for the TTL check
                          (default: clock_source())

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

        return self._parse_unframed(
            data,
            validate_crc=validate_crc,
            validate_priority=validate_priority,
            check_ttl=check_ttl,
            current_time=current_time,
        )

    def _parse_unframed(
        self,
        data: bytes,
        validate_crc: bool = True,
        validate_priority: bool = True,
        check_ttl: bool = False,
        current_time: Optional[float] = None
    ) -> PBSEnvelope:
        """Parse an envelope that carries no COBS framing."""
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

        # 6. TTL check (optional). PBS-ENV-01 Section 12.2 applies when
        # TTL > 0; an envelope with TTL 0 never expires (Section 12.1).
        if check_ttl and ttl > 0:
            current = self.clock_source() if current_time is None else current_time
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

    def receive(
        self,
        timeout: Optional[float] = None,
        check_ttl: bool = True
    ) -> Optional[PBSEnvelope]:
        """
        Receive and parse one PBS envelope from serial_port.

        Unframed (use_framing=False): reads the 44-byte header, checks Magic
        and Size, reads Size payload bytes and parses the envelope.

        Framed (use_framing=True): reads until a 0x00 delimiter, COBS-decodes
        the frame and parses it. Bytes read past the delimiter, and a partial
        frame left by a timeout, are kept for the next call. Empty frames
        (consecutive delimiters) are skipped. A frame that fails decoding or
        validation raises; the next call continues with the next frame.

        The envelope is checked for TTL expiry on receipt, as PBS-ENV-01
        Section 12.2 requires of every receiver: with TTL > 0 it is expired
        when clock_source() - Timestamp / 10^6 > TTL. An envelope with TTL 0
        never expires. An expired envelope raises PBSTTLError after it has
        been read in full, so the next call reads the next envelope or frame.

        Args:
            timeout: Read timeout in seconds (None = blocking). Applied to the
                     port's timeout attribute, if it has one, for the duration
                     of the call (unframed: the header read only).
            check_ttl: If False, skip the expiry check and return expired
                       envelopes (default True).

        Returns:
            PBSEnvelope, or None when a read returns fewer bytes than needed
            (timeout or end of stream).

        Raises:
            PBSSerialError: Serial read failed
            PBSFramingError: COBS decoding failed, or no delimiter arrived
                             within the maximum frame length
            PBSValidationError: Received data failed validation
            PBSTTLError: The envelope has expired (subclass of
                         PBSValidationError)
        """
        if not self.serial_port:
            raise PBSError("No serial port configured")

        try:
            if self.use_framing:
                return self._receive_framed(timeout, check_ttl)
            return self._receive_unframed(timeout, check_ttl)
        except PBSError:
            raise
        except Exception as e:
            raise PBSSerialError(f"Serial read failed: {e}") from e

    def _receive_unframed(self, timeout: Optional[float], check_ttl: bool) -> Optional[PBSEnvelope]:
        port = self.serial_port
        has_timeout = hasattr(port, 'timeout')
        if has_timeout:
            old_timeout = port.timeout
            port.timeout = timeout
        try:
            header_data = port.read(HEADER_SIZE)
        finally:
            if has_timeout:
                port.timeout = old_timeout

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
            payload_data = port.read(size)
            if len(payload_data) < size:
                return None  # Incomplete

        return self._parse_unframed(header_data + payload_data, check_ttl=check_ttl)

    def _max_encoded_frame_length(self) -> int:
        """Longest COBS encoding of a valid envelope, delimiter excluded."""
        n = HEADER_SIZE + self.max_payload_size
        return n + n // 254 + 1

    def _take_frame(self) -> Optional[bytes]:
        """
        Remove one frame (delimiter excluded) from the receive buffer.

        Returns None when the buffer holds no delimiter yet. Returns b''
        for an empty frame and for the tail of a discarded overlong frame.
        """
        buf = self._receive_buffer
        idx = buf.find(0x00)
        if idx < 0:
            if len(buf) > self._max_encoded_frame_length():
                del buf[:]
                self._discard_to_delimiter = True
                raise PBSFramingError(
                    f"No frame delimiter within {self._max_encoded_frame_length()} bytes; "
                    "discarding to the next delimiter"
                )
            return None
        frame = bytes(buf[:idx])
        del buf[:idx + 1]
        if self._discard_to_delimiter:
            self._discard_to_delimiter = False
            return b''
        return frame

    def _receive_framed(self, timeout: Optional[float], check_ttl: bool) -> Optional[PBSEnvelope]:
        port = self.serial_port
        has_timeout = hasattr(port, 'timeout')
        if has_timeout:
            old_timeout = port.timeout
            port.timeout = timeout
        try:
            while True:
                frame = self._take_frame()
                if frame is None:
                    # Read what the port has buffered, at least one byte.
                    chunk = port.read(getattr(port, 'in_waiting', 0) or 1)
                    if not chunk:
                        return None  # Timeout or end of stream; partial frame kept
                    self._receive_buffer.extend(chunk)
                    continue
                if not frame:
                    continue  # Empty frame
                data = COBSFraming.decode(frame)
                envelope = self._parse_unframed(data, check_ttl=check_ttl)
                if envelope.size > self.max_payload_size:
                    raise PBSValidationError(
                        f"Payload size {envelope.size} exceeds maximum {self.max_payload_size}"
                    )
                if len(data) != HEADER_SIZE + envelope.size:
                    raise PBSValidationError(
                        f"Frame carries {len(data)} bytes; header Size gives "
                        f"{HEADER_SIZE + envelope.size}"
                    )
                return envelope
        finally:
            if has_timeout:
                port.timeout = old_timeout

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
