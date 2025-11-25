import socket
import csv
from datetime import datetime
import os

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
CSV_FILE = "accelerometer_data.csv"

# Create CSV file with headers if it doesn't exist
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_unix', 'type', 'sensor_timestamp', 'x', 'y', 'z', 'datetime'])

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Listening UDP on {UDP_PORT}...")
print(f"Saving data to: {CSV_FILE}")

while True:
    data, addr = sock.recvfrom(4096)
    message = data.decode()
    print("DATA:", message, "FROM:", addr)
    
    try:
        # Parse the data: timestamp_unix,type,sensor_timestamp,x,y,z
        parts = message.split(',')
        if len(parts) >= 6:
            timestamp_unix = parts[0]
            data_type = parts[1]
            sensor_timestamp = parts[2]
            x = parts[3]
            y = parts[4]
            z = parts[5]
            
            # Convert timestamp to readable datetime
            dt = datetime.fromtimestamp(int(timestamp_unix) / 1000.0)
            datetime_str = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            # Save to CSV
            with open(CSV_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp_unix, data_type, sensor_timestamp, x, y, z, datetime_str])
            
            print(f"  → Saved: {data_type} X={x} Y={y} Z={z} at {datetime_str}")
    except Exception as e:
        print(f"  → Error parsing data: {e}")
