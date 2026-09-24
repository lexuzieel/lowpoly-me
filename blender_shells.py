"""Replace the flat inflated head/beanie/hood with real 3D shells around a skull, add a forearm,
reshape teeth. Runs after blender_build.py + blender_face.py.

All geometry is authored in photo pixel space (x right, y down, d toward camera), front-projected UVs:
back and sides land on the inpainted parts of each texture, so they get plausible fabric colors."""
import json
import math
import os

import bmesh
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

ROOT = globals().get("ROOT") or os.path.dirname(os.path.abspath(__file__))
S = 2400.0
face_data = json.load(open(os.path.join(ROOT, "out/face.json")))
M = json.load(open(os.path.join(ROOT, "out/metrics.json")))
W, H = face_data["w"], face_data["h"]


def to_px(co):
    return Vector((co.x * S + W / 2, H - co.z * S, -co.y * S))


def to_bl(p):
    return Vector(((p.x - W / 2) / S, -p.z / S, (H - p.y) / S))


for n in ("head", "beanie", "skull", "hood", "arm", "teeth"):
    if n in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[n])

face = bpy.data.objects["face"]
F = [to_px(face.data.vertices[i].co) for i in range(478)]
fkd = KDTree(478)
for i, p in enumerate(F):
    fkd.insert((p.x, p.y, 0), i)
fkd.balance()

# --- skull ellipsoid from landmarks ---
cx = (F[234].x + F[454].x) / 2
a = abs(F[454].x - F[234].x) / 2 * 1.02
cy = F[168].y                               # between the eyes
chin = F[152].y
fh = chin - F[10].y                         # forehead-to-chin
skull_top = M["beanie_top"] + 18
b = cy - skull_top
c = a * 1.15
cd = F[10].z - 6 - c                        # front of skull just behind the forehead
C = Vector((cx, cy, cd))
print(f"skull a={a:.0f} b={b:.0f} c={c:.0f} fh={fh:.0f}")


def ell(center, ra, rb, rc, th, ph):
    """th: 0 at top .. pi at bottom; ph: pi/2 faces the camera."""
    return center + Vector((ra * math.sin(th) * math.cos(ph), -rb * math.cos(th), rc * math.sin(th) * math.sin(ph)))


def grid_mesh(name, rows, mat_name, close_top=True):
    """rows: list of vertex rings (same count each). Quads between rings, optional top fan."""
    seg = len(rows[0])
    verts = [v for r in rows for v in r]
    faces = []
    for i in range(len(rows) - 1):
        for j in range(seg):
            a0, a1 = i * seg + j, i * seg + (j + 1) % seg
            faces.append([a0, a1, a1 + seg, a0 + seg])
    if close_top:
        top = sum(rows[0], Vector()) / seg
        verts.append(top)
        t = len(verts) - 1
        faces += [[t, (j + 1) % seg, j] for j in range(seg)]
    return make(name, verts, faces, mat_name)


def make(name, verts, faces, mat_name):
    me = bpy.data.meshes.new(name)
    me.from_pydata([to_bl(v) for v in verts], [], faces)
    uv = me.uv_layers.new(name="UV")
    for li, loop in enumerate(me.loops):
        p = verts[loop.vertex_index]
        uv.data[li].uv = (p.x / W, 1 - p.y / H)
    for poly in me.polygons:
        poly.use_smooth = False
    me.materials.append(bpy.data.materials[mat_name])
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


SEG = 16
phis = [math.pi / 2 + 2 * math.pi * j / SEG for j in range(SEG)]  # start at the front

# skull: stays behind the face surface wherever the face covers it
rows = []
for i in range(1, 10):
    th = math.pi * i / 10
    ring = []
    for ph in phis:
        p = ell(C, a, b, c, th, ph)
        _, k, dist = fkd.find((p.x, p.y, 0))
        if dist < 40 and p.z > F[k].z - 8:
            p.z = F[k].z - 8
        ring.append(p)
    rows.append(ring)
grid_mesh("skull", rows, "face")

# beanie: cap whose rim runs over the forehead in front, over the ears on the sides
ba, bb, bc = a * 1.1, b * 1.05, c * 1.1
front_cut = F[10].y + fh * 0.04
side_cut = cy - b * 0.12
back_cut = cy + b * 0.05


EDGE = M["beanie_edge"]  # [x, lowest knit pixel y] along the photo


def edge_y(x):
    if x <= EDGE[0][0] or x >= EDGE[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(EDGE, EDGE[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def generic_rim(ph):
    s_ = math.sin(ph)
    return side_cut + (front_cut - side_cut) * max(0, s_) ** 1.5 + (back_cut - side_cut) * max(0, -s_)


def th_for(y):
    return math.acos(max(-1, min(1, (cy - y) / bb)))


K = 6
rows = [[None] * SEG for _ in range(K)]
for j, ph in enumerate(phis):
    y = generic_rim(ph)
    w = max(0, math.sin(ph)) ** 1.5
    if w > 0:
        # front: follow the real knit edge from the mask (fixed-point on the rim's x)
        for _ in range(3):
            x = C.x + ba * math.sin(th_for(y)) * math.cos(ph)
            ey = edge_y(x)
            if ey is None:
                break
            y = ey * w + generic_rim(ph) * (1 - w)
    th_max = th_for(y)
    for k in range(K):
        rows[k][j] = ell(C, ba, bb, bc, th_max * (k + 1) / K, ph)
grid_mesh("beanie", rows, "beanie")

# hood: bigger shell with a face opening, skirt tucked under the collar
ha = (M["hood_right"] - M["hood_left"]) / 2
hcx = (M["hood_right"] + M["hood_left"]) / 2
hb = cy - M["hood_top"]
hc = c * 1.25
HC = Vector((hcx, cy, cd - c * 0.05))
open_l, open_r = M["beanie_left"] - a * 0.08, M["beanie_right"] + a * 0.08
open_t, open_b = M["beanie_top"] - fh * 0.02, chin + fh * 0.08
neck_y = chin + fh * 0.2
# Pole of the shell points at the camera: the face opening is simply the first ring,
# a clean oval following the beanie and the jaw, instead of quads cut out of a sphere.
HSEG = 20
hphis = [2 * math.pi * j / HSEG for j in range(HSEG)]


def hood_pt(al, ph):
    p = HC + Vector((ha * math.sin(al) * math.cos(ph), hb * math.sin(al) * math.sin(ph), hc * math.cos(al)))
    if p.y > cy:  # lower half hangs further down and tucks under the collar
        p.y = cy + (p.y - cy) * 1.75
        p.z -= (p.y - chin) * 0.25 if p.y > chin else 0  # hem slopes back into the collar
    return p


def rim_alpha(ph):
    ro = math.hypot(orx * math.cos(ph), ory * math.sin(ph))
    rh = math.hypot(ha * math.cos(ph), hb * math.sin(ph))
    return math.asin(min(0.97, ro / rh))


orx, ory = (open_r - open_l) / 2, (open_b - open_t) / 2
rims = [rim_alpha(ph) for ph in hphis]
rows = []
K = 7
for k in range(K):
    rows.append([hood_pt(al + (math.pi * 0.97 - al) * k / K, ph) for al, ph in zip(rims, hphis)])
# folded edge: the rim rolls inward and back, gives the hood a thick lip
lip = [HC + (p - HC) * 0.9 + Vector((0, 0, -hc * 0.12)) for p in rows[0]]
rows.insert(0, lip)
back_pole = hood_pt(math.pi, 0)
hood = grid_mesh("hood", rows[::-1], "clothes")  # reversed: the back pole closes the shell
top_i = len(hood.data.vertices) - 1
hood.data.vertices[top_i].co = to_bl(back_pole)
# jacket: remove the old flat hood region, the new hood + skirt replaces it
cl = bpy.data.objects["clothes"]
bm = bmesh.new()
bm.from_mesh(cl.data)
kill = [f for f in bm.faces
        if (lambda p: p.y < chin and abs(p.x - hcx) < ha * 1.05)(to_px(f.calc_center_median()))]
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.to_mesh(cl.data)
bm.free()

# --- hand: anchored where it leaves the frame (bottom-right), a bit smaller than the selfie made it ---
hand = bpy.data.objects["hand"]
hp = [to_px(v.co) for v in hand.data.vertices]
wrist = Vector((W + 150, H + 120, sum(p.z for p in hp) / len(hp)))  # off-screen: the arm comes from there
# nudge it into the card: the photo edge it was cut at stays inside the hidden margin (edges are padded)
nudge = Vector((-135, -75, 0))
for v, p in zip(hand.data.vertices, hp):
    v.co = to_bl(p + nudge)
wrist = wrist + nudge
hw = max(p.x for p in hp) - min(p.x for p in hp)
direction = Vector((0.35, 1.0, 0.55)).normalized()

# --- teeth: an arc following the smile, not a slab ---
mc = (F[61] + F[291]) / 2
mw = (F[291] - F[61]).length
lip_d = sum(F[i].z for i in (13, 82, 312)) / 3
tv, tf = [], []
N = 8
for k in range(N + 1):
    u = k / N - 0.5
    x = mc.x + u * mw * 0.58
    arc = (2 * u) ** 2 * mw * 0.06                   # corners sit higher: follows the smile
    d = lip_d - mw * 0.1 - (2 * u) ** 2 * mw * 0.14
    notch = mw * 0.012 if k % 2 else 0               # little gaps between teeth on the lower edge
    tv += [Vector((x, mc.y - mw * 0.06 - arc, d)), Vector((x, mc.y + mw * 0.07 - arc - notch, d - 1))]
tf = [[2 * k, 2 * k + 2, 2 * k + 3, 2 * k + 1] for k in range(N)]
teeth_mat = bpy.data.materials.get("Teeth")
me = bpy.data.meshes.new("teeth")
me.from_pydata([to_bl(v) for v in tv], [], tf)
me.materials.append(teeth_mat)
o = bpy.data.objects.new("teeth", me)
bpy.context.scene.collection.objects.link(o)

json.dump({"skull": [cx, cy, cd, a, b, c], "neck_y": neck_y, "chin": chin, "fh": fh,
           "wrist": list(wrist), "arm_dir": list(direction), "hw": hw},
          open(os.path.join(ROOT, "out/rig_points.json"), "w"))
print(sorted(o.name for o in bpy.data.objects if o.type == "MESH"))
