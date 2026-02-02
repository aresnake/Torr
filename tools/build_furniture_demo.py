# build_furniture_demo.py
# Demo visuelle (Blender UI) : crée une chaise + un banc crédibles, bevel, et sauvegarde un .blend dans D:\MCP_WORLD1\out
# Data-first (bmesh) pour éviter la magie bpy.ops (sauf sauvegarde).

import os
import bpy
import bmesh
from mathutils import Vector

BASE_OUT = r"D:\MCP_WORLD1\out"
BLEND_OUT = os.path.join(BASE_OUT, "furniture_demo.blend")


def ensure_clean_scene():
    # purge objects (data-first-ish)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    # keep collections but clean links
    for coll in list(bpy.data.collections):
        if coll.name not in {"Collection", "Scene Collection"} and coll.users == 0:
            bpy.data.collections.remove(coll)


def ensure_collection(name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def create_cube_mesh(name: str) -> bpy.types.Mesh:
    me = bpy.data.meshes.new(name + "_Mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)  # cube "unit" centered, edge length 2
    bm.to_mesh(me)
    bm.free()
    return me


def create_part(coll: bpy.types.Collection, name: str, location, scale, bevel=0.02, shade_smooth=True):
    me = create_cube_mesh(name)
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)

    obj.location = Vector(location)
    obj.scale = Vector(scale)

    # bevel modifier (simple + visible)
    mod = obj.modifiers.new(name="Bevel", type="BEVEL")
    mod.width = bevel
    mod.segments = 3
    mod.profile = 0.7
    mod.limit_method = 'ANGLE'
    mod.angle_limit = 0.610865  # 35 deg

    if shade_smooth:
        for p in me.polygons:
            p.use_smooth = True

    return obj


def build_chair(coll: bpy.types.Collection, origin=(0, 0, 0)):
    ox, oy, oz = origin

    # proportions "réalistes" (mètres, approx)
    seat_h = 0.45
    seat_w = 0.46
    seat_d = 0.46
    seat_t = 0.04

    leg_w = 0.05
    leg_h = seat_h - 0.02

    back_h = 0.55
    back_t = 0.035
    back_w = seat_w
    back_y = -seat_d * 0.45

    # seat
    create_part(
        coll, "Chair_Seat",
        location=(ox, oy, oz + seat_h),
        scale=(seat_w/2, seat_d/2, seat_t/2),
        bevel=0.015
    )

    # legs (4 corners)
    lx = (seat_w/2 - leg_w/2) * 0.95
    ly = (seat_d/2 - leg_w/2) * 0.95
    leg_z = oz + (leg_h/2)

    for name, x, y in [
        ("Chair_Leg_FL", +lx, +ly),
        ("Chair_Leg_FR", -lx, +ly),
        ("Chair_Leg_BL", +lx, -ly),
        ("Chair_Leg_BR", -lx, -ly),
    ]:
        create_part(
            coll, name,
            location=(ox + x, oy + y, leg_z),
            scale=(leg_w/2, leg_w/2, leg_h/2),
            bevel=0.01
        )

    # backrest
    create_part(
        coll, "Chair_Back",
        location=(ox, oy + back_y, oz + seat_h + back_h/2),
        scale=(back_w/2, back_t/2, back_h/2),
        bevel=0.012
    )


def build_bench(coll: bpy.types.Collection, origin=(1.2, 0, 0)):
    ox, oy, oz = origin

    seat_h = 0.45
    seat_w = 1.20
    seat_d = 0.40
    seat_t = 0.05

    leg_w = 0.06
    leg_h = seat_h - 0.02

    # seat
    create_part(
        coll, "Bench_Seat",
        location=(ox, oy, oz + seat_h),
        scale=(seat_w/2, seat_d/2, seat_t/2),
        bevel=0.015
    )

    # 4 legs (reculées un peu vers les bords)
    lx = (seat_w/2 - leg_w/2) * 0.93
    ly = (seat_d/2 - leg_w/2) * 0.92
    leg_z = oz + (leg_h/2)

    for name, x, y in [
        ("Bench_Leg_FL", +lx, +ly),
        ("Bench_Leg_FR", -lx, +ly),
        ("Bench_Leg_BL", +lx, -ly),
        ("Bench_Leg_BR", -lx, -ly),
    ]:
        create_part(
            coll, name,
            location=(ox + x, oy + y, leg_z),
            scale=(leg_w/2, leg_w/2, leg_h/2),
            bevel=0.01
        )


def ensure_camera_and_light():
    scn = bpy.context.scene

    # light
    light_data = bpy.data.lights.new(name="KeyLight", type='AREA')
    light_obj = bpy.data.objects.new(name="KeyLight", object_data=light_data)
    scn.collection.objects.link(light_obj)
    light_obj.location = (2.5, -2.5, 2.2)
    light_data.energy = 1200
    light_data.size = 2.0

    # camera
    cam_data = bpy.data.cameras.new(name="Camera")
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    scn.collection.objects.link(cam_obj)
    cam_obj.location = (2.8, -3.2, 1.7)
    cam_obj.rotation_euler = (1.15, 0.0, 0.78)
    scn.camera = cam_obj


def main():
    os.makedirs(BASE_OUT, exist_ok=True)
    ensure_clean_scene()

    coll = ensure_collection("Furniture")
    build_chair(coll, origin=(0, 0, 0))
    build_bench(coll, origin=(1.4, 0, 0))

    ensure_camera_and_light()

    # save blend
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
    print(f"[OK] Saved: {BLEND_OUT}")


if __name__ == "__main__":
    main()
