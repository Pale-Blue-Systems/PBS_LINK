"""
PBS-LINK: Pale Blue Systems Reference SDK
Implements PBS-ENV-01 v1.3 (44-Byte Header)
"""

from .core import (
    # Main class
    PBSLink,

    # Data structures
    PBSEnvelope,

    # Enums
    Priority,
    Flags,

    # Exceptions
    PBSError,
    PBSValidationError,
    PBSCRCError,
    PBSMagicError,
    PBSPriorityError,
    PBSTTLError,
    PBSSerialError,
    PBSFramingError,

    # Utilities
    COBSFraming,
    calculate_crc32,
    verify_crc32,
    build_envelope,
    parse_envelope,

    # Constants
    HEADER_FORMAT,
    HEADER_SIZE,
    MAGIC_BYTE,
    MAX_PAYLOAD_SIZE_DEFAULT,
)

__version__ = "0.1.1"
__author__ = "Pale Blue Systems"
__license__ = "Apache 2.0"

__all__ = [
    # Main class
    "PBSLink",

    # Data structures
    "PBSEnvelope",

    # Enums
    "Priority",
    "Flags",

    # Exceptions
    "PBSError",
    "PBSValidationError",
    "PBSCRCError",
    "PBSMagicError",
    "PBSPriorityError",
    "PBSTTLError",
    "PBSSerialError",
    "PBSFramingError",

    # Utilities
    "COBSFraming",
    "calculate_crc32",
    "verify_crc32",
    "build_envelope",
    "parse_envelope",

    # Constants
    "HEADER_FORMAT",
    "HEADER_SIZE",
    "MAGIC_BYTE",
    "MAX_PAYLOAD_SIZE_DEFAULT",
]
