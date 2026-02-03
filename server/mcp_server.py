# mcp_server.py  (Claude Desktop compatible: initialize + tools + empty prompts/resources)
from __future__ import annotations

import json
import os
import platform
import sys
import traceback
from typing import Any, Dict, Optional

from providers.headless import HeadlessBlenderProvider
from providers.ui_tcp import UiTcpBlenderProvider

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
    tools = [
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
        {
            "name": "system_info",
            "description": "Return runtime info for server/provider (versions, paths, blender exe).",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "world_health",
            "description": "Health check for the persistent Blender provider.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    ]
    tools = sorted(tools, key=lambda t: t.get("name", ""))
    return {"tools": tools}


def _normalize_ok(payload: Any) -> JSON:
    if isinstance(payload, dict):
        if "ok" in payload:
            return payload
        out = {"ok": True}
        out.update(payload)
        return out
    return {"ok": True, "value": payload}


def _error_payload(ex: Exception, trace: Optional[str]) -> JSON:
    out: JSON = {
        "ok": False,
        "error_type": type(ex).__name__,
        "error_message": str(ex),
    }
    if trace:
        out["trace"] = trace
    return out


def _short_trace() -> Optional[str]:
    tb = traceback.format_exc()
    if not tb:
        return None
    lines = tb.splitlines()
    return "\n".join(lines[:20])


def main() -> None:
    # UTF-8 safety on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if os.environ.get("TORR_PROVIDER", "headless").lower() == "ui":
        provider = UiTcpBlenderProvider()
    else:
        provider = HeadlessBlenderProvider()

    # Minimal MCP session state
    initialized = False
    negotiated_protocol = "2024-11-05"  # safe default

    allowed_tools = {
        "world_observe",
        "world_reset",
        "world_mutate",
        "world_observe_diff",
        "system_info",
        "world_health",
    }

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

                if tool_name not in allowed_tools:
                    payload = {
                        "ok": False,
                        "error_type": "UnknownTool",
                        "error_message": f"Unknown tool: {tool_name}",
                    }
                    write_json(
                        {
                            "jsonrpc": "2.0",
                            "id": _id,
                            "result": {
                                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
                            },
                        }
                    )
                    continue

                try:
                    if tool_name == "system_info":
                        payload = {
                            "ok": True,
                            "server": {
                                "python_version": sys.version.split()[0],
                                "platform": platform.platform(),
                                "cwd": os.getcwd(),
                            },
                            "provider": provider.get_info(),
                        }
                    elif tool_name == "world_health":
                        payload = provider.health()
                        payload = _normalize_ok(payload)
                    else:
                        out = provider.call(tool_name, tool_args)
                        payload = _normalize_ok(out)
                except Exception as ex:
                    payload = _error_payload(ex, _short_trace())

                write_json(
                    {
                        "jsonrpc": "2.0",
                        "id": _id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
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
