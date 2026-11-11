"""Blender script: renders game cartridges with their real label, cover-flow style.

Run by maak_bibliotheek.py:
  blender -b --factory-startup --python render_carts.py -- jobs.json

jobs.json = {"poses": [...], "supersample": 3, "samples": 64,
             "jobs": [{"system": "gba|gb|gbc", "body": [r,g,b], "clear": false,
                       "label": "label.png" or null, "out": "dir"}]}

For every job and pose it writes <out>/<pose>.png (RGBA, final size) and
<out>/poses.json with the anchor (cart bottom-centre) and the label rectangle
(front pose only) in image pixels.

The cartridges are modelled here from the real dimensions (mm); nothing is
taken from other models. Units: 1 Blender unit = 1 metre.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

MM = 0.001

# Real cartridge dimensions (mm) and label area.
SPECS = {
    "gba": dict(w=57.0, h=35.0, d=8.0, lw=44.0, lh=22.5, ltop=2.6, corner=None),
    "gb":  dict(w=57.0, h=65.0, d=7.6, lw=44.0, lh=38.5, ltop=14.0, corner=6.0),
}
SPECS["gbc"] = SPECS["gb"]
SPECS["folder"] = dict(w=60.0, h=46.0, d=4.0, lw=40.0, lh=15.0, ltop=0, corner=None)
# NES (72-pin): portrait label in a recess at the top, grip grooves beside it
# and horizontal ridges at the bottom.
SPECS["nes"] = dict(w=120.0, h=133.0, d=17.0, lw=56.0, lh=92.0, ltop=4.0, corner=None)

# Pixels per mm on screen for the front pose (fits ~128x84 px).
SCALE = {"gba": 2.20, "gb": 1.26, "gbc": 1.26, "folder": 1.62, "nes": 0.64}


# ---------------------------------------------------------------------------
# Scene helpers

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def apply_mods(obj):
    bpy.context.view_layer.objects.active = obj
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def box(name, sx, sy, sz, loc, rot_y=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((sx, sy, sz)), verts=bm.verts)
    if rot_y:
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(rot_y, 3, 'Y'))
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def multi_box(name, boxes):
    """One cutter object made of several boxes (sx, sy, sz, loc): one boolean."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for sx, sy, sz, loc in boxes:
        r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector((sx, sy, sz)), verts=r["verts"])
        bmesh.ops.translate(bm, vec=Vector(loc), verts=r["verts"])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def boolean_cut(target, cutter):
    m = target.modifiers.new("cut", 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.solver = 'EXACT'
    m.object = cutter
    apply_mods(target)
    bpy.data.objects.remove(cutter)


def rounded_rect(name, w, h, r, seg=6):
    """Flat rounded rectangle in the XZ plane (normal -Y), UVs 0..1."""
    pts = []
    for cx, cz, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new((x, 0.0, z)) for x, z in pts]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.y > 0:
        f.normal_flip()
    uv = bm.loops.layers.uv.new("UVMap")
    for loop in f.loops:
        x, _, z = loop.vert.co
        loop[uv].uv = ((x + w / 2) / w, (z + h / 2) / h)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------------------
# Materials

def plastic_material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.36
    p.inputs["Coat Weight"].default_value = 0.12
    p.inputs["Coat Roughness"].default_value = 0.18
    # Fine moulded-plastic grain.
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4000.0
    noise.inputs["Detail"].default_value = 2.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def set_plastic(m, rgb, clear):
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*rgb, 1.0)
    p.inputs["Transmission Weight"].default_value = 0.75 if clear else 0.0
    p.inputs["Roughness"].default_value = 0.22 if clear else 0.36


def label_material():
    m = bpy.data.materials.new("label")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.42
    p.inputs["Coat Weight"].default_value = 0.35
    p.inputs["Coat Roughness"].default_value = 0.12
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = "labeltex"
    tex.extension = 'EXTEND'
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.name = "map"
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], p.inputs["Base Color"])
    # A touch of self-illumination keeps labels vivid at 240x160.
    nt.links.new(tex.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = 0.12
    return m


def set_label(m, path, label_aspect):
    nt = m.node_tree
    tex = nt.nodes["labeltex"]
    mp = nt.nodes["map"]
    p = nt.nodes["Principled BSDF"]
    if not path:
        tex.image = None
        # Blank label: off-white paper.
        for l in list(p.inputs["Base Color"].links):
            nt.links.remove(l)
        p.inputs["Base Color"].default_value = (0.86, 0.85, 0.82, 1.0)
        for l in list(p.inputs["Emission Color"].links):
            nt.links.remove(l)
        p.inputs["Emission Color"].default_value = (0.86, 0.85, 0.82, 1.0)
        return
    if not p.inputs["Base Color"].links:
        nt.links.new(tex.outputs["Color"], p.inputs["Base Color"])
        nt.links.new(tex.outputs["Color"], p.inputs["Emission Color"])
    old = tex.image
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = 'sRGB'
    tex.image = img
    if old and old.users == 0:
        bpy.data.images.remove(old)
    # Cover-fit the scan into the label area (centre crop).
    ia = img.size[0] / max(1, img.size[1])
    sx = sy = 1.0
    if ia > label_aspect:
        sx = label_aspect / ia
    else:
        sy = ia / label_aspect
    mp.inputs["Scale"].default_value = (sx, sy, 1.0)
    mp.inputs["Location"].default_value = ((1 - sx) / 2, (1 - sy) / 2, 0.0)


# ---------------------------------------------------------------------------
# Cartridge models

def build_cart(system, body_mat, lab_mat):
    s = SPECS[system]
    W, H, D = s["w"] * MM, s["h"] * MM, s["d"] * MM
    body = box("cart_" + system, W, D, H, (0, 0, H / 2))
    bev = body.modifiers.new("bevel", 'BEVEL')
    bev.width = 0.9 * MM
    bev.segments = 4
    bev.limit_method = 'ANGLE'
    apply_mods(body)

    front = -D / 2
    if s["corner"]:
        # Game Boy: cut-off top-right corner.
        c = s["corner"] * MM
        cut = box("cut", c * 1.4142, D * 2, c * 1.4142, (0, 0, 0))
        cut.data.transform(Matrix.Translation((W / 2, 0, H)) @ Matrix.Rotation(math.radians(45), 4, 'Y'))
        boolean_cut(body, cut)
        # Grip ridges across the top of the front face.
        for i in range(6):
            z = H - 3.2 * MM - i * 1.5 * MM
            g = box("g", 40 * MM, 0.8 * MM, 0.55 * MM, (-3.0 * MM, front, z))
            boolean_cut(body, g)
        # Moulded arrow below the label.
        arrow_z = 5.0 * MM
        me = bpy.data.meshes.new("arrow")
        bm = bmesh.new()
        a = 2.4 * MM
        top = [bm.verts.new((x, y, z)) for x, y, z in ((-a, front - 1 * MM, arrow_z + a * 0.8),
                                                        (a, front - 1 * MM, arrow_z + a * 0.8),
                                                        (0, front - 1 * MM, arrow_z - a * 0.6))]
        bot = [bm.verts.new((v.co.x, front + 0.35 * MM, v.co.z)) for v in top]
        bm.faces.new(top)
        bm.faces.new(list(reversed(bot)))
        for i in range(3):
            bm.faces.new((top[i], top[(i + 1) % 3], bot[(i + 1) % 3], bot[i]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        arrow = bpy.data.objects.new("arrow", me)
        bpy.context.scene.collection.objects.link(arrow)
        boolean_cut(body, arrow)
    elif system == "nes":
        lw, lh = s["lw"] * MM, s["lh"] * MM
        top = H - s["ltop"] * MM
        cuts = []
        # Vertical grip grooves left and right of the label.
        for side in (-1, 1):
            for i in range(7):
                x = side * (lw / 2 + 7.0 * MM + i * 4.2 * MM)
                cuts.append((1.4 * MM, 1.6 * MM, lh - 10 * MM, (x, front, top - lh / 2 - 2 * MM)))
        # Horizontal ridges across the bottom.
        for i in range(8):
            z = 7.0 * MM + i * 3.6 * MM
            cuts.append((W - 16 * MM, 1.6 * MM, 1.3 * MM, (0, front, z)))
        boolean_cut(body, multi_box("grips", cuts))
    else:
        # GBA: side notches near the bottom + a groove line under the label.
        for sx in (-1, 1):
            n = box("n", 2.4 * MM, D * 2, 6.0 * MM, (sx * W / 2, 0, 5.2 * MM))
            boolean_cut(body, n)
        g = box("g", 40 * MM, 0.7 * MM, 0.5 * MM, (0, front, 4.2 * MM))
        boolean_cut(body, g)

    # Label recess.
    lw, lh = s["lw"] * MM, s["lh"] * MM
    lz = H - s["ltop"] * MM - lh / 2
    rec = box("rec", lw + 1.2 * MM, 1.0 * MM, lh + 1.2 * MM, (0, front, lz))
    boolean_cut(body, rec)

    body.data.materials.clear()          # booleans leave an empty slot behind
    body.data.materials.append(body_mat)
    for poly in body.data.polygons:
        poly.material_index = 0
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    bpy.ops.object.shade_auto_smooth(angle=math.radians(40))
    body.select_set(False)

    label = rounded_rect("label_" + system, lw, lh, 1.6 * MM)
    label.location = (0, front + 0.42 * MM, lz)
    label.data.materials.append(lab_mat)

    root = bpy.data.objects.new("root_" + system, None)
    bpy.context.scene.collection.objects.link(root)
    body.parent = root
    label.parent = root
    return root, (lw, lh, lz, front + 0.42 * MM)


def build_folder(body_mat, lab_mat):
    """A manila folder (for sub directories), slightly open."""
    W, H = 60 * MM, 46 * MM
    back = box("folder_back", W, 0.9 * MM, H, (0, 1.2 * MM, H / 2))
    tab = box("folder_tab", 22 * MM, 0.9 * MM, 5 * MM, (-W / 2 + 13 * MM, 1.2 * MM, H + 2.0 * MM))
    front = box("folder_front", W, 0.9 * MM, H - 5 * MM, (0, 0, (H - 5 * MM) / 2))
    front.data.transform(Matrix.Translation((0, -1.2 * MM, 0)) @ Matrix.Rotation(math.radians(-7), 4, 'X'))
    paper = box("folder_paper", W - 6 * MM, 0.4 * MM, H - 2 * MM, (0, 0.5 * MM, (H - 2 * MM) / 2))
    root = bpy.data.objects.new("root_folder", None)
    bpy.context.scene.collection.objects.link(root)
    for ob in (back, tab, front):
        bev = ob.modifiers.new("bevel", 'BEVEL')
        bev.width = 0.35 * MM
        bev.segments = 2
        apply_mods(ob)
        ob.data.materials.append(body_mat)
        ob.parent = root
    paper.data.materials.append(lab_mat)
    paper.parent = root
    # Name sticker on the front flap.
    lw, lh = 40 * MM, 15 * MM
    lz = (H - 5 * MM) * 0.55
    ang = math.radians(-7)
    label = rounded_rect("label_folder", lw, lh, 1.2 * MM)
    label.data.transform(Matrix.Translation((0, -1.2 * MM, 0)) @ Matrix.Rotation(ang, 4, 'X') @
                         Matrix.Translation((0, -0.5 * MM, lz)))
    label.data.materials.append(lab_mat)
    label.parent = root
    ly = -1.2 * MM - 0.5 * MM - lz * math.sin(-ang)
    return root, (lw, lh, lz * math.cos(ang), ly)


# ---------------------------------------------------------------------------
# GBA: external model "Gameboy Advance Cartridge" by Vxcl (CC-BY-4.0,
# https://sketchfab.com/3d-models/gameboy-advance-cartridge-38c1e6702e5d4f21af1d0930689b1d10)

GBA_PLASTIC = ("Cartrough", "cARTsmooth")


def build_gba_model(path, lab_mat):
    """Imports the GBA cart model, faces it to the camera, scales it to 57 mm
    and gives the label face our own 0..1 UVs + the label material."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    meshes = {}
    for o in new:
        if o.type == 'MESH' and o.material_slots:
            meshes[o.material_slots[0].material.name] = o
    keep = [meshes[n] for n in GBA_PLASTIC + ("gblabel",) if n in meshes]
    # Bake the hierarchy away, drop the screw (back side) and the PCB (inside).
    for o in keep:
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
    for o in new:
        if o not in keep:
            bpy.data.objects.remove(o)

    # Model space: label on +X, Z up. Turn it so the label faces -Y (camera).
    ws = [v.co for o in keep for v in o.data.vertices]
    mn = Vector([min(v[i] for v in ws) for i in range(3)])
    mx = Vector([max(v[i] for v in ws) for i in range(3)])
    width = mx.y - mn.y
    k = 57.0 * MM / width
    m = (Matrix.Rotation(math.radians(-90), 4, 'Z') @ Matrix.Scale(k, 4) @
         Matrix.Translation((-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z)))
    for o in keep:
        o.data.transform(m)

    root = bpy.data.objects.new("root_gba", None)
    bpy.context.scene.collection.objects.link(root)
    for o in keep:
        o.parent = root
        bpy.context.view_layer.objects.active = o

    label = meshes.get("gblabel")
    lb = [v.co for v in label.data.vertices]
    lx0, lx1 = min(v.x for v in lb), max(v.x for v in lb)
    lz0, lz1 = min(v.z for v in lb), max(v.z for v in lb)
    ly = min(v.y for v in lb) - 0.02 * MM
    for v in label.data.vertices:
        v.co.y -= 0.02 * MM           # Just in front of the moulded recess
    uv = label.data.uv_layers.active
    for loop in label.data.loops:
        co = label.data.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = ((co.x - lx0) / (lx1 - lx0), (co.z - lz0) / (lz1 - lz0))
    label.data.materials.clear()
    label.data.materials.append(lab_mat)

    # Tint stage on the plastic: base colour x (target / average colour).
    mats = []
    for n in GBA_PLASTIC:
        if n not in meshes:
            continue
        mat = meshes[n].material_slots[0].material
        nt = mat.node_tree
        p = next(x for x in nt.nodes if x.type == 'BSDF_PRINCIPLED')
        link = p.inputs["Base Color"].links[0]
        tex = link.from_node
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.clamp_result = False
        mix.inputs["Factor"].default_value = 0.0
        nt.links.new(link.from_socket, mix.inputs[6])
        nt.links.new(mix.outputs[2], p.inputs["Base Color"])
        avg = (0.5, 0.5, 0.5)
        img = getattr(tex, "image", None)
        if img:
            import numpy as np
            a = np.empty(len(img.pixels), dtype=np.float32)
            img.pixels.foreach_get(a)
            a = a.reshape(-1, 4)[::97, :3]
            avg = tuple(float(x) for x in a.mean(axis=0))
        mats.append((mat, mix, p, max(1e-3, sum(avg) / 3)))
    lw, lh = lx1 - lx0, lz1 - lz0
    return root, (lw, lh, (lz0 + lz1) / 2, ly), mats


def tint_gba(mats, rgb, clear):
    """rgb None = the model's own grey."""
    for mat, mix, p, avg in mats:
        # The model's textures are quite dark; lift them a bit so the cart reads
        # well on the small (and less bright) GBA screen.
        mix.inputs["Factor"].default_value = 1.0
        if rgb is None:
            mix.inputs[7].default_value = (1.45, 1.45, 1.45, 1.0)
        else:
            boost = 1.7 if clear else 1.3      # keep coloured plastic readable
            mix.inputs[7].default_value = (*(min(6.0, boost * c / avg) for c in rgb), 1.0)
        # Only a hint of transmission: fully clear plastic shows the dark studio.
        p.inputs["Transmission Weight"].default_value = 0.25 if clear else 0.0


# ---------------------------------------------------------------------------
# Other external cart models (all CC-BY-4.0, see CREDITS.md):
#   GB/GBC: "Gameboy cartridge" by Val Turcea, "Gameboy Cartridge" by Karolina D
#           (same base mesh; the label sits baked into the texture atlas)
#   NES:    "NES Cartridge" by Anette Rana (separate label plane)

MODEL_CFG = {
    # label = faces whose UV centre lies in this atlas box (u0, v0, u1, v1)
    "gb":  dict(label_uv=(0.57, 0.60, 0.93, 0.92), up_axis="-X", height=65.0),
    # label = the object using this material
    "nes": dict(label_mat="blinn1", up="label_long", height=133.0),
}


def add_tint(mat):
    """Inserts base colour x tint into a model material; returns a handle."""
    nt = mat.node_tree
    p = next(x for x in nt.nodes if x.type == 'BSDF_PRINCIPLED')
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.clamp_result = False
    mix.inputs["Factor"].default_value = 0.0
    avg = 0.5
    if p.inputs["Base Color"].links:
        link = p.inputs["Base Color"].links[0]
        nt.links.new(link.from_socket, mix.inputs[6])
        img = getattr(link.from_node, "image", None)
        if img:
            import numpy as np
            a = np.empty(len(img.pixels), dtype=np.float32)
            img.pixels.foreach_get(a)
            avg = float(a.reshape(-1, 4)[::97, :3].mean())
    else:
        c = p.inputs["Base Color"].default_value
        mix.inputs[6].default_value = c
        avg = (c[0] + c[1] + c[2]) / 3
    nt.links.new(mix.outputs[2], p.inputs["Base Color"])
    return (mat, mix, p, max(1e-3, avg), p.inputs["Metallic"].default_value,
            p.inputs["Roughness"].default_value)


def tint_model(handles, rgb, clear, metal=False, neutral=1.0):
    for mat, mix, p, avg, met0, rough0 in handles:
        mix.inputs["Factor"].default_value = 1.0
        if rgb is None:
            mix.inputs[7].default_value = (neutral, neutral, neutral, 1.0)
        else:
            boost = 1.7 if clear else 1.15
            mix.inputs[7].default_value = (*(min(8.0, boost * c / avg) for c in rgb), 1.0)
        p.inputs["Transmission Weight"].default_value = 0.25 if clear else 0.0
        p.inputs["Metallic"].default_value = 0.65 if metal else met0
        p.inputs["Roughness"].default_value = 0.32 if metal else rough0


def build_model_cart(path, kind, lab_mat):
    cfgm = MODEL_CFG[kind]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    meshes = [o for o in new if o.type == 'MESH']
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
    for o in new:
        if o.type != 'MESH':
            bpy.data.objects.remove(o)

    # Label faces as (object, [polygon indices]).
    lab = []
    if "label_mat" in cfgm:
        for o in meshes:
            if o.material_slots and o.material_slots[0].material.name.startswith(cfgm["label_mat"]):
                lab.append((o, [p.index for p in o.data.polygons]))
    else:
        u0, v0, u1, v1 = cfgm["label_uv"]
        for o in meshes:
            uv = o.data.uv_layers.active
            sel = []
            for p in o.data.polygons:
                us = [uv.data[l].uv for l in p.loop_indices]
                cu = sum(u.x for u in us) / len(us)
                cv = sum(u.y for u in us) / len(us)
                if u0 <= cu <= u1 and v0 <= cv <= v1:
                    sel.append(p.index)
            if sel:
                lab.append((o, sel))
    lpts = [o.data.vertices[i].co.copy() for o, ps in lab for pi in ps for i in o.data.polygons[pi].vertices]
    allp = [v.co.copy() for o in meshes for v in o.data.vertices]
    n = Vector()
    for o, ps in lab:
        for pi in ps:
            n += o.data.polygons[pi].normal * o.data.polygons[pi].area
    n.normalize()
    lc = sum(lpts, Vector()) / len(lpts)
    mc = sum(allp, Vector()) / len(allp)
    if (lc - mc).dot(n) < 0:
        n = -n

    def principal(pts):
        import numpy as np
        a = np.array([[q.x, q.y, q.z] for q in pts])
        a = a - a.mean(axis=0)
        nn = np.array([n.x, n.y, n.z])
        a = a - np.outer(a @ nn, nn)          # in the label plane only
        w, v = np.linalg.eigh(a.T @ a)
        d = v[:, -1]
        return Vector((float(d[0]), float(d[1]), float(d[2]))).normalized()

    if "up_axis" in cfgm:
        # Fixed model axis (+/-X/Y/Z) for meshes where the label is not a guide.
        ax = cfgm["up_axis"]
        up = Vector({"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[ax[-1]])
        if ax.startswith("-"):
            up = -up
    else:
        up = principal(lpts if cfgm["up"] == "label_long" else allp)
        if (lc - mc).dot(up) < 0:             # labels sit in the upper part
            up = -up
    print("MODELAXES", kind, "normal", tuple(round(c, 3) for c in n), "up", tuple(round(c, 3) for c in up), flush=True)
    right = up.cross(n).normalized()
    up = n.cross(right).normalized()
    R = Matrix((right, -n, up)).to_4x4()      # rows: new x, y, z
    rp = [R @ q for q in allp]
    k = cfgm["height"] * MM / (max(q.z for q in rp) - min(q.z for q in rp))
    T = (Matrix.Scale(k, 4) @
         Matrix.Translation((-(min(q.x for q in rp) + max(q.x for q in rp)) / 2,
                             -(min(q.y for q in rp) + max(q.y for q in rp)) / 2,
                             -min(q.z for q in rp))) @ R)
    for o in meshes:
        o.data.transform(T)

    # Label faces: our label material + 0..1 UVs over the label rectangle.
    lw = lh = lz = ly = None
    for o, ps in lab:
        me = o.data
        if not any(sl.material is lab_mat for sl in o.material_slots):
            me.materials.append(lab_mat)
        idx = [i for i, sl in enumerate(o.material_slots) if sl.material is lab_mat][0]
        if "label_mat" in cfgm:
            for v in me.vertices:
                v.co.y -= 0.05 * MM            # a hair in front of the plastic
        vs = [me.vertices[i].co for pi in ps for i in me.polygons[pi].vertices]
        x0, x1 = min(v.x for v in vs), max(v.x for v in vs)
        z0, z1 = min(v.z for v in vs), max(v.z for v in vs)
        uv = me.uv_layers.active
        for pi in ps:
            poly = me.polygons[pi]
            poly.material_index = idx
            for l in poly.loop_indices:
                co = me.vertices[me.loops[l].vertex_index].co
                uv.data[l].uv = ((co.x - x0) / (x1 - x0), (co.z - z0) / (z1 - z0))
        lw, lh, lz, ly = x1 - x0, z1 - z0, (z0 + z1) / 2, min(v.y for v in vs)

    root = bpy.data.objects.new("root_" + kind, None)
    bpy.context.scene.collection.objects.link(root)
    handles, seen = [], set()
    for o in meshes:
        o.parent = root
        for sl in o.material_slots:
            m = sl.material
            if m and m is not lab_mat and m.name not in seen and m.use_nodes:
                seen.add(m.name)
                handles.append(add_tint(m))
    return root, (lw, lh, lz, ly), handles


# ---------------------------------------------------------------------------
# Label mask: a quick flat render (Workbench) where only the label is white.
# The packer uses it to keep the label free of dithering.

def render_mask(sc, lab_mat, path):
    eng = sc.render.engine
    shade = sc.display.shading
    sc.render.engine = 'BLENDER_WORKBENCH'
    shade.light = 'FLAT'
    shade.color_type = 'MATERIAL'
    for m in bpy.data.materials:
        m.diffuse_color = (0, 0, 0, 1)
    lab_mat.diffuse_color = (1, 1, 1, 1)
    view = sc.view_settings.view_transform
    sc.view_settings.view_transform = 'Standard'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    sc.view_settings.view_transform = view
    sc.render.engine = eng


# ---------------------------------------------------------------------------
# Stage: lights, world, camera

def setup_stage(samples):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.device = 'CPU'
    sc.render.film_transparent = True
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Base Contrast'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'

    world = bpy.data.worlds.new("world")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.42, 0.43, 0.46, 1)
    bg.inputs["Strength"].default_value = 0.25

    def area(name, loc, size, power, color=(1, 1, 1)):
        l = bpy.data.lights.new(name, 'AREA')
        l.size = size
        l.energy = power
        l.color = color
        o = bpy.data.objects.new(name, l)
        sc.collection.objects.link(o)
        o.location = loc
        d = Vector((0, 0, 0.03)) - Vector(loc)
        o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        return o

    area("key", (-0.16, -0.22, 0.22), 0.22, 2.2, (1.0, 0.97, 0.93))
    area("fill", (0.24, -0.16, 0.06), 0.30, 0.7, (0.92, 0.95, 1.0))
    area("rim", (0.05, 0.25, 0.20), 0.15, 1.4)
    area("top", (0.0, -0.05, 0.30), 0.30, 0.5)

    cam = bpy.data.cameras.new("cam")
    cam.lens = 85
    cam.sensor_width = 36
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


def place_camera(co, scale_px_mm, res_x, target_z, pitch_deg=7.0):
    cam = co.data
    fov = 2 * math.atan(cam.sensor_width / (2 * cam.lens))
    width_m = (res_x / scale_px_mm) * MM
    dist = width_m / (2 * math.tan(fov / 2))
    p = math.radians(pitch_deg)
    co.location = (0, -dist * math.cos(p), target_z + dist * math.sin(p))
    d = Vector((0, 0, target_z)) - co.location
    co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


# ---------------------------------------------------------------------------

def downscale(path_in, path_out, ss):
    """Box-filter downscale of an RGBA render by `ss` (premultiplied alpha)."""
    img = bpy.data.images.load(path_in, check_existing=False)
    W, H = img.size
    w, h = W // ss, H // ss
    px = list(img.pixels)
    out = [0.0] * (w * h * 4)
    n = ss * ss
    for y in range(h):
        for x in range(w):
            r = g = b = a = 0.0
            for yy in range(ss):
                base = ((y * ss + yy) * W + x * ss) * 4
                for xx in range(ss):
                    i = base + xx * 4
                    pa = px[i + 3]
                    r += px[i] * pa; g += px[i + 1] * pa; b += px[i + 2] * pa; a += pa
            o = (y * w + x) * 4
            if a > 0:
                out[o] = r / a; out[o + 1] = g / a; out[o + 2] = b / a
            out[o + 3] = a / n
    small = bpy.data.images.new("small", w, h, alpha=True)
    small.pixels = out
    small.filepath_raw = path_out
    small.file_format = 'PNG'
    small.save()
    bpy.data.images.remove(small)
    bpy.data.images.remove(img)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    with open(argv[0], encoding="utf-8") as f:
        cfg = json.load(f)
    ss = int(cfg.get("supersample", 3))
    poses = cfg["poses"]

    clear_scene()
    cam = setup_stage(int(cfg.get("samples", 64)))
    body_mat = plastic_material("plastic")
    lab_mat = label_material()
    carts = {}
    gba_mats = None
    model = cfg.get("gba_model")
    if model and os.path.exists(model):
        r, dims, gba_mats = build_gba_model(model, lab_mat)
        carts["gba"] = (r, dims)
    else:
        carts["gba"] = build_cart("gba", body_mat, lab_mat)
    handles = {}
    for kind, key in (("gb", "gb_model"), ("nes", "nes_model")):
        path = cfg.get(key)
        if path and os.path.exists(path):
            r, dims, h = build_model_cart(path, kind, lab_mat)
            carts[kind] = (r, dims)
            handles[kind] = h
        else:
            carts[kind] = build_cart(kind, body_mat, lab_mat)
    carts["gbc"] = carts["gb"]
    if "gb" in handles:
        handles["gbc"] = handles["gb"]
    carts["folder"] = build_folder(body_mat, lab_mat)

    sc = bpy.context.scene
    tmp = os.path.join(os.path.dirname(os.path.abspath(argv[0])), "_render_tmp_%d.png" % os.getpid())
    for job in cfg["jobs"]:
        system = job["system"]
        root, (lw, lh, lz, ly) = carts[system]
        for k, (r, _) in carts.items():
            hide = r is not root
            for ob in [r] + list(r.children):
                ob.hide_render = hide
        if system == "gba" and gba_mats:
            tint_gba(gba_mats, job.get("body"), job.get("clear", False))
        elif system in handles:
            tint_model(handles[system], job.get("body"), job.get("clear", False),
                       job.get("metal", False), cfg.get("neutral_" + system, 1.0))
        else:
            set_plastic(body_mat, job.get("body") or [0.25, 0.25, 0.27], job.get("clear", False))
        set_label(lab_mat, job.get("label"), lw / lh)
        spec = SPECS[system]
        H = spec["h"] * MM
        os.makedirs(job["out"], exist_ok=True)
        meta = {"system": system, "supersample": ss, "poses": {}}
        for pose in poses:
            if "systems" in pose and system not in pose["systems"]:
                continue
            if pose.get("zoom") and job.get("no_zoom"):
                continue
            scale = SCALE[system] * pose["scale"]
            fw, fh = pose["canvas"]
            sc.render.resolution_x = fw * ss
            sc.render.resolution_y = fh * ss
            sc.render.resolution_percentage = 100
            place_camera(cam, scale * ss, fw * ss, H * 0.5)
            # Shift the frame so the cart's bottom-centre lands at the anchor.
            root.rotation_euler = (0, 0, math.radians(pose["yaw"]))
            bpy.context.view_layer.update()
            cam.data.shift_x = 0.0
            cam.data.shift_y = 0.0
            p = world_to_camera_view(sc, cam, Vector((0, 0, 0)))
            ax, ay = pose["anchor"]
            cam.data.shift_x = (p.x - ax / fw)
            cam.data.shift_y = (p.y - (1 - ay / fh)) * fh / fw
            bpy.context.view_layer.update()
            sc.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            out = os.path.join(job["out"], pose["name"] + ".png")
            os.replace(tmp, out)      # Full (supersampled) size; the packer scales down.
            if job.get("label"):
                render_mask(sc, lab_mat, os.path.join(job["out"], pose["name"] + "_mask.png"))
                sc.render.filepath = tmp
            # Zoom poses stand on the shelf with the canvas bottom (the rest of
            # the cart is hidden behind the shelf).
            pm = {"anchor": [ax, fh] if pose.get("zoom") else [ax, ay]}
            if pose["yaw"] == 0:
                # Label rectangle in image pixels (for drawing titles on blank carts).
                corners = [Vector((sx * lw / 2, ly, lz + sz * lh / 2)) for sx in (-1, 1) for sz in (-1, 1)]
                pts = [world_to_camera_view(sc, cam, root.matrix_world @ c) for c in corners]
                xs = [q.x * fw for q in pts]
                ys = [(1 - q.y) * fh for q in pts]
                pm["label"] = [round(min(xs)), round(min(ys)), round(max(xs) - min(xs)), round(max(ys) - min(ys))]
            meta["poses"][pose["name"]] = pm
        with open(os.path.join(job["out"], "poses.json"), "w") as f:
            json.dump(meta, f)
        print("RENDERED", job["out"], flush=True)
    if os.path.exists(tmp):
        os.remove(tmp)


main()
