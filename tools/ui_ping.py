import json
import socket

HOST = "127.0.0.1"
PORT = 61888

def send(obj):
    with socket.create_connection((HOST, PORT), timeout=3) as s:
        s.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    return json.loads(data.decode("utf-8").strip())

print(send({"method": "ping", "params": {}}))
print(send({"method": "world_observe", "params": {}}))
