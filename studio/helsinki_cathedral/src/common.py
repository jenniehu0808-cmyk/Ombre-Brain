"""common.py - shared helpers for the Helsinki Cathedral build (bpy 5.2, headless, Cycles CPU).

Every module starts with:   from common import *
Coordinate contract: metres, Z up, +X = east, +Y = north. The south facade (grand stairs,
the one in the reference photo) faces -Y; the camera sits at -Y looking +Y.
Origin = dome axis, z = 0 at the top of the podium/platform the cathedral stands on.
"""
import bpy, bmesh, math, os, sys, json, time
from mathutils import Vector, Matrix, Euler

WORK = os.path.dirname(os.path.abspath(__file__))
PREVIEWS = os.path.join(WORK, 'previews')
os.makedirs(PREVIEWS, exist_ok=True)

def load_spec():
    with open(os.path.join(WORK, 'spec.json')) as f:
        return json.load(f)

def rad(d): return math.radians(d)

# ----------------------------------------------------------------------------- scene
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.render.engine = 'CYCLES'                 # NEVER EEVEE/WORKBENCH: no GPU here, process aborts
    sc.cycles.device = 'CPU'
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    try:
        sc.view_settings.view_transform = 'AgX'
        sc.view_settings.look = 'AgX - Base Contrast'
    except Exception:
        pass
    sc.render.film_transparent = False
    return sc

def get_collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col

# ----------------------------------------------------------------------------- materials
# Builders may add/override entries in MATERIAL_SPECS before calling mat(); keys are Principled inputs.
MATERIAL_SPECS = {
    'default':      {'Base Color': (0.6, 0.6, 0.6, 1), 'Roughness': 0.7},
    'white_paint':  {'Base Color': (0.93, 0.91, 0.87, 1), 'Roughness': 0.55},   # columns, trim, cornices, pilasters
    'wall':         {'Base Color': (0.86, 0.83, 0.77, 1), 'Roughness': 0.65},   # plain wall fields (slightly off-white)
    'copper_green': {'Base Color': (0.16, 0.30, 0.22, 1), 'Roughness': 0.5, 'Metallic': 0.15},  # patinated domes/roofs
    'roof_dark':    {'Base Color': (0.12, 0.18, 0.15, 1), 'Roughness': 0.6},    # lower roofs (dark green/grey)
    'gold':         {'Base Color': (1.0, 0.76, 0.30, 1), 'Roughness': 0.28, 'Metallic': 1.0},
    'granite':      {'Base Color': (0.36, 0.34, 0.33, 1), 'Roughness': 0.85},   # stairs
    'zinc':         {'Base Color': (0.78, 0.77, 0.73, 1), 'Roughness': 0.6},    # apostle statues
    'glass':        {'Base Color': (0.05, 0.06, 0.08, 1), 'Roughness': 0.12, 'Specular IOR Level': 0.6},
    'wood_door':    {'Base Color': (0.33, 0.17, 0.08, 1), 'Roughness': 0.5},
    'ground':       {'Base Color': (0.42, 0.40, 0.38, 1), 'Roughness': 0.9},    # cobbled square
}

def mat(name):
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (-300, 0)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    for k, v in MATERIAL_SPECS.get(name, MATERIAL_SPECS['default']).items():
        bsdf.inputs[k].default_value = v
    return m

def set_material(ob, name):
    m = mat(name) if isinstance(name, str) else name
    ob.data.materials.clear()
    ob.data.materials.append(m)
    return ob

# ----------------------------------------------------------------------------- mesh building
def _smooth_bm(bm, angle_deg):
    r = math.radians(angle_deg)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > r:
            e.smooth = False

def _finish(name, bm, material=None, collection=None, smooth_angle=None):
    if smooth_angle is not None:
        _smooth_bm(bm, smooth_angle)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (collection if collection is not None else get_collection('Cathedral')).objects.link(ob)
    if material is not None:
        me.materials.append(mat(material) if isinstance(material, str) else material)
    return ob

def add_box(name, size, center=(0, 0, 0), material=None, collection=None, rotation=(0, 0, 0)):
    """Axis-aligned box, size=(sx,sy,sz) centred at `center` (rotation in radians applied about its centre)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if any(rotation):
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler(rotation).to_matrix(), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _finish(name, bm, material, collection)

def add_box_on(name, size, base_center=(0, 0, 0), **kw):
    """Box whose bottom face centre is at base_center."""
    c = (base_center[0], base_center[1], base_center[2] + size[2] / 2)
    return add_box(name, size, c, **kw)

def add_cylinder(name, radius, height, base_center=(0, 0, 0), segments=48, material=None, collection=None,
                 radius_top=None, smooth=True, cap=True):
    """Vertical cylinder/cone frustum standing on base_center."""
    bm = bmesh.new()
    r2 = radius if radius_top is None else radius_top
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=segments,
                          radius1=radius, radius2=r2, depth=height)
    bmesh.ops.translate(bm, vec=Vector(base_center) + Vector((0, 0, height / 2)), verts=bm.verts)
    return _finish(name, bm, material, collection, smooth_angle=40 if smooth else None)

def add_sphere(name, radius, center=(0, 0, 0), segments=48, rings=24, material=None, collection=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _finish(name, bm, material, collection, smooth_angle=60)

def lathe(name, profile, segments=64, center=(0, 0, 0), material=None, collection=None, smooth_angle=35):
    """Surface of revolution about the local Z axis.
    profile: list of (r, z) in order along the outline. r=0 points lie on the axis (closed tip).
    An outline that starts AND ends at r=0 gives a closed solid (orb, dome with floor, baluster).
    An outline whose ends have r>0 is open there (e.g. a dome shell sitting on a drum)."""
    bm = bmesh.new()
    vs = [bm.verts.new((max(float(r), 0.0), 0.0, float(z))) for r, z in profile]
    es = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), dvec=(0, 0, 0),
                   angle=math.tau, steps=segments, use_merge=True, use_normal_flip=False, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _finish(name, bm, material, collection, smooth_angle)

def dome_profile(radius, rise=None, z0=0.0, steps=24, thickness=0.0):
    """(r,z) outline of a dome: hemisphere scaled vertically to `rise` (default = radius), base at z0.
    Returns an open outline from the rim (r=radius, z=z0) up to the apex (r=0, z=z0+rise)."""
    rise = radius if rise is None else rise
    pts = []
    for i in range(steps + 1):
        a = (i / steps) * (math.pi / 2)
        pts.append((radius * math.cos(a), z0 + rise * math.sin(a)))
    return pts

def mitered_frame(name, profile, half_w, half_d, center=(0, 0, 0), material=None, collection=None, smooth_angle=None):
    """Closed moulding/cornice ring wrapped around a rectangle of half sizes (half_w along X, half_d along Y),
    with properly mitred corners. profile = closed polygon of (offset, z): offset is measured OUTWARD from the
    rectangle edge (negative = inside), z relative to center[2]. Great for cornices, plinth bands, balustrade rails."""
    bm = bmesh.new()
    corners = [Vector((half_w, half_d, 0)), Vector((-half_w, half_d, 0)), Vector((-half_w, -half_d, 0)), Vector((half_w, -half_d, 0))]
    bis = [Vector((1, 1, 0)), Vector((-1, 1, 0)), Vector((-1, -1, 0)), Vector((1, -1, 0))]
    loops = []
    for c, b in zip(corners, bis):
        loops.append([bm.verts.new(c + Vector((b.x * off, b.y * off, z))) for off, z in profile])
    n = len(profile)
    for i in range(4):
        a, b2 = loops[i], loops[(i + 1) % 4]
        for j in range(n):
            k = (j + 1) % n
            try:
                bm.faces.new((a[j], a[k], b2[k], b2[j]))
            except ValueError:
                pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _finish(name, bm, material, collection, smooth_angle)

def prism(name, profile, length, material=None, collection=None, smooth_angle=None):
    """Straight extrusion of a closed (y,z) polygon along +X from x=0 to x=length. Object origin at (0,0,0):
    position/rotate it afterwards with ob.location / ob.rotation_euler. Use for straight cornices, raking
    cornices of pediments, mouldings, steps."""
    bm = bmesh.new()
    v0 = [bm.verts.new((0.0, y, z)) for y, z in profile]
    v1 = [bm.verts.new((length, y, z)) for y, z in profile]
    bm.faces.new(v0)
    bm.faces.new(list(reversed(v1)))
    n = len(profile)
    for j in range(n):
        k = (j + 1) % n
        bm.faces.new((v0[j], v1[j], v1[k], v0[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _finish(name, bm, material, collection, smooth_angle)

def extrude_polygon(name, points_xy, height, base_z=0.0, material=None, collection=None, smooth_angle=None):
    """Closed footprint polygon (x,y) extruded up by `height` from base_z. Any simple polygon (pediment
    triangle, chamfered block, L-shape...)."""
    bm = bmesh.new()
    v0 = [bm.verts.new((x, y, base_z)) for x, y in points_xy]
    v1 = [bm.verts.new((x, y, base_z + height)) for x, y in points_xy]
    bm.faces.new(list(reversed(v0)))
    bm.faces.new(v1)
    n = len(points_xy)
    for j in range(n):
        k = (j + 1) % n
        bm.faces.new((v0[j], v0[k], v1[k], v1[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _finish(name, bm, material, collection, smooth_angle)

def join(objects, name=None):
    """Join several mesh objects into one (keeps materials). Returns the joined object."""
    objects = [o for o in objects if o is not None]
    if not objects:
        return None
    bm = bmesh.new()
    mats = []
    for ob in objects:
        me = ob.data
        mat_map = []
        for m in me.materials:
            if m not in mats:
                mats.append(m)
            mat_map.append(mats.index(m))
        tmp = bmesh.new()
        tmp.from_mesh(me)
        for f in tmp.faces:
            f.material_index = mat_map[f.material_index] if mat_map else 0
        bmesh.ops.transform(tmp, matrix=ob.matrix_world, verts=tmp.verts)
        tmp_me = bpy.data.meshes.new('_tmp')
        tmp.to_mesh(tmp_me)
        tmp.free()
        bm.from_mesh(tmp_me)
        bpy.data.meshes.remove(tmp_me)
    me = bpy.data.meshes.new(name or objects[0].name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    col = objects[0].users_collection[0]
    new = bpy.data.objects.new(name or objects[0].name, me)
    col.objects.link(new)
    for ob in objects:
        bpy.data.objects.remove(ob, do_unlink=True)
    return new

def duplicate(ob, name, location=None, rotation=None, scale=None, collection=None):
    """Linked duplicate (shares mesh data) - use for repeated columns, balusters, stars, statues."""
    new = bpy.data.objects.new(name, ob.data)
    (collection or ob.users_collection[0]).objects.link(new)
    new.location = ob.location if location is None else Vector(location)
    new.rotation_euler = ob.rotation_euler if rotation is None else Euler(rotation)
    new.scale = ob.scale if scale is None else Vector(scale)
    return new

def place(ob, location=None, rotation=None, scale=None):
    if location is not None: ob.location = Vector(location)
    if rotation is not None: ob.rotation_euler = Euler(rotation)
    if scale is not None: ob.scale = Vector(scale)
    return ob

def add_bevel(ob, width=0.04, segments=2, angle_deg=30):
    m = ob.modifiers.new('Bevel', 'BEVEL')
    m.width = width; m.segments = segments
    m.limit_method = 'ANGLE'; m.angle_limit = math.radians(angle_deg)
    return m

def add_boolean(ob, cutter, operation='DIFFERENCE', solver='EXACT'):
    """Boolean modifier (render evaluates it). Cutter is hidden from render."""
    m = ob.modifiers.new('Bool', 'BOOLEAN')
    m.object = cutter; m.operation = operation; m.solver = solver
    cutter.hide_render = True
    cutter.display_type = 'WIRE'
    return m

def apply_modifiers(ob):
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        for m in list(ob.modifiers):
            bpy.ops.object.modifier_apply(modifier=m.name)
    return ob

# ----------------------------------------------------------------------------- camera / light / render
def setup_camera(location, target, lens=28.0, sensor_width=36.0, shift_x=0.0, shift_y=0.0, name='Camera', clip_end=2000.0):
    """Camera at `location` looking at `target`. lens in mm (36mm sensor). shift_y>0 raises the frame
    without tilting (keeps verticals vertical, like a shift lens)."""
    sc = bpy.context.scene
    cam_data = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam_data.lens = lens; cam_data.sensor_width = sensor_width; cam_data.sensor_fit = 'AUTO'
    cam_data.shift_x = shift_x; cam_data.shift_y = shift_y; cam_data.clip_end = clip_end
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, cam_data)
        sc.collection.objects.link(cam)
    cam.location = Vector(location)
    d = Vector(target) - Vector(location)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    sc.camera = cam
    return cam

def sun_direction(azimuth_deg, elevation_deg):
    """Unit vector pointing TOWARD the sun. Azimuth clockwise from north (+Y): 90=east(+X), 180=south(-Y), 270=west(-X)."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    return Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))

def setup_sun_sky(azimuth_deg=228.0, elevation_deg=8.0, sun_strength=0.0, sun_angle_deg=0.9,
                  sky_strength=1.0, air=1.0, dust=2.0, ozone=1.2, altitude=0.0, sun_color=None, sun_disc=True,
                  exposure=-4.0):
    """Physically based sky world (Blender 5 'multiple scattering' model, the successor of Nishita).
    DEFAULT RECIPE (verified): sun_disc=True -> the sky itself carries the sun; it is physically bright, so the
    scene exposure is set to `exposure` (about -4 for golden hour). sun_strength=0 -> no extra lamp.
    If you want an extra Sun lamp (sharper shadows), pass sun_strength>0 (W/m2; at this exposure ~80-150 matches
    the sky's own sun) and sun_disc=False. Azimuth clockwise from north(+Y): 180=south, 228=SW, 270=west.
    Returns (world, sun_object_or_None)."""
    sc = bpy.context.scene
    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new('ShaderNodeTexSky')
    try:
        sky.sky_type = 'MULTIPLE_SCATTERING'   # Blender 5.x physically based sky
    except TypeError:
        sky.sky_type = 'NISHITA'               # Blender 4.x name of the same model family
    sky.sun_disc = sun_disc
    sky.sun_elevation = math.radians(elevation_deg)
    sky.sun_rotation = math.radians(azimuth_deg % 360.0)   # VERIFIED on bpy 5.2: rotation == azimuth clockwise from +Y
    sky.sun_size = math.radians(sun_angle_deg)
    sky.sun_intensity = 1.0
    sky.altitude = altitude; sky.air_density = air; sky.ozone_density = ozone
    if hasattr(sky, 'aerosol_density'):
        sky.aerosol_density = dust
    else:                                      # Blender 4.x
        sky.dust_density = dust
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = sky_strength
    out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(sky.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    sc.view_settings.exposure = exposure
    try:
        w.cycles.sampling_method = 'AUTOMATIC'
    except Exception:
        pass
    if sun_strength <= 0:
        old = bpy.data.objects.get('Sun')
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        return w, None
    ld = bpy.data.lights.get('Sun') or bpy.data.lights.new('Sun', 'SUN')
    ld.energy = sun_strength
    ld.angle = math.radians(sun_angle_deg)
    if sun_color is None:
        t = max(0.0, min(1.0, elevation_deg / 25.0))        # lower sun -> warmer
        sun_color = (1.0, 0.62 + 0.33 * t, 0.35 + 0.55 * t)
    ld.color = sun_color
    sun = bpy.data.objects.get('Sun')
    if sun is None:
        sun = bpy.data.objects.new('Sun', ld)
        sc.collection.objects.link(sun)
    d = sun_direction(azimuth_deg, elevation_deg)
    sun.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    return w, sun

def render(path, res=(480, 640), samples=32, denoise=True, time_limit=0.0, exposure=None):
    """Render the current camera to an absolute path. Keep previews small (<= 640x853, <= 48 samples)."""
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = int(res[0]), int(res[1])
    sc.render.resolution_percentage = 100
    sc.cycles.samples = int(samples)
    sc.cycles.use_denoising = denoise
    sc.cycles.time_limit = time_limit
    if exposure is not None:
        sc.view_settings.exposure = exposure
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print(f'[render] {path}  {time.time() - t:.1f}s')
    return path

def save_blend(path):
    path = os.path.abspath(path)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print('[blend]', path)
    return path

def count_scene():
    n_obj = len([o for o in bpy.data.objects if o.type == 'MESH'])
    n_tri = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
    return n_obj, n_tri

# ----------------------------------------------------------------------------- comparison helpers
def contact_sheet(paths, out_path, labels=None, height=600):
    """Put several images side by side (scaled to the same height) with labels. Returns out_path."""
    from PIL import Image, ImageDraw
    ims = []
    for p in paths:
        im = Image.open(p).convert('RGB')
        s = height / im.size[1]
        ims.append(im.resize((max(1, int(im.size[0] * s)), height), Image.LANCZOS))
    W = sum(i.size[0] for i in ims) + 10 * (len(ims) - 1)
    out = Image.new('RGB', (W, height + 22), 'black')
    dr = ImageDraw.Draw(out)
    x = 0
    for i, im in enumerate(ims):
        out.paste(im, (x, 22))
        if labels:
            dr.text((x + 6, 5), str(labels[i]), fill='white')
        x += im.size[0] + 10
    out.save(out_path)
    return out_path

def compare_with_photo(render_path, out_path=None, height=700):
    """Render next to the reference photo at equal height: previews/<name>_vs_photo.png"""
    if out_path is None:
        out_path = os.path.splitext(render_path)[0] + '_vs_photo.png'
    photo = os.path.join(WORK, 'ref', 'photo_small.jpg')
    if not os.path.exists(photo):
        print('[compare] reference photo not found (%s) - skipping the comparison sheet' % photo)
        return None
    try:
        import PIL  # noqa: F401  (not bundled with Blender's own Python)
    except ImportError:
        print('[compare] Pillow not available - skipping the comparison sheet')
        return None
    return contact_sheet([os.path.join(WORK, 'ref', 'photo_small.jpg'), render_path], out_path, ['REFERENCE PHOTO', 'RENDER'], height)
