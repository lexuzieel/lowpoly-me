"""Export the character to web/me.glb (geometry + UVs; textures are loaded separately)."""
import os

import bpy

ROOT = globals().get("ROOT") or os.path.dirname(os.path.abspath(__file__))
bpy.ops.object.select_all(action="DESELECT")
for o in bpy.data.objects:
    if o.type in ("MESH", "ARMATURE"):
        o.select_set(True)
bpy.ops.export_scene.gltf(filepath=os.path.join(ROOT, "web/me.glb"), use_selection=True,
                          export_format="GLB", export_materials="NONE", export_normals=True,
                          export_skins=True, export_morph=True, export_animations=False)
print(os.path.getsize(os.path.join(ROOT, "web/me.glb")))
