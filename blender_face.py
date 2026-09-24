"""Face rig on top of blender_build.py: shape keys for lip sync / blinks, mouth cavity, eyeballs.

Works on the "face" object whose first 478 vertices are MediaPipe landmarks (fixed topology)."""
import json
import math
import os

import bpy
from mathutils import Vector

ROOT = globals().get("ROOT") or os.path.dirname(os.path.abspath(__file__))
S = 2400.0
face_data = json.load(open(os.path.join(ROOT, "out/face.json")))
W, H = face_data["w"], face_data["h"]

ob = bpy.data.objects["face"]
me = ob.data
for o in [o for o in bpy.data.objects if o.name.startswith(("eye_", "mouth_", "teeth"))]:
    bpy.data.objects.remove(o)
if me.shape_keys:
    ob.shape_key_clear()


# pixel space (x right, y down, d toward camera) <-> Blender
def to_px(co):
    return Vector((co.x * S + W / 2, H - co.z * S, -co.y * S))


def to_bl(p):
    return Vector(((p.x - W / 2) / S, -p.z / S, (H - p.y) / S))


base = [to_px(v.co) for v in me.vertices]
L = lambda i: base[i]  # landmark position in px

def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def add_key(name, fn):
    """fn(index, p) -> new pixel-space position."""
    kb = ob.shape_key_add(name=name, from_mix=False)
    kb.value = 0  # Blender 5 creates new keys at 1.0
    for i, p in enumerate(base):
        kb.data[i].co = to_bl(fn(i, p))
    return kb


ob.shape_key_add(name="Basis")

# --- key landmarks ---
UPPER_IN = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]
LOWER_IN = [95, 88, 178, 87, 14, 317, 402, 318, 324]
LOWER_OUT = [146, 91, 181, 84, 17, 314, 405, 321, 375]
mc = (L(61) + L(291)) / 2          # mouth center
mw = (L(291) - L(61)).length       # mouth width
jaw_hw = (L(454) - L(234)).length / 2
pivot = Vector((mc.x, (L(234).y + L(454).y) / 2, min(L(234).z, L(454).z)))  # jaw hinge, near the ears


def jaw_weight(i, p):
    if i in LOWER_IN or i in LOWER_OUT:
        return 1.0
    if i in UPPER_IN:
        return 0.0
    wy = smoothstep(mc.y - 4, mc.y + mw * 0.25, p.y)
    wx = 1 - smoothstep(mw * 0.6, jaw_hw * 1.05, abs(p.x - mc.x))
    return wy * wx


def jaw_open(i, p):
    w = jaw_weight(i, p)
    if w == 0:
        return p
    th = 0.32 * w
    dy, dd = p.y - pivot.y, p.z - pivot.z
    return Vector((p.x, pivot.y + dy * math.cos(th) + dd * math.sin(th), pivot.z + dd * math.cos(th) - dy * math.sin(th)))


def gauss(p, c, r):
    return math.exp(-((p - c).length / r) ** 2)


def corners(dx, dy, dd, r=0.35):
    """Move mouth corners: dx outward, dy up, dd forward (fractions of mouth width)."""
    def fn(i, p):
        out = Vector(p)
        for c, sgn in ((L(61), -1), (L(291), 1)):
            g = gauss(p, c, mw * r)
            out += Vector((sgn * dx * mw, -dy * mw, dd * mw)) * g
        return out
    return fn


def pucker(i, p):
    g = gauss(p, mc, mw * 0.55)
    return p + Vector(((mc.x - p.x) * 0.45, 0, mw * 0.12)) * g


def blink(upper, lower, ring2):
    up_i = {u: lo for u, lo in zip(upper, lower)}
    r2 = {r: u for r, u in zip(ring2, upper)}

    def fn(i, p):
        if i in up_i:
            tgt = L(up_i[i])
            return p.lerp(tgt, 0.92) + Vector((0, 0, 6))
        if i in r2:
            u = r2[i]
            return p + (L(up_i[u]) - L(u)) * 0.45
        return p
    return fn


R_UP, R_LO, R_R2 = [246, 161, 160, 159, 158, 157, 173], [7, 163, 144, 145, 153, 154, 155], [247, 30, 29, 27, 28, 56, 190]
L_UP, L_LO, L_R2 = [466, 388, 387, 386, 385, 384, 398], [249, 390, 373, 374, 380, 381, 382], [467, 260, 259, 257, 258, 286, 414]
BROWS = [70, 63, 105, 66, 107, 46, 53, 52, 65, 55, 300, 293, 334, 296, 336, 276, 283, 282, 295, 285]
brow_c = [L(i) for i in BROWS]


def brows_up(i, p):
    g = max(gauss(p, c, mw * 0.3) for c in brow_c)
    return p + Vector((0, -mw * 0.12, 0)) * g


add_key("jawOpen", jaw_open)
add_key("smile", corners(0.10, 0.10, -0.02))
add_key("wide", corners(0.12, 0.0, -0.03))
add_key("pucker", pucker)
add_key("frown", corners(0.02, -0.08, 0))
add_key("blinkR", blink(R_UP, R_LO, R_R2))   # person's right = left side of the photo
add_key("blinkL", blink(L_UP, L_LO, L_R2))
add_key("browsUp", brows_up)

# --- extra visemes for phoneme lip sync ---
UPPER_OUT = [185, 40, 39, 37, 0, 267, 269, 270, 409]
up_c = sum((L(i) for i in UPPER_OUT), Vector()) / len(UPPER_OUT)
lo_c = sum((L(i) for i in LOWER_OUT), Vector()) / len(LOWER_OUT)


def upper_up(i, p):
    """Upper lip lifts: shows the upper teeth (EE, F/V)."""
    if p.y > mc.y + 2 or i in LOWER_IN or i in LOWER_OUT:
        return p
    g = gauss(p, up_c, mw * 0.4)
    return p + Vector((0, -mw * 0.06, mw * 0.01)) * g


def lips_press(i, p):
    """M/B/P: lips pressed together and rolled in a bit."""
    g = gauss(p, mc, mw * 0.45)
    out = p + Vector(((mc.x - p.x) * 0.06, 0, -mw * 0.04)) * g
    if p.y > mc.y - 2:
        out += Vector((0, -mw * 0.025, 0)) * gauss(p, lo_c, mw * 0.35)
    return out


def lip_bite(i, p):
    """F/V: lower lip rides up and back under the upper teeth."""
    if p.y < mc.y - 2 and i not in LOWER_IN:
        return p
    g = 1.0 if (i in LOWER_IN or i in LOWER_OUT) else gauss(p, lo_c, mw * 0.3)
    return p + Vector((0, -mw * 0.05, -mw * 0.1)) * g


add_key("upperUp", upper_up)
add_key("mbp", lips_press)
add_key("fv", lip_bite)


# --- flat-color helper material ---
def flat_mat(name, rgb):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    return m


def add_mesh(name, verts_px, faces, mat, uvs_px=None):
    m = bpy.data.meshes.new(name)
    m.from_pydata([to_bl(v) for v in verts_px], [], faces)
    if uvs_px:
        uv = m.uv_layers.new(name="UV")
        for li, loop in enumerate(m.loops):
            x, y = uvs_px[loop.vertex_index]
            uv.data[li].uv = (x / W, 1 - y / H)
    for poly in m.polygons:
        poly.use_smooth = False
    m.materials.append(mat)
    o = bpy.data.objects.new(name, m)
    bpy.context.scene.collection.objects.link(o)
    return o


# --- mouth cavity: dark curved bowl behind the lips, deep enough for the open jaw ---
lip_d = sum(L(i).z for i in UPPER_IN) / len(UPPER_IN)
cav = []
cols, rows = 8, 5
for r in range(rows + 1):
    for c in range(cols + 1):
        u, v = c / cols - 0.5, r / rows
        x = mc.x + u * mw * 0.6
        y = mc.y - mw * 0.1 + v * mw * 0.5
        # edges curl far back so the open jaw never pulls them through the cheeks
        d = lip_d - mw * 0.12 - (1 - (2 * u) ** 2) * mw * 0.2 - v * mw * 0.15 - (2 * u) ** 4 * mw * 0.35
        cav.append(Vector((x, y, d)))
cf = [[r * (cols + 1) + c, r * (cols + 1) + c + 1, (r + 1) * (cols + 1) + c + 1, (r + 1) * (cols + 1) + c]
      for r in range(rows) for c in range(cols)]
add_mesh("mouth_in", cav, cf, flat_mat("MouthIn", (0.09, 0.02, 0.025)))

# upper teeth: a slim bent strip just behind the upper lip
teeth = []
for k in range(7):
    u = k / 6 - 0.5
    x = mc.x + u * mw * 0.62
    d = lip_d - mw * 0.1 - (2 * u) ** 2 * mw * 0.12
    teeth += [Vector((x, mc.y - mw * 0.05, d)), Vector((x, mc.y + mw * 0.11, d - 1))]
tf = [[2 * k, 2 * k + 2, 2 * k + 3, 2 * k + 1] for k in range(6)]
add_mesh("teeth", teeth, tf, flat_mat("Teeth", (0.78, 0.74, 0.66)))

# --- eyeballs: low-poly spheres behind the lid holes, textured by front projection ---
img = bpy.data.images.load(os.path.join(ROOT, "out/tex_eyes.jpg"), check_existing=True)
emat = bpy.data.materials.new("eyes")
emat.use_nodes = True
tex = emat.node_tree.nodes.new("ShaderNodeTexImage")
tex.image = img
tex.interpolation = "Closest"
bsdf = emat.node_tree.nodes.get("Principled BSDF")
emat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

for name, ci, ring, lids in (("eye_R", 468, [469, 470, 471, 472], R_UP + R_LO),
                             ("eye_L", 473, [474, 475, 476, 477], L_UP + L_LO)):
    ic = L(ci)
    ir = sum((L(i) - ic).length for i in ring) / 4
    r = ir * 2.1
    lid_d = min(L(i).z for i in lids)  # iris depth from MediaPipe is noisy; the lids are reliable
    print(name, "iris d", round(ic.z, 1), "lid d", round(lid_d, 1), "r", round(r, 1))
    center = Vector((ic.x, ic.y, lid_d - 3 - r))
    vs, fs, uvs = [], [], []
    seg, ring_n = 12, 8
    for a in range(ring_n + 1):          # latitude from front pole (a=0) to back
        th = math.pi * a / ring_n
        for b in range(seg):
            ph = 2 * math.pi * b / seg
            p = center + Vector((math.sin(th) * math.cos(ph) * r, math.sin(th) * math.sin(ph) * r, math.cos(th) * r))
            vs.append(p)
            uvs.append((p.x, p.y))
    for a in range(ring_n):
        for b in range(seg):
            i0 = a * seg + b
            i1 = a * seg + (b + 1) % seg
            fs.append([i0, i1, i1 + seg, i0 + seg])
    eo = add_mesh(name, vs, fs, emat, uvs)
    # pivot at the eyeball center, so web can rotate it to look at the camera
    c_bl = to_bl(center)
    eo.data.transform(__import__("mathutils").Matrix.Translation(-c_bl))
    eo.location = c_bl

print("shape keys:", [k.name for k in me.shape_keys.key_blocks])
print("objects:", sorted(o.name for o in bpy.data.objects if o.type == "MESH"))
