# mcp_server.py  (Claude Desktop compatible: initialize + tools + empty prompts/resources)
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Dict, Optional

from provider_headless import HeadlessBlenderProvider

JSON = Dict[str, Any]


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr, flush=True)


def read_json_line() -> Optional[JSON]:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line)


def write_json(obj: JSON) -> None:
    # IMPORTANT: stdout must be JSON-RPC ONLY
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def tools_list() -> JSON:
    return {
        "tools": [
            {
                "name": "world_observe",
                "description": "Return a compact snapshot of the current Blender scene (persistent headless).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "level": {"type": "string", "enum": ["compact"], "default": "compact"},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "world_reset",
                "description": "Reset the Blender scene to empty (dev tool).",
                "inputSchema": {
                    "type": "object",
                    "properties": {"seed": {"type": "integer", "default": 0}},
                    "additionalProperties": False,
                },
            },
            {
                "name": "world_mutate",
                "description": "Apply a batch of actions (DSL v1). V3 supports primitives, transforms, delete, collections.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "dsl_version": {"type": "string", "enum": ["1.0"]},
                        "batch": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "op": {"type": "string"},
                                    "args": {"type": "object"},
                                },
                                "required": ["op", "args"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["dsl_version", "batch"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "world_observe_diff",
                "description": "Compute a semantic diff between two snapshot_ids returned by world_observe/world_mutate.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
                    "required": ["from", "to"],
                    "additionalProperties": False,
                },
            },
        ]
    }


def main() -> None:
    # UTF-8 safety on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

    provider = HeadlessBlenderProvider()

    # Minimal MCP session state
    initialized = False
    negotiated_protocol = "2024-11-05"  # safe default

    tool_aliases = {
        "world.observe": "world_observe",
        "world.reset": "world_reset",
        "world.mutate": "world_mutate",
        "world.observe_diff": "world_observe_diff",
    }
    tool_provider_names = {
        "world_observe": "world.observe",
        "world_reset": "world.reset",
        "world_mutate": "world.mutate",
        "world_observe_diff": "world.observe_diff",
    }
    allowed_tools = set(tool_provider_names.keys())

    while True:
        msg: Optional[JSON] = None
        try:
            msg = read_json_line()
            if msg is None:
                break

            method = msg.get("method")
            _id = msg.get("id")
            params = msg.get("params") or {}

            # --- MCP handshake (Claude Desktop expects this) ---
            if method == "initialize":
                # Client proposes protocolVersion; we accept and echo a compatible one
                pv = params.get("protocolVersion")
                if isinstance(pv, str) and pv.strip():
                    negotiated_protocol = pv.strip()

                initialized = True
                write_json(
                    {
                        "jsonrpc": "2.0",
                        "id": _id,
                        "result": {
                            "protocolVersion": negotiated_protocol,
                            "serverInfo": {"name": "mcp_world1", "version": "0.3.1"},
                            "capabilities": {
                                "tools": {"listChanged": False},
                                "resources": {"listChanged": False},
                                "prompts": {"listChanged": False},
                                "logging": {},
                            },
                        },
                    }
                )
                continue

            # Claude sends this as a notification (no id)
            if method == "notifications/initialized":
                # no response
                continue

            # Optional but sometimes used
            if method == "shutdown":
                write_json({"jsonrpc": "2.0", "id": _id, "result": None})
                break

            # --- Optional lists Claude might call ---
            if method == "resources/list":
                write_json({"jsonrpc": "2.0", "id": _id, "result": {"resources": []}})
                continue

            if method == "prompts/list":
                write_json({"jsonrpc": "2.0", "id": _id, "result": {"prompts": []}})
                continue

            # --- Your tools ---
            if method == "tools/list":
                # Some hosts call tools/list before/after initialize; we allow it anyway.
                write_json({"jsonrpc": "2.0", "id": _id, "result": tools_list()})
                continue

            if method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments") or {}

                if tool_name in tool_aliases:
                    tool_name = tool_aliases[tool_name]

                if tool_name not in allowed_tools:
                    write_json(
                        {
                            "jsonrpc": "2.0",
                            "id": _id,
                            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                        }
                    )
                    continue

                provider_tool = tool_provider_names.get(tool_name, tool_name)
                out = provider.call(provider_tool, tool_args)

                write_json(
                    {
                        "jsonrpc": "2.0",
                        "id": _id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}]
                        },
                    }
                )
                continue

            # Unknown method
            write_json(
                {
                    "jsonrpc": "2.0",
                    "id": _id,
                    "error": {"code": -32601, "message": f"Unknown method: {method}"},
                }
            )

        except Exception as ex:
            eprint("Server error:", repr(ex))
            eprint(traceback.format_exc())
            _id = None
            try:
                if isinstance(msg, dict):
                    _id = msg.get("id")
            except Exception:
                _id = None

            write_json(
                {"jsonrpc": "2.0", "id": _id, "error": {"code": -32000, "message": "Internal server error"}}
            )


if __name__ == "__main__":
    main()
