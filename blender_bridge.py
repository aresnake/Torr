# blender_bridge.py
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Tuple

import bpy

JSON = Dict[str, Any]

SNAPSHOT_VERSION = "1.2"
DIFF_VERSION = "1.1"
DSL_VERSION = "1.0"

# Precision control: stabilizes float noise for training
ROUND_DECIMALS = 5

_snapshot_counter = 0
_snapshots: Dict[str, JSON] = {}


def write_json(obj: JSON) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _r(x: float) -> float:
    return round(float(x), ROUND_DECIMALS)


def _vec3(v) -> List[float]:
    return [_r(v[0]), _r(v[1]), _r(v[2])]


def _next_snapshot_id() -> str:
    global _snapshot_counter
    _snapshot_counter += 1
    return f"S{_snapshot_counter}"


def bootstrap_clean_scene() -> None:
    # Remove all objects (including default cube/light/camera)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def world_reset(seed: int = 0) -> JSON:
    bootstrap_clean_scene()

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 250
    scene.frame_set(1)

    sid = _next_snapshot_id()
    snap = world_observe_compact(snapshot_id=sid)
    _snapshots[sid] = snap

    return {"ok": True, "seed": seed, "snapshot_id": sid, "object_count": 0}


def world_observe_compact(snapshot_id: str | None = None) -> JSON:
    scene = bpy.context.scene
    objs: List[JSON] = []

    for obj in scene.objects:
        objs.append(
            {
                "name": obj.name,
                "type": obj.type,
                "location": _vec3(obj.location),
                "rotation_euler": _vec3(obj.rotation_euler),
                "scale": _vec3(obj.scale),
                "collection": (obj.users_collection[0].name if obj.users_collection else scene.collection.name),
            }
        )

    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "snapshot_id": snapshot_id,
        "scene": {"name": scene.name, "frame": int(scene.frame_current), "frame_range": [int(scene.frame_start), int(scene.frame_end)]},
        "objects": objs,
        "summary_text": f"{len(objs)} objects in scene.",
    }


def _obj_map(snap: JSON) -> Dict[str, JSON]:
    return {str(o.get("name")): o for o in (snap.get("objects") or [])}


def _transform_tuple(o: JSON) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    loc = tuple(float(x) for x in o.get("location", [0, 0, 0]))
    rot = tuple(float(x) for x in o.get("rotation_euler", [0, 0, 0]))
    sca = tuple(float(x) for x in o.get("scale", [1, 1, 1]))
    return loc, rot, sca


def world_observe_diff(from_id: str, to_id: str) -> JSON:
    a = _snapshots.get(from_id)
    b = _snapshots.get(to_id)
    if not a or not b:
        return {"ok": False, "diff_version": DIFF_VERSION, "error": "unknown snapshot_id", "from": from_id, "to": to_id}

    a_objs = _obj_map(a)
    b_objs = _obj_map(b)

    added = sorted([k for k in b_objs.keys() if k not in a_objs])
    removed = sorted([k for k in a_objs.keys() if k not in b_objs])

    transforms_changed: List[JSON] = []
    for k in sorted(set(a_objs.keys()) & set(b_objs.keys())):
        ta = _transform_tuple(a_objs[k])
        tb = _transform_tuple(b_objs[k])
        if ta != tb:
            transforms_changed.append({"name": k, "from": {"loc": list(ta[0]), "rot": list(ta[1]), "scale": list(ta[2])},
                                       "to": {"loc": list(tb[0]), "rot": list(tb[1]), "scale": list(tb[2])}})

    # Collection change is also useful
    collections_changed: List[JSON] = []
    for k in sorted(set(a_objs.keys()) & set(b_objs.keys())):
        ca = a_objs[k].get("collection")
        cb = b_objs[k].get("collection")
        if ca != cb:
            collections_changed.append({"name": k, "from": ca, "to": cb})

    return {
        "ok": True,
        "diff_version": DIFF_VERSION,
        "from": from_id,
        "to": to_id,
        "objects_added": added,
        "objects_removed": removed,
        "transforms_changed": transforms_changed,
        "collections_changed": collections_changed,
        "metrics": {"object_count_from": len(a_objs), "object_count_to": len(b_objs)},
        "warnings": [],
    }


def _ensure_collection(name: str) -> bpy.types.Collection:
    name = str(name)
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _link_object_to_collection(obj: bpy.types.Object, col: bpy.types.Collection) -> None:
    # Link if not already linked
    if obj.name not in col.objects:
        col.objects.link(obj)
    # Optional: remove from master collection to avoid duplicates
    # Keep it non-destructive for now.


def _find_object(name: str) -> bpy.types.Object | None:
    return bpy.data.objects.get(str(name))


def _dsl_object_create_primitive(args: JSON) -> JSON:
    prim_type = str(args.get("type", "cube")).lower()
    name = str(args.get("name", "Object"))
    location = args.get("location", [0.0, 0.0, 0.0])
    collection = args.get("collection")

    supported = {"cube"}
    if prim_type not in supported:
        return {"ok": False, "error": f"primitive type not supported in v1: {prim_type}", "supported": sorted(list(supported))}

    # Create cube mesh manually
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)

    verts = [
        (-1, -1, -1),
        (1, -1, -1),
        (1, 1, -1),
        (-1, 1, -1),
        (-1, -1, 1),
        (1, -1, 1),
        (1, 1, 1),
        (-1, 1, 1),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    try:
        obj.location.x = float(location[0])
        obj.location.y = float(location[1])
        obj.location.z = float(location[2])
    except Exception:
        pass

    if collection:
        col = _ensure_collection(str(collection))
        _link_object_to_collection(obj, col)

    return {"ok": True, "created": name}


def _dsl_object_set_transform(args: JSON) -> JSON:
    name = str(args.get("name", ""))
    obj = _find_object(name)
    if obj is None:
        return {"ok": False, "error": f"object not found: {name}"}

    if "location" in args:
        loc = args.get("location")
        obj.location.x = float(loc[0])
        obj.location.y = float(loc[1])
        obj.location.z = float(loc[2])

    if "rotation_euler" in args:
        rot = args.get("rotation_euler")
        obj.rotation_euler.x = float(rot[0])
        obj.rotation_euler.y = float(rot[1])
        obj.rotation_euler.z = float(rot[2])

    if "scale" in args:
        sca = args.get("scale")
        obj.scale.x = float(sca[0])
        obj.scale.y = float(sca[1])
        obj.scale.z = float(sca[2])

    return {"ok": True, "updated": name}


def _dsl_object_delete(args: JSON) -> JSON:
    name = str(args.get("name", ""))
    obj = _find_object(name)
    if obj is None:
        return {"ok": False, "error": f"object not found: {name}"}
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"ok": True, "deleted": name}


def _dsl_collection_create(args: JSON) -> JSON:
    name = str(args.get("name", ""))
    if not name:
        return {"ok": False, "error": "collection name required"}
    _ensure_collection(name)
    return {"ok": True, "created": name}


def _dsl_collection_link_object(args: JSON) -> JSON:
    col_name = str(args.get("collection", ""))
    obj_name = str(args.get("object", ""))
    if not col_name or not obj_name:
        return {"ok": False, "error": "collection and object required"}
    col = _ensure_collection(col_name)
    obj = _find_object(obj_name)
    if obj is None:
        return {"ok": False, "error": f"object not found: {obj_name}"}
    _link_object_to_collection(obj, col)
    return {"ok": True, "linked": {"object": obj_name, "collection": col_name}}


def world_mutate(dsl_version: str, batch: List[JSON]) -> JSON:
    if dsl_version != DSL_VERSION:
        return {"ok": False, "error": f"unsupported dsl_version {dsl_version}", "supported": DSL_VERSION}

    applied = 0
    warnings: List[str] = []
    errors: List[JSON] = []

    for i, item in enumerate(batch):
        op = str(item.get("op", ""))
        args = item.get("args") or {}

        try:
            if op == "object.create_primitive":
                r = _dsl_object_create_primitive(args)
            elif op == "object.set_transform":
                r = _dsl_object_set_transform(args)
            elif op == "object.delete":
                r = _dsl_object_delete(args)
            elif op == "collection.create":
                r = _dsl_collection_create(args)
            elif op == "collection.link_object":
                r = _dsl_collection_link_object(args)
            else:
                r = {"ok": False, "error": "op not supported in v3"}

            if r.get("ok"):
                applied += 1
            else:
                errors.append({"index": i, "op": op, "error": r.get("error", "unknown")})

        except Exception as ex:
            errors.append({"index": i, "op": op, "error": repr(ex)})

    sid = _next_snapshot_id()
    snap = world_observe_compact(snapshot_id=sid)
    _snapshots[sid] = snap

    return {
        "ok": len(errors) == 0,
        "dsl_version": DSL_VERSION,
        "applied": applied,
        "errors": errors,
        "warnings": warnings,
        "snapshot_id": sid,
    }


def main() -> None:
    # stdout must be JSON-only.
    bootstrap_clean_scene()
    write_json({"ok": True, "type": "bridge_ready", "snapshot_version": SNAPSHOT_VERSION, "dsl_version": DSL_VERSION})

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
            tool = req.get("tool")
            args = req.get("args") or {}

            if tool == "world.reset":
                seed = int(args.get("seed", 0))
                write_json(world_reset(seed=seed))
                continue

            if tool == "world.observe":
                sid = _next_snapshot_id()
                snap = world_observe_compact(snapshot_id=sid)
                _snapshots[sid] = snap
                write_json(snap)
                continue

            if tool == "world.observe_diff":
                from_id = str(args.get("from"))
                to_id = str(args.get("to"))
                write_json(world_observe_diff(from_id, to_id))
                continue

            if tool == "world.mutate":
                dslv = str(args.get("dsl_version", ""))
                batch = args.get("batch") or []
                if not isinstance(batch, list):
                    write_json({"ok": False, "error": "batch must be a list"})
                    continue
                write_json(world_mutate(dsl_version=dslv, batch=batch))
                continue

            write_json({"ok": False, "error": f"unknown tool {tool}"})

        except Exception as ex:
            write_json({"ok": False, "error": repr(ex)})


if __name__ == "__main__":
    main()
