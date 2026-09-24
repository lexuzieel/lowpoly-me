"""Render the face with each shape key at 1.0 -> out/key_<name>.png"""
import math
import os

import bpy
from mathutils import Vector

ROOT = globals().get("ROOT") or os.path.dirname(os.path.abspath(__file__))
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "FLAT"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x, scene.render.resolution_y = 300, 360
face = bpy.data.objects["face"]
for m in ("MouthIn", "Teeth"):  # workbench texture mode shows flat materials by their color
    pass
keys = face.data.shape_keys.key_blocks
c = sum((face.matrix_world @ v.co for v in face.data.vertices[:478]), Vector()) / 478
cam = scene.camera
views = globals().get("VIEWS", [0])
for ang in views:
    for k in keys:
        for kk in keys:
            kk.value = 0
        k.value = 1
        a = math.radians(ang)
        cam.location = c + Vector((math.sin(a) * 0.55, -math.cos(a) * 0.55, 0.0))
        cam.rotation_euler = (math.pi / 2, 0, a)
        scene.render.filepath = os.path.join(ROOT, f"out/key_{ang}_{k.name}.png")
        bpy.ops.render.render(write_still=True)
for kk in keys:
    kk.value = 0
