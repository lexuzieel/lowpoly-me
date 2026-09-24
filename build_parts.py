"""Turn segmentation masks into inflated low-poly meshes -> out/parts.json

Coordinates are photo pixels (x right, y down) plus depth d in pixels (bigger = closer to camera).
Blender side converts to meters."""
import json

import cv2
import numpy as np

seg = cv2.imread("out/seg.png", cv2.IMREAD_GRAYSCALE)
face = json.load(open("out/face.json"))
H, W = seg.shape

# 0 bg, 1 hair, 2 body-skin, 3 face-skin, 4 clothes, 5 others (beanie)
def clean(m, k=9):
    m = cv2.morphologyEx(m.astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))


def components(m):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    return [(lab == i).astype(np.uint8) * 255 for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 3000]


def inflate_mesh(mask, spacing, depth_scale, fill_holes=False, strict=True):
    """Triangulate mask with ~spacing px triangles; depth = rounded profile of distance to edge."""
    m = mask.copy()
    if fill_holes:
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(m, cnts, -1, 255, -1)
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    R = dist.max()

    pts = []
    cnts, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    for c in cnts:
        if cv2.contourArea(c) < 500:
            continue
        approx = cv2.approxPolyDP(c, spacing * 0.12, True)[:, 0, :]
        # resample so boundary edges are not longer than spacing
        for i in range(len(approx)):
            a, b = approx[i].astype(float), approx[(i + 1) % len(approx)].astype(float)
            n = max(1, int(np.linalg.norm(b - a) / (spacing * 0.7)))
            for t in range(n):
                pts.append(a + (b - a) * t / n)
    # interior: jittered grid, denser near edges looks nicer but keep it simple
    rng = np.random.default_rng(1)
    for y in np.arange(0, H, spacing):
        for x in np.arange(0, W, spacing * 0.866):
            px = x + (spacing / 2 if int(y / spacing) % 2 else 0) + rng.uniform(-.15, .15) * spacing
            py = y + rng.uniform(-.15, .15) * spacing
            xi, yi = int(px), int(py)
            if 0 <= xi < W and 0 <= yi < H and dist[yi, xi] > spacing * 0.45 and mask[yi, xi]:
                pts.append(np.array([px, py]))
    pts = np.array(pts)

    sub = cv2.Subdiv2D((0, 0, W, H))
    for p in pts:
        sub.insert((float(np.clip(p[0], 0, W - 1)), float(np.clip(p[1], 0, H - 1))))
    idx = {}
    verts, tris = [], []

    def vid(x, y):
        key = (round(x, 2), round(y, 2))
        if key not in idx:
            d = dist[min(int(y), H - 1), min(int(x), W - 1)]
            depth = np.sqrt(max(R * R - (R - d) ** 2, 0)) * depth_scale
            idx[key] = len(verts)
            verts.append([float(x), float(y), float(depth)])
        return idx[key]

    for t in sub.getTriangleList():
        p = t.reshape(3, 2)
        if (p < 0).any() or (p[:, 0] >= W).any() or (p[:, 1] >= H).any():
            continue
        c = p.mean(0)
        # keep triangle only if it lies inside the mask (centroid + edge midpoints)
        probes = [c] + [(p[i] + p[(i + 1) % 3]) / 2 * 0.8 + c * 0.2 for i in range(3)]
        if all(mask[int(q[1]), int(q[0])] for q in (probes if strict else probes[:1])):
            tris.append([vid(*p[0]), vid(*p[1]), vid(*p[2])])
    return {"verts": verts, "tris": tris}


parts = {}
img = cv2.imread("photo.jpg")
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
yellow = (hsv[..., 0] >= 12) & (hsv[..., 0] <= 35) & (hsv[..., 1] > 90) & (hsv[..., 2] > 60)
person = clean(seg != 0, 5)

beanie = clean(yellow & ((seg == 5) | (seg == 1)), 9)
beanie = max(components(beanie), key=lambda c: c.sum())
face_skin = clean(seg == 3, 9)
head = clean((face_skin > 0) | (beanie > 0), 9)
skin = clean(seg == 2, 9)
hand_mask = max(components(skin), key=lambda c: np.nonzero(c)[0].mean())

# clothes = the whole person silhouette minus head, filled behind the hand, smoothed
clothes = cv2.bitwise_or(person, cv2.dilate(hand_mask, np.ones((25, 25), np.uint8)))
clothes = cv2.GaussianBlur(cv2.morphologyEx(clothes, cv2.MORPH_CLOSE, np.ones((61, 61), np.uint8)), (41, 41), 0)
clothes = ((clothes > 127) * 255).astype(np.uint8)
cnts, _ = cv2.findContours(clothes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
clothes = np.zeros_like(clothes)
cv2.drawContours(clothes, [max(cnts, key=cv2.contourArea)], -1, 255, -1)
clothes &= ~cv2.erode(head, np.ones((41, 41), np.uint8))  # hole for the head, slightly tucked under

# clothes texture: keep dark jacket pixels, repaint everything else (snow, lamps, hand, skin)
dark = hsv[..., 2] < 110
yy = np.arange(H)[:, None].repeat(W, 1)
xx = np.arange(W)[None, :].repeat(H, 0)
logo = (yy > H * 0.85) & (xx > W * 0.7) & (xx < W * 0.82)
blue = (hsv[..., 0] >= 90) & (hsv[..., 0] <= 135) & (hsv[..., 1] > 60)
keep = ((seg == 4) | (seg == 5)) & ~yellow & ~blue & (dark | logo) & (cv2.erode(clean(seg != 0, 5), np.ones((9, 9), np.uint8)) > 0)
keep = keep & ~(cv2.dilate(hand_mask, np.ones((31, 31), np.uint8)) > 0)


def part_texture(name, keep_mask):
    """Photo where every pixel outside keep_mask is repainted from inside it."""
    hole = (~keep_mask).astype(np.uint8) * 255
    q = 6
    small = cv2.resize(img, (W // q, H // q), interpolation=cv2.INTER_AREA)
    hs = cv2.resize(hole, (W // q, H // q), interpolation=cv2.INTER_NEAREST)
    filled = cv2.resize(cv2.inpaint(small, hs, 25, cv2.INPAINT_TELEA), (W, H))
    cv2.imwrite(f"out/tex_{name}.jpg", np.where(hole[..., None] > 0, filled, img))


part_texture("clothes", keep)
part_texture("face", cv2.erode(face_skin, np.ones((7, 7), np.uint8)) > 0)
part_texture("beanie", cv2.erode(beanie, np.ones((7, 7), np.uint8)) > 0)
part_texture("head", cv2.erode(head, np.ones((7, 7), np.uint8)) > 0)
# eyes: keep only the visible eyeball inside the lids, spread it outward for the rotating eyeballs
pts = np.array(face["points"])[:, :2] * [W, H]
eye_mask = np.zeros((H, W), np.uint8)
for loop in ([33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7],
             [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249]):
    cv2.fillPoly(eye_mask, [pts[loop].astype(np.int32)], 255)
eye_mask = cv2.erode(eye_mask, np.ones((3, 3), np.uint8))
hole = (eye_mask == 0).astype(np.uint8) * 255
x0, y0 = pts[[33, 263]].min(0).astype(int) - 60
x1, y1 = pts[[33, 263]].max(0).astype(int) + 60
crop = img[y0:y1, x0:x1]
filled = cv2.inpaint(crop, hole[y0:y1, x0:x1], 9, cv2.INPAINT_TELEA)
eyes = img.copy()
eyes[y0:y1, x0:x1] = filled
cv2.imwrite("out/tex_eyes.jpg", eyes)
part_texture("hand", cv2.erode(hand_mask, np.ones((5, 5), np.uint8)) > 0)

parts["clothes"] = inflate_mesh(clothes, 90, 0.8, fill_holes=True)
parts["beanie"] = inflate_mesh(beanie, 45, 0.5)
parts["head"] = inflate_mesh(head, 60, 0.9)
parts["hand"] = inflate_mesh(hand_mask, 30, 1.2, strict=False)  # fine + lenient: no holes in narrow fingers

for k, v in parts.items():
    print(k, len(v["verts"]), "verts", len(v["tris"]), "tris")
json.dump(parts, open("out/parts.json", "w"))

# --- measurements for the 3D shells (hood / beanie / skull) ---
fp = np.array(face["points"])[:, :2] * [W, H]
eye_y = int(fp[168][1])
cx_face = (fp[234][0] + fp[454][0]) / 2
row = np.nonzero(person[eye_y])[0]
# contiguous run of the person mask around the face at eye level = hood width
runs = np.split(row, np.where(np.diff(row) > 1)[0] + 1)
hood_run = min(runs, key=lambda r: 0 if r[0] <= cx_face <= r[-1] else abs((r[0] + r[-1]) / 2 - cx_face))
col = np.nonzero(person[:, int(cx_face)])[0]
bys, bxs = np.nonzero(beanie)
# lowest beanie pixel per column: the real knit edge, sampled every 8 px
edge = []
for x in range(int(bxs.min()), int(bxs.max()) + 1, 8):
    ys_col = np.nonzero(beanie[:, x])[0]
    if len(ys_col):
        edge.append([x, int(ys_col.max())])
metrics = {
    "beanie_edge": edge,
    "hood_left": int(hood_run[0]), "hood_right": int(hood_run[-1]),
    "hood_top": int(col.min()),
    "beanie_top": int(bys.min()), "beanie_left": int(bxs.min()), "beanie_right": int(bxs.max()),
}
json.dump(metrics, open("out/metrics.json", "w"))
print(metrics)
