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

# Pixels per mm on screen for the front pose (fits ~128x84 px).
SCALE = {"gba": 2.20, "gb": 1.26, "gbc": 1.26, "folder": 1.62}


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
    carts["gb"] = build_cart("gb", body_mat, lab_mat)
    carts["gbc"] = carts["gb"]
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
        else:
            set_plastic(body_mat, job.get("body") or [0.25, 0.25, 0.27], job.get("clear", False))
        set_label(lab_mat, job.get("label"), lw / lh)
        spec = SPECS[system]
        H = spec["h"] * MM
        os.makedirs(job["out"], exist_ok=True)
        meta = {"system": system, "supersample": ss, "poses": {}}
        for pose in poses:
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
            pm = {"anchor": [ax, ay]}
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
