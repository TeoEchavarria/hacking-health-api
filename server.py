import socket

UDP_IP = "0.0.0.0"
UDP_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Listening UDP on {UDP_PORT}...")

while True:
    data, addr = sock.recvfrom(4096)
    print("DATA:", data.decode(), "FROM:", addr)
