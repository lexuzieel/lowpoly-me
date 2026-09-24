"""Extract face landmarks (3D) and segmentation masks from photo.jpg -> out/"""
import json
import os

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision

os.makedirs("out", exist_ok=True)
img_bgr = cv2.imread("photo.jpg")
h, w = img_bgr.shape[:2]
img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))

# Face landmarks: 478 points, x/y normalized to image, z relative depth (same scale as x)
fl = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
    base_options=mpt.BaseOptions(model_asset_path="models/face_landmarker.task"),
    output_face_blendshapes=True, num_faces=1))
res = fl.detect(img)
lm = res.face_landmarks[0]
pts = [[p.x, p.y, p.z] for p in lm]

# Canonical triangulation shipped with mediapipe
edges = {tuple(sorted((c.start, c.end))) for c in vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION}
adj = {}
for a, b in edges:
    adj.setdefault(a, set()).add(b)
    adj.setdefault(b, set()).add(a)
tris = set()
for a, b in edges:
    for c in adj[a] & adj[b]:
        tris.add(tuple(sorted((a, b, c))))

json.dump({"w": w, "h": h, "points": pts, "tris": sorted(tris)}, open("out/face.json", "w"))
print("landmarks", len(pts), "tris", len(tris))

# Multiclass selfie segmentation: 0 bg, 1 hair, 2 body-skin, 3 face-skin, 4 clothes, 5 others
seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
    base_options=mpt.BaseOptions(model_asset_path="models/selfie_multiclass.tflite"),
    output_category_mask=True))
cat = np.squeeze(seg.segment(img).category_mask.numpy_view()).astype(np.uint8)
print("seg", cat.shape, np.unique(cat))
cv2.imwrite("out/seg.png", cat)
palette = np.array([[0, 0, 0], [0, 200, 255], [80, 80, 255], [0, 255, 0], [255, 0, 0], [255, 0, 255]], np.uint8)
vis = cv2.addWeighted(img_bgr, 0.5, palette[cat], 0.5, 0)
for p in pts:
    cv2.circle(vis, (int(p[0] * w), int(p[1] * h)), 2, (255, 255, 255), -1)
cv2.imwrite("out/debug.jpg", vis)
fl.close(); seg.close()
