"""
agent_v1.py — Agent V1.1
Construit une chaise simple via MCP World-1 (siège + 4 pieds + dossier).

IMPORTANT:
- Le DSL v3 ignore "scale" dans object.create_primitive (dans ton bridge actuel).
  Donc on fait: create_primitive -> object.set_transform (scale + position).
- Ce script lance son propre mcp_server.py (stdio). Il peut aussi tourner pendant que
  Claude Desktop est connecté, mais évite de faire 10 runs simultanés.
"""

import json
import subprocess
from typing import Dict, Any, List, Tuple

MCP_CMD = ["python", "mcp_server.py"]


def send(proc, payload: Dict[str, Any]) -> Dict[str, Any]:
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("No response from MCP server")
    return json.loads(line)


def call_tool(proc, _id: int, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": _id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def content_text(resp: Dict[str, Any]) -> str:
    return resp["result"]["content"][0]["text"]


def chair_plan() -> List[Tuple[str, List[float], List[float]]]:
    """
    Returns list of (name, location, scale).
    Dimensions are simplistic and deterministic.
    """
    seat_loc = [0.0, 0.0, 0.45]
    seat_sca = [0.9, 0.9, 0.08]

    back_loc = [0.0, -0.38, 0.85]
    back_sca = [0.9, 0.08, 0.8]

    # Legs at corners
    lx = 0.40
    ly = 0.40
    leg_z = 0.22
    leg_sca = [0.08, 0.08, 0.45]

    legs = [
        ("Chair_Leg_FL", [ lx,  ly, leg_z], leg_sca),
        ("Chair_Leg_FR", [-lx,  ly, leg_z], leg_sca),
        ("Chair_Leg_BL", [ lx, -ly, leg_z], leg_sca),
        ("Chair_Leg_BR", [-lx, -ly, leg_z], leg_sca),
    ]

    parts = [
        ("Chair_Seat", seat_loc, seat_sca),
        ("Chair_Back", back_loc, back_sca),
        *legs,
    ]
    return parts


def main():
    print("[agent] starting agent_v1.1 (chair full)")

    proc = subprocess.Popen(
        MCP_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=".",
    )

    try:
        # 0) initialize
        print("[agent] initialize")
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
            },
        )

        # 1) reset world
        print("[agent] world_reset")
        r_reset = call_tool(proc, 2, "world_reset", {"seed": 0})
        print("[agent] reset_out:", content_text(r_reset))

        # 2) observe baseline (captures snapshot_id)
        r_obs0 = call_tool(proc, 3, "world_observe", {"level": "compact"})
        obs0_txt = content_text(r_obs0)
        print("[agent] observe0:", obs0_txt)
        obs0 = json.loads(obs0_txt)
        s_before = obs0["snapshot_id"]

        # 3) optional: create collection Chair
        print("[agent] create collection Chair")
        r_col = call_tool(
            proc,
            4,
            "world_mutate",
            {
                "dsl_version": "1.0",
                "batch": [
                    {"op": "collection.create", "args": {"name": "Chair"}},
                ],
            },
        )
        col_txt = content_text(r_col)
        print("[agent] mutate(collection):", col_txt)
        s_after_col = json.loads(col_txt).get("snapshot_id")

        # 4) build chair parts
        parts = chair_plan()

        batch: List[Dict[str, Any]] = []
        for name, loc, sca in parts:
            # Create cube at origin-ish (location will be set precisely after)
            batch.append(
                {
                    "op": "object.create_primitive",
                    "args": {
                        "type": "cube",
                        "name": name,
                        "location": [0.0, 0.0, 0.0],
                        "collection": "Chair",
                    },
                }
            )
            batch.append(
                {
                    "op": "object.set_transform",
                    "args": {
                        "name": name,
                        "location": loc,
                        "scale": sca,
                        "rotation_euler": [0.0, 0.0, 0.0],
                    },
                }
            )
            batch.append(
                {
                    "op": "collection.link_object",
                    "args": {"collection": "Chair", "object": name},
                }
            )

        print(f"[agent] world_mutate (build chair parts: ops={len(batch)})")
        r_mut = call_tool(
            proc,
            5,
            "world_mutate",
            {
                "dsl_version": "1.0",
                "batch": batch,
            },
        )
        mut_txt = content_text(r_mut)
        print("[agent] mutate(build):", mut_txt)
        s_after_build = json.loads(mut_txt)["snapshot_id"]

        # 5) observe after build
        r_obs1 = call_tool(proc, 6, "world_observe", {"level": "compact"})
        obs1_txt = content_text(r_obs1)
        print("[agent] observe1:", obs1_txt)
        obs1 = json.loads(obs1_txt)
        s_after_obs = obs1["snapshot_id"]

        # 6) diff from baseline to last observe
        print("[agent] world_observe_diff")
        r_diff = call_tool(proc, 7, "world_observe_diff", {"from": s_before, "to": s_after_obs})
        print("[agent] diff:", content_text(r_diff))

        print("[agent] DONE")

    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
