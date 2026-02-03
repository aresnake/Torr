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

    t = threading.Thread(target=drain, args=("[stderr] ", p.stderr), daemon=True)
    t.start()

    r = send(p, {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
    print("[tools/list]", json.dumps(r, ensure_ascii=False))

    r = send(p, {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"system_info","arguments":{}}})
    sys_info = tool_text(r)
    print("[system_info]", sys_info)

    r = send(p, {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"world_health","arguments":{}}})
    health = tool_text(r)
    print("[world_health]", health)

    r = send(p, {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"world_reset","arguments":{"seed":0}}})
    reset_out = tool_text(r)
    print("[reset_out]", reset_out)

    r = send(p, {"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"world_observe","arguments":{"level":"compact"}}})
    obs0 = tool_text(r)
    print("[observe0]", obs0)
    s0 = obs0["snapshot_id"]

    r = send(p, {"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"world_mutate","arguments":{
        "dsl_version":"1.0",
        "batch":[{"op":"object.create_primitive","args":{"type":"cube","name":"Chair_Seat","location":[0,0,0.45]}}]
    }}})
    mut = tool_text(r)
    print("[mutate]", mut)
    s1 = mut["snapshot_id"]

    r = send(p, {"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"world_observe","arguments":{"level":"compact"}}})
    obs1 = tool_text(r)
    print("[observe1]", obs1)
    s2 = obs1["snapshot_id"]

    # Diff is headless-only for now. In UI mode, snapshot ids are U*, so skip.
    if str(s0).startswith("U") or str(s1).startswith("U") or str(s2).startswith("U"):
        print("[diff skipped] ui provider does not support observe_diff yet.")
    else:
        r = send(p, {"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"world_observe_diff","arguments":{"from":s0,"to":s1}}})
        diff1 = tool_text(r)
        print("[diff s0->s1]", diff1)

        r = send(p, {"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"world_observe_diff","arguments":{"from":s1,"to":s2}}})
        diff2 = tool_text(r)
        print("[diff s1->s2]", diff2)

    p.kill()
