# Выполняется ВНУТРИ Blender (запускается через scripts/render.py):
#   blender --background --factory-startup --python scripts/blender_render.py -- --dat ... --part ... ...
# Multi-view рендер одной LDraw-детали: ракурсы по сфере (спираль Фибоначчи),
# вариативный свет/фон/цвет пластика (LEGO.md §8.1). Сид фиксирован по part_num.
import argparse
import math
import random
import sys

import bpy
from mathutils import Vector

# нейтральные «пластиковые» цвета (light/dark bluish gray, red, yellow, blue)
PALETTE = [
    (0.63, 0.65, 0.67), (0.35, 0.37, 0.39), (0.70, 0.06, 0.06),
    (0.95, 0.75, 0.05), (0.05, 0.20, 0.60),
]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--dat", required=True)
    ap.add_argument("--part", required=True)
    ap.add_argument("--ldraw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--views", type=int, default=24)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--samples", type=int, default=32)
    return ap.parse_args(argv)


def fibonacci_sphere(n):
    """n равномерных направлений на единичной сфере."""
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - z * z)
        yield Vector((r * math.cos(golden * i), r * math.sin(golden * i), z))


def set_base_color(objs, rgb):
    # аддон строит материал как RGB-узел "Color" -> группа "LEGO Standard"
    for obj in objs:
        for slot in obj.material_slots:
            mat = slot.material
            if not (mat and mat.node_tree):
                continue
            for node in mat.node_tree.nodes:
                if node.type == "RGB":
                    node.outputs[0].default_value = (*rgb, 1.0)
                elif node.type == "BSDF_PRINCIPLED":
                    node.inputs["Base Color"].default_value = (*rgb, 1.0)


def main():
    args = parse_args()
    rng = random.Random(args.part)  # воспроизводимость на деталь

    bpy.ops.preferences.addon_enable(module="ExportLdraw")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.ldraw_exporter.import_operator(
        filepath=args.dat, ldraw_path=args.ldraw)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        print("RENDER ERROR: no mesh imported")
        sys.exit(1)

    # ограничивающая сфера детали в мировых координатах
    corners = [o.matrix_world @ Vector(c) for o in meshes
               for c in o.bound_box]
    center = sum(corners, Vector()) / len(corners)
    radius = max((c - center).length for c in corners)

    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    dist = radius / math.sin(cam_data.angle / 2) * 1.1  # стартовая позиция
    # для per-view фита: все углы bbox мешей одним плоским списком
    fit_coords = [c for v in corners for c in v]

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    bpy.context.collection.objects.link(sun)

    world = bpy.data.worlds["World"]
    world.use_nodes = True
    bg_node = world.node_tree.nodes["Background"]

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = args.size
    try:  # GPU (Metal), иначе CPU
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = "GPU"
    except Exception as e:  # noqa: BLE001
        print("RENDER note: GPU недоступен, CPU:", e)

    for i, direction in enumerate(fibonacci_sphere(args.views)):
        cam.location = center + direction * dist
        cam.rotation_euler = (center - cam.location).to_track_quat(
            "-Z", "Y").to_euler()
        # per-view фит по проекции bbox (ПАТЧ п.1): деталь занимает
        # стабильную долю кадра независимо от вытянутости
        bpy.context.view_layer.update()
        loc, _ = cam.camera_fit_coords(
            bpy.context.evaluated_depsgraph_get(), fit_coords)
        cam.location = center + (loc - center) * 1.08  # небольшой отступ

        sun.rotation_euler = (
            math.radians(rng.uniform(15, 70)), 0,
            math.radians(rng.uniform(0, 360)))
        sun.data.energy = rng.uniform(2.0, 5.0)
        gray = rng.uniform(0.55, 0.95)  # контрастный светло-серый фон
        bg_node.inputs["Color"].default_value = (gray, gray, gray, 1.0)
        bg_node.inputs["Strength"].default_value = rng.uniform(0.6, 1.2)
        set_base_color(meshes, rng.choice(PALETTE))

        scene.render.filepath = f"{args.out}/{args.part}/{args.part}_v{i:02d}.png"
        bpy.ops.render.render(write_still=True)
        print(f"RENDER view {i + 1}/{args.views}")

    print(f"RENDER DONE {args.views} views -> {args.out}/{args.part}")


main()
