from pbs_link import PBSLink

# 1. Initialize
link = PBSLink(device_id="Rover-Alpha")

# 2. Send Critical Alert (P0)
print("Sending Critical Alert...")
link.send(priority=0, payload="DRILL_JAM_DETECTED", ttl=0, require_ack=True)

# 3. Send Bulk Data (P4)
print("Sending Telemetry...")
link.send(priority=4, payload="Temp: 45C, Batt: 98%", ttl=60)