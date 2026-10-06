"""Build a CRITICAL alert and a BULK telemetry envelope with PBS_LINK.

Run after installing the package (pip install .):

    python EXAMPLES/rover_alert.py

The link is created with serial_port=None, so PBSLink.send() returns each
envelope as bytes instead of writing it. To write to a link, pass any object
with a write(bytes) method as serial_port (for example a pyserial
serial.Serial instance); send() then returns the number of bytes written.
"""
from PBS_LINK import PBSLink, Priority, parse_envelope

link = PBSLink(device_id="Rover-Alpha", serial_port=None)

# CRITICAL (0): never expires (TTL 0) and requests acknowledgement (Flags 0x01).
alert = link.send(
    priority=Priority.CRITICAL,
    payload="DRILL_JAM_DETECTED",
    ttl=0,
    require_ack=True,
)

# BULK (4): expires 60 s after its timestamp (PBS-ENV-01 section 12.2).
telemetry = link.send(
    priority=Priority.BULK,
    payload="Temp: 45C, Batt: 98%",
    ttl=60,
)

for name, packet in (("alert", alert), ("telemetry", telemetry)):
    env = parse_envelope(packet)  # verifies magic, header CRC-32 and priority
    print(f"{name}: {len(packet)} bytes (44-byte header + {env.size}-byte payload)")
    print(f"  header   {packet[:44].hex()}")
    print(
        f"  source={env.source_id} seq={env.sequence} "
        f"priority={env.priority_name} ack={env.ack_requested} "
        f"ttl={env.ttl}s crc32=0x{env.crc32:08x}"
    )
    print(f"  payload  {env.payload!r}")
