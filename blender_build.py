"""Build the low-poly character in the running Blender (sent via run.sh)."""
import json
import os

import bmesh
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

ROOT = globals().get("ROOT") or os.path.dirname(os.path.abspath(__file__))
S = 2400.0  # photo pixels per meter
face = json.load(open(os.path.join(ROOT, "out/face.json")))
parts = json.load(open(os.path.join(ROOT, "out/parts.json")))
W, H = face["w"], face["h"]

# --- clean scene ---
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
    for d in list(coll):
        if d.users == 0:
            coll.remove(d)

# --- photo material, nearest filtering for the old-school look ---
def photo_material(name, path):
    img = bpy.data.images.load(os.path.join(ROOT, path), check_existing=True)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"
    emit = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


MAT = {n: photo_material(n, f"out/tex_{n}.jpg") for n in ("clothes", "face", "beanie", "head", "hand")}


def kd_of(verts):
    kd = KDTree(len(verts))
    for i, v in enumerate(verts):
        kd.insert((v[0], v[1], 0), i)
    kd.balance()
    return kd


def depth_under(part, x, y):
    """Depth of an already-placed part at photo point (x, y) (nearest vertex)."""
    _, i, _ = part["kd"].find((x, y, 0))
    return part["verts"][i][2]


def make_object(name, verts, tris, mat=None, uvs=None):
    mat = mat or MAT[name]
    me = bpy.data.meshes.new(name)
    co = [((x - W / 2) / S, -d / S, (H - y) / S) for x, y, d in verts]
    me.from_pydata(co, [], tris)
    uv = me.uv_layers.new(name="UV")
    for poly in me.polygons:
        poly.use_smooth = False
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            x, y = uvs[vi] if uvs else verts[vi][:2]
            uv.data[li].uv = (x / W, 1 - y / H)
    # consistent normals facing the camera (-Y)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if sum(f.normal.y * f.calc_area() for f in bm.faces) > 0:
        for f in bm.faces:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# --- stack parts front-to-back: clothes -> head -> face/beanie -> hand ---
placed = {}
for name in ["clothes", "head", "neck", "beanie", "hand"]:
    if name not in parts:
        continue
    p = parts[name]
    vs = p["verts"]
    if name == "head":
        cx = sum(v[0] for v in vs) / len(vs)
        cy = sum(v[1] for v in vs) / len(vs)
        base = depth_under(placed["clothes"], cx, cy) * 0.6
        vs = [[x, y, d + base] for x, y, d in vs]
    elif name in ("beanie", "neck"):
        vs = [[x, y, d + depth_under(placed["head"], x, y) * 0.9] for x, y, d in vs]
    elif name == "hand":
        top = max(v[2] for v in placed["clothes"]["verts"])
        base = depth_under(placed["clothes"], 1100, 2200) + 60
        vs = [[x, y, d + base] for x, y, d in vs]
    placed[name] = {"verts": vs, "kd": kd_of(vs)}
    tris = p["tris"]
    uvs = None
    if name == "hand":
        # closed volume: mirrored back side, stitched at the silhouette (where d == 0)
        n = len(vs)
        back = [[x, y, base - (d - base) * 0.6] for x, y, d in vs]
        vs = vs + back
        tris = tris + [[c + n, b + n, a + n] for a, b, c in tris]
    make_object(name, vs, tris)

# --- face: MediaPipe mesh, relief on top of the head blob ---
pts = face["points"]
zmax = max(p[2] for p in pts)
head = placed["head"]
fv = []
for x, y, z in pts:
    px, py = x * W, y * H
    relief = (zmax - z) * W
    fv.append([px, py, depth_under(head, px, py) * 0.55 + relief * 0.9])
# extrude the open border of the face backwards: cheeks, jaw and temples
from collections import Counter
ec = Counter(tuple(sorted(e)) for t in face["tris"] for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))
border = {e for e, c in ec.items() if c == 1}
# keep only the outer loop (the one through forehead landmark 10); eyes and mouth holes stay open
outer, todo = set(), [10]
while todo:
    v = todo.pop()
    if v in outer:
        continue
    outer.add(v)
    todo += [b if a == v else a for a, b in border if v in (a, b)]
border = {e for e in border if e[0] in outer}
bverts = sorted({v for e in border for v in e})
cx = sum(v[0] for v in fv) / len(fv)
cy = sum(v[1] for v in fv) / len(fv)
uvs = [v[:2] for v in fv]
ring = {}
for layer, (grow, back) in enumerate([(1.03, 45), (1.05, 110)]):  # short: the skull fills the rest
    new = {}
    for i in bverts:
        src = ring.get(i, i) if layer else i
        x, y, d = fv[i]
        new[i] = len(fv)
        fv.append([cx + (x - cx) * grow, cy + (y - cy) * grow, d - back])
        uvs.append(uvs[i])  # stretched edge pixels, the classic look
    ring = new
    prev = {i: (i if layer == 0 else prev_ring[i]) for i in bverts}
    prev_ring = new
    for a, b in border:
        pa, pb = prev[a], prev[b]
        face["tris"].append([pa, pb, new[b]])
        face["tris"].append([pa, new[b], new[a]])
make_object("face", fv, face["tris"], uvs=uvs)

# --- camera + viewport ---
cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 50
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = (0, -3.2, (H * 0.55) / S)
cam.rotation_euler = (1.5708, 0, 0)
scene = bpy.context.scene
scene.camera = cam
scene.render.resolution_x, scene.render.resolution_y = 720, 1100

for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        sp = area.spaces.active
        sp.shading.type = "SOLID"
        sp.shading.light = "FLAT"
        sp.shading.color_type = "TEXTURE"
        sp.overlay.show_wireframes = False
        with bpy.context.temp_override(area=area, region=area.regions[-1]):
            bpy.ops.view3d.view_all()

print({o.name: len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH"})
