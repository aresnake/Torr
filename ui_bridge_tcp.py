# ui_bridge_tcp.py
# Run inside Blender (UI) via: Blender > Scripting > Run Script
# Opens a local TCP server that receives JSON lines and replies with JSON lines.

import json
import socket
import threading
import traceback

import bpy

HOST = "127.0.0.1"
PORT = 61888

def _json_reply(sock, obj):
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    sock.sendall(data)

def _handle_request(req):
    try:
        method = req.get("method")
        params = req.get("params") or {}

        if method == "ping":
            return {"ok": True, "pong": True, "blender": bpy.app.version_string}

        if method == "world_reset":
            # minimal reset: delete all objects
            bpy.ops.object.select_all(action='SELECT')
            bpy.ops.object.delete(use_global=False)
            return {"ok": True, "object_count": len(bpy.data.objects)}

        if method == "world_observe":
            objs = []
            for o in bpy.context.scene.objects:
                if o.type in {"MESH", "EMPTY", "LIGHT", "CAMERA"}:
                    objs.append({
                        "name": o.name,
                        "type": o.type,
                        "location": list(o.location),
                        "rotation_euler": list(o.rotation_euler),
                        "scale": list(o.scale),
                    })
            return {"ok": True, "scene": bpy.context.scene.name, "object_count": len(objs), "objects": objs}

        # placeholder: we'll wire mutate next
        if method == "world_mutate":
            return {"ok": False, "error_type": "not_implemented", "error_message": "world_mutate not implemented yet in UI bridge."}

        return {"ok": False, "error_type": "unknown_method", "error_message": f"Unknown method: {method}"}

    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "trace": traceback.format_exc().splitlines()[:20],
        }

def _client_thread(conn, addr):
    try:
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line.decode("utf-8"))
                except Exception as e:
                    _json_reply(conn, {"ok": False, "error_type": "json_parse", "error_message": str(e)})
                    continue
                resp = _handle_request(req)
                _json_reply(conn, resp)
    finally:
        try:
            conn.close()
        except Exception:
            pass

def start_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(5)
    print(f"[Torr UI Bridge] listening on {HOST}:{PORT}")

    while True:
        conn, addr = s.accept()
        t = threading.Thread(target=_client_thread, args=(conn, addr), daemon=True)
        t.start()

# Start in background thread so Blender UI remains responsive
threading.Thread(target=start_server, daemon=True).start()
print("[Torr UI Bridge] started")
