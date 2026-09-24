"""Armature + procedural skin weights. Runs after blender_shells.py.

Bones: b_chest -> b_neck -> b_head -> b_eye_L / b_eye_R, b_chest -> b_forearm -> b_hand.
The hood blends head -> neck -> chest by height, so it follows the head instead of letting it poke out."""
import json
import os

import bpy
from mathutils import Vector

ROOT = globals().get("ROOT") or os.path.dirname(os.path.abspath(__file__))
S = 2400.0
face_data = json.load(open(os.path.join(ROOT, "out/face.json")))
R = json.load(open(os.path.join(ROOT, "out/rig_points.json")))
W, H = face_data["w"], face_data["h"]


def to_px(co):
    return Vector((co.x * S + W / 2, H - co.z * S, -co.y * S))


def to_bl(p):
    return Vector(((p[0] - W / 2) / S, -p[2] / S, (H - p[1]) / S))


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


if "rig" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["rig"])
for ob in bpy.data.objects:
    if ob.type == "MESH":
        ob.parent = None
        for m in [m for m in ob.modifiers if m.type == "ARMATURE"]:
            ob.modifiers.remove(m)
        ob.vertex_groups.clear()

cx, cy, cd, a, b, c = R["skull"]
chin, fh, neck_y = R["chin"], R["fh"], R["neck_y"]
wrist = Vector(R["wrist"])
arm_dir = Vector(R["arm_dir"])
hw = R["hw"]
hand_c = sum((to_px(v.co) for v in bpy.data.objects["hand"].data.vertices), Vector()) / len(
    bpy.data.objects["hand"].data.vertices)

P = {  # joint positions in pixel space
    "chest": (cx, chin + fh * 1.3, cd),
    "neck": (cx, neck_y + fh * 0.15, cd - c * 0.2),
    "head": (cx, chin - fh * 0.15, cd - c * 0.1),
    "top": (cx, cy - b, cd),
    "elbow": tuple(wrist + arm_dir * hw * 1.9),
    "wrist": tuple(wrist),
    "hand": tuple(hand_c),
}

arm_data = bpy.data.armatures.new("rig")
rig = bpy.data.objects.new("rig", arm_data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig

win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
with bpy.context.temp_override(window=win, area=area, active_object=rig, object=rig):
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def bone(name, h, t, parent=None):
        bn = eb.new(name)
        bn.head, bn.tail = to_bl(h), to_bl(t)
        if parent:
            bn.parent = eb[parent]
        return bn

    bone("b_chest", P["chest"], P["neck"])
    bone("b_neck", P["neck"], P["head"], "b_chest")
    bone("b_head", P["head"], P["top"], "b_neck")
    for side in ("L", "R"):
        eo = bpy.data.objects[f"eye_{side}"]
        c_px = to_px(eo.location)
        bone(f"b_eye_{side}", tuple(c_px), tuple(c_px + Vector((0, 0, 40))), "b_head")
    bone("b_forearm", P["elbow"], P["wrist"], "b_chest")
    bone("b_hand", P["wrist"], P["hand"], "b_forearm")
    bpy.ops.object.mode_set(mode="OBJECT")


def bind(ob, weights_fn):
    """weights_fn(px) -> {bone: weight}"""
    groups = {}
    mw = ob.matrix_world
    for v in ob.data.vertices:
        for bname, w in weights_fn(to_px(mw @ v.co)).items():
            if w <= 0:
                continue
            if bname not in groups:
                groups[bname] = ob.vertex_groups.new(name=bname)
            groups[bname].add([v.index], w, "REPLACE")
    mat = ob.matrix_world.copy()
    ob.parent = rig
    ob.matrix_world = mat
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = rig


def hood_w(p):
    head = 1 - smoothstep(chin - fh * 0.1, neck_y + fh * 0.1, p.y)
    chest = smoothstep(neck_y, chin + fh * 0.55, p.y)
    return {"b_head": head, "b_chest": chest, "b_neck": max(0, 1 - head - chest)}


for n in ("face", "skull", "beanie", "mouth_in", "teeth"):
    bind(bpy.data.objects[n], lambda p: {"b_head": 1})
bind(bpy.data.objects["eye_L"], lambda p: {"b_eye_L": 1})
bind(bpy.data.objects["eye_R"], lambda p: {"b_eye_R": 1})
bind(bpy.data.objects["hood"], hood_w)
bind(bpy.data.objects["clothes"], lambda p: {"b_chest": 1})
bind(bpy.data.objects["hand"], lambda p: {"b_hand": 1})
print("bones:", [bn.name for bn in arm_data.bones])
