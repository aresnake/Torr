import json
import os
import subprocess
import sys
import threading

def drain(prefix, stream):
    for line in stream:
        line = line.rstrip("\n")
        if line:
            print(f"{prefix}{line}")

def send(p, obj):
    p.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
    p.stdin.flush()
    line = p.stdout.readline().strip()
    if not line:
        raise RuntimeError("No response from server (stdout empty).")
    return json.loads(line)

def tool_text(resp):
    # MCP tool result is in result.content[0].text as JSON string
    txt = resp["result"]["content"][0]["text"]
    return json.loads(txt)

if __name__ == "__main__":
    env = os.environ.copy()

    p = subprocess.Popen(
        [sys.executable, "-m", "server.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )

    assert p.stdin and p.stdout and p.stderr

    # Drain stderr so it never blocks
    t = threading.Thread(target=drain, args=("[stderr] ", p.stderr), daemon=True)
    t.start()

    # 1) tools/list
    r = send(p, {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
    print("[tools/list]", json.dumps(r, ensure_ascii=False))

    # 2) reset
    r = send(p, {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"world.reset","arguments":{"seed":0}}})
    reset_out = tool_text(r)
    print("[reset_out]", reset_out)
    s_reset = reset_out["snapshot_id"]

    # 3) observe -> Sx
    r = send(p, {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"world.observe","arguments":{"level":"compact"}}})
    obs0 = tool_text(r)
    print("[observe0]", obs0)
    s0 = obs0["snapshot_id"]

    # 4) mutate create cube
    r = send(p, {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"world.mutate","arguments":{
        "dsl_version":"1.0",
        "batch":[{"op":"object.create_primitive","args":{"type":"cube","name":"Chair_Seat","location":[0,0,0.45]}}]
    }}})
    mut = tool_text(r)
    print("[mutate]", mut)
    s1 = mut["snapshot_id"]

    # 5) observe after mutate
    r = send(p, {"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"world.observe","arguments":{"level":"compact"}}})
    obs1 = tool_text(r)
    print("[observe1]", obs1)
    s2 = obs1["snapshot_id"]

    # 6) diff between observe0 and mutate result
    r = send(p, {"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"world.observe_diff","arguments":{"from":s0,"to":s1}}})
    diff1 = tool_text(r)
    print("[diff s0->s1]", diff1)

    # 7) diff between mutate result and observe1
    r = send(p, {"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"world.observe_diff","arguments":{"from":s1,"to":s2}}})
    diff2 = tool_text(r)
    print("[diff s1->s2]", diff2)

    p.kill()
