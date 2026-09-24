"""Render front / 3-4 / side previews with Workbench -> out/prev_<angle>.png"""
import math
import os

import bpy
from mathutils import Vector

ROOT = globals().get("ROOT") or os.path.dirname(os.path.abspath(__file__))
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
sh = scene.display.shading
sh.light = "FLAT"
sh.color_type = "TEXTURE"
scene.render.resolution_x, scene.render.resolution_y = 480, 640
scene.render.film_transparent = False
scene.world.color = (0.05, 0.05, 0.06) if scene.world else None

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
center = sum(pts, Vector()) / len(pts)
cam = scene.camera
dist = 1.25
for ang in (0, 35, 80):
    a = math.radians(ang)
    cam.location = center + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0))
    cam.rotation_euler = (math.pi / 2, 0, a)
    scene.render.filepath = os.path.join(ROOT, f"out/prev_{ang}.png")
    bpy.ops.render.render(write_still=True)
cam.location = center + Vector((0, -dist, 0))
cam.rotation_euler = (math.pi / 2, 0, 0)
print("center", center)
