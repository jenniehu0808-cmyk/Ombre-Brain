"""mod_look.py - materials, sky/sun, camera and render settings for the Helsinki Cathedral build.

apply_spec_materials(spec): copies spec['materials'] into common.MATERIAL_SPECS. main.py should call this FIRST,
                    before the other modules build, so materials they derive from the palette (statues_site's
                    'granite_step', ...) are born with the spec colours. build() calls it again (idempotent).
build(spec, col)  : upgrades the shared materials IN PLACE (procedural tonal variation, bump, roughness variation;
                    node trees are rebuilt from the spec palette, so the call order of the other modules does not
                    matter) and re-tints derived materials ('<name>_<suffix>' / '<name>.001') without touching their
                    node trees. Returns [look_shadow_buildings_W, look_shadow_buildings_NW, look_bounce_palace_E]:
                    two off-camera boxes standing for the buildings west / north-west of Senate Square whose shadow
                    lies over the square, the stairs and the lower S portico / west wing, and a diffuse-only ochre
                    bounce card for the palace east of the square (LOOK['square_shadow'] = False -> []).
setup_look(spec)  : world/sun (setup_sun_sky(**spec['sun'], sun_disc=False + warm Sun lamp, LOOK['sun_lamp']) + view transform (Standard / look 'None';
                    AgX and Khronos were tested against the photo and rejected, see LOOK), camera (setup_camera from
                    spec['camera'], portrait 3:4), Cycles final settings. Call it AFTER all builds.
final_render(path, res=None, samples=None): final-quality render wrapper (adaptive sampling, OIDN, clamp).

Only `from common import *` is imported locally (single-file bundle contract).
"""
from common import *

# ----------------------------------------------------------------------------- look constants (tuned against ref/photo.jpg)
LOOK = {
    # Tested against the photo (see report): AgX desaturates the warm highlights (lit white reads pinkish-pale,
    # B/R 0.8 vs 0.6 in the photo); 'Standard' keeps the pale-gold whites and the clean blue sky. Khronos PBR
    # Neutral is the runner-up (deeper sky, more orange whites). Fixer r1: 'Medium High Contrast' crushed the shade
    # faces ~0.4 EV below the photo while the lit faces already clipped -> look 'None' (identity curve) with
    # sun_intensity 0.5 and exposure -2.45 (spec.sun): shade faces +8 units, sky at the photo level, clipping halved.
    'view_transform': 'Standard',
    'look': 'None',
    'white_balance': False,         # scene.view_settings white balance (photo shadows are neutral grey -> off)
    'wb_temperature': 6500.0,       # 6500 = neutral (D65); lower = cooler image
    'wb_tint': 10.0,                # 10 = neutral
    'sky_ground_albedo': 0.25,      # (no measurable effect on the 5.x multiple-scattering sky; kept for older builds)
    'sun_intensity': 0.33,          # sun disc relative to the sky: lifts the sky vs the sun the way the phone's HDR
                                    # processing did in the photo (sky top (77,113,165) there). Fixer r2: 0.5 -> 0.33 with
                                    # sun el 6.5 / ozone 2.0 / exposure -2.5 (spec.sun): lit whites were ~0.4 EV too bright
                                    # and too peach (tower W face (216,172,129) -> ~(185,159,132) vs photo (165,144,112)).
    'final_samples': 512,
    'adaptive_threshold': 0.01,
    'preview_samples': 32,
    # Senate Square is shadowed by the buildings west of it in the photo (SPEC 6): an off-camera shadow caster.
    'square_shadow': True,
    # Fixer r3 (sun az 279 = 9 deg north of west, rays drift 0.158 m north per metre west): the W box now reaches
    # y -23.5 so the S-portico rays (crossing x=-75 at y -27..-24) hit it; its top 16.5 puts the shadow line at
    # 16.5 - 65*tan(6.5) = 9.1 m on column 1 and ~7.2 m on column 5 (photo: 8.5-9.5 / 6.5-8 m), stairs + square shaded.
    'shadow_building': {'x_range': [-135.0, -75.0], 'y_range': [-220.0, -23.5], 'top_z': 16.5},
    # Fixer r1: the buildings north-west of the square also shade the W portico below z~10 and the west faces of
    # the SW corner block / S arm flank (whose bounce turned the whole left wing orange). At el 5 deg the shadow top
    # at the W portico (x=-29.5) is 15 - 45.5*tan(el) = 11.0 m at el 5 (9.8 m at el 6.5, fixer r2); the south edge y=-33 keeps the S portico lit.
    'shadow_building_NW': {'x_range': [-140.0, -75.0], 'y_range': [-33.0, 45.0], 'top_z': 15.0},
    'shadow_sink': 0.5,             # blocker bottoms this far BELOW square_ground_z (no coplanar z-fight with the ground)
    # Fixer r2 added a shadow-only slab between S-portico columns 2 and 3 (x -4.4..-4.2, z<6) because at az 269 no distant
    # caster could shade the E half of the portico. Fixer r3: at az 279 the W box does it (diagonal line, as in the photo),
    # so the slab is off (it drew a razor-straight vertical terminator across the back wall). Dict -> re-enable.
    'shadow_portico': None,
    # Fixer r3: the photo's shade is neutral/warm (B/R 1.08-1.17), lit by the sunlit ochre W facade of the Government
    # Palace east of the square. A diffuse-only bounce card there (outside the frustum: nearest corner bearing 48 deg,
    # HFOV +-17) warms the tympanum / frieze / column shade / back wall.
    'bounce_palace_E': {'x_range': [45.0, 65.0], 'y_range': [-150.0, 5.0], 'z_range': [-7.5, 24.0], 'material': 'ochre_facade'},
    # Fixer r3: explicit warm Sun lamp instead of the sky's disc. With the disc (sun_intensity 0.33) the lit whites stayed
    # pale cream (drum W wall B/R 0.75 vs 0.61 in the photo) whatever the dust; derivation: lit white linear (0.78,0.52,0.26)
    # minus sky fill (0.13,0.16,0.18) = direct (0.65,0.36,0.08) -> colour 1:0.55:0.12; a 16 W/m2 test gave direct_R 0.45
    # -> 16*0.65/0.45 = 23 W/m2. None -> back to the sky disc with 'sun_intensity'.
    # Calibrated on the scene: at 23 the R channel of every lit white clipped; 16 W/m2 puts the drum W wall at ~(228,194,150)
    # (photo (229,191,139)); the remaining blue on lit W faces is the pale west sky fill, so the lamp's B is 0.05.
    'sun_lamp': {'strength': 16.0, 'color': (1.0, 0.55, 0.05)},
    # Fixer r3: the patina's sun-lit limb is a light golden-olive in the photo ((131,117,78) vs the mid (41,50,45) and the
    # shaded E limb (19,37,44)): a 40:1 lit/shade ratio that a Lambertian base under this sun/sky cannot give (brightening
    # the base lifts the mid/shade 1:1). The real patina has a strong warm sun-side sheen that the Principled lobes cannot
    # put on the limb in this geometry (the half vector points down-SW). Stand-in: a second Sun lamp, same direction,
    # light-linked so that ONLY the copper objects receive it ('boost' x the main lamp). None -> off.
    'copper_sun': {'boost': 2.5, 'color': (1.0, 0.6, 0.25)},
}
# bounce card only (never seen by the camera): a bright ochre facade. 0.8 in R is above a real render's albedo, but the
# card stands for 100+ m of lit yellow frontage (palace + university wing) with one 20 x 155 m box.
MATERIAL_SPECS['ochre_facade'] = {'Base Color': (0.80, 0.56, 0.22, 1.0), 'Roughness': 0.8}
LOOK_MATERIALS = ('white_paint', 'wall', 'copper_green', 'roof_dark', 'gold', 'granite', 'zinc', 'glass', 'wood_door', 'ground')
# material polish (r4), tuned in close-ups from the spec camera against ref/crop_dome_drum.jpg / crop_statue_*.jpg:
GOLD_ROUGH = 0.10                   # polished gilt: one crisp sun highlight, the rest reflects the (dark) sky
GOLD_BASE_MUL = 0.65                # main orb rendered (127,111,52) vs photo (71,65,40) with rough 0.17-0.35 + coat;
                                    # 0.85 / 0.78 still left the full-frame orb 1.5x too bright ((130,124,75) vs (87,78,57))
GOLD_F82_TINT = (1.0, 0.70, 0.30)   # grazing (F82) tint gold too: a white F82 let the blue sky through at the limbs
ZINC_TINT = (1.0, 0.94, 0.78)       # x spec zinc: corner apostle (145,140,134) vs photo (155,139,110) -> less blue
GRANITE_BLOCK = (0.9, 0.32, 0.012)  # block length, course height, joint width (m) of the podium / stair-wall granite


# ----------------------------------------------------------------------------- node helpers
def _bsdf(m):
    nt = m.node_tree
    for n in nt.nodes:
        if n.bl_idname == 'ShaderNodeBsdfPrincipled':
            return n
    # should not happen for mat()-made materials; build a minimal tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(b.outputs['BSDF'], out.inputs['Surface'])
    return b


def _sock(node, name, kind, out=False):
    """Socket by name AND type (ShaderNodeMix has several 'A'/'B' sockets)."""
    for s in (node.outputs if out else node.inputs):
        if s.name == name and s.type == kind:
            return s
    return (node.outputs if out else node.inputs)[name]


def _unlink(nt, socket):
    for l in list(socket.links):
        nt.links.remove(l)


def _coords(nt, scale=(1.0, 1.0, 1.0), x=-1400, y=0):
    tc = nt.nodes.new('ShaderNodeTexCoord'); tc.location = (x, y)
    mp = nt.nodes.new('ShaderNodeMapping'); mp.location = (x + 200, y)
    mp.inputs['Scale'].default_value = scale
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    return mp.outputs['Vector']


def _noise(nt, vec, scale, detail=2.0, roughness=0.5, distortion=0.0, x=-1000, y=0):
    n = nt.nodes.new('ShaderNodeTexNoise'); n.location = (x, y)
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = roughness
    n.inputs['Distortion'].default_value = distortion
    nt.links.new(vec, n.inputs['Vector'])
    return n


def _ramp(nt, fac, stops, x=-700, y=0, interp='LINEAR'):
    """stops = [(pos, (r,g,b)), ...]"""
    r = nt.nodes.new('ShaderNodeValToRGB'); r.location = (x, y)
    r.color_ramp.interpolation = interp
    els = r.color_ramp.elements
    while len(els) > 1:
        els.remove(els[-1])
    els[0].position = stops[0][0]; els[0].color = tuple(stops[0][1]) + (1.0,)
    for pos, c in stops[1:]:
        e = els.new(pos); e.color = tuple(c) + (1.0,)
    nt.links.new(fac, r.inputs['Factor'])
    return r


def _mix(nt, fac, a, b_socket, blend='MIX', x=-400, y=0, a_is_socket=False):
    mx = nt.nodes.new('ShaderNodeMix'); mx.location = (x, y)
    mx.data_type = 'RGBA'; mx.blend_type = blend; mx.clamp_result = True
    mx.inputs[0].default_value = fac
    A = _sock(mx, 'A', 'RGBA'); B = _sock(mx, 'B', 'RGBA')
    if a_is_socket:
        nt.links.new(a, A)
    else:
        A.default_value = tuple(a) if len(a) == 4 else tuple(a) + (1.0,)
    nt.links.new(b_socket, B)
    return _sock(mx, 'Result', 'RGBA', out=True)


def _bump(nt, height, bsdf, strength=0.1, distance=0.02, x=-400, y=-400):
    bp = nt.nodes.new('ShaderNodeBump'); bp.location = (x, y)
    bp.inputs['Strength'].default_value = strength
    bp.inputs['Distance'].default_value = distance
    nt.links.new(height, bp.inputs['Height'])
    _unlink(nt, bsdf.inputs['Normal'])
    nt.links.new(bp.outputs['Normal'], bsdf.inputs['Normal'])
    return bp


def _map_range(nt, fac, lo, hi, x=-400, y=-200):
    mr = nt.nodes.new('ShaderNodeMapRange'); mr.location = (x, y)
    mr.inputs['To Min'].default_value = lo; mr.inputs['To Max'].default_value = hi
    nt.links.new(fac, mr.inputs['Value'])
    return mr.outputs['Result']


def _reset_tree(m, base_rgb, rough, metallic=0.0, spec_level=0.5):
    """Rebuild a clean Principled tree with the given constants (idempotent upgrades)."""
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (300, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (0, 0)
    nt.links.new(b.outputs['BSDF'], out.inputs['Surface'])
    b.inputs['Base Color'].default_value = tuple(base_rgb) + (1.0,)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metallic
    b.inputs['Specular IOR Level'].default_value = spec_level
    return nt, b


def _spec_rgb(spec, name, fallback):
    v = spec.get('materials', {}).get(name, {})
    return tuple(v.get('rgb', fallback))[:3], v.get('roughness', None), v.get('metallic', None)


def apply_spec_materials(spec):
    """Copy spec['materials'] (linear rgb, roughness, metallic) into common.MATERIAL_SPECS."""
    for k, v in spec.get('materials', {}).items():
        if isinstance(v, dict) and 'rgb' in v:
            d = {'Base Color': tuple(v['rgb'])[:3] + (1.0,), 'Roughness': v.get('roughness', 0.6)}
            if 'metallic' in v:
                d['Metallic'] = v['metallic']
            MATERIAL_SPECS[k] = d


# ----------------------------------------------------------------------------- material upgrades (in place)
def _upgrade_paint(m, base, rough, variation=0.35, greyer=(0.90, 0.90, 0.905), bump_strength=0.06):
    """Warm white/wall paint: faint large-scale tonal variation (Noise->ColorRamp multiplied in) + subtle bump."""
    nt, b = _reset_tree(m, base, rough)
    vec = _coords(nt)
    n1 = _noise(nt, vec, scale=0.07, detail=2.5, roughness=0.55, y=200)              # ~14 m blotches
    rp = _ramp(nt, n1.outputs['Factor'], [(0.38, greyer), (0.62, (1.0, 1.0, 1.0))], y=200)
    col = _mix(nt, variation, base, rp.outputs['Color'], blend='MULTIPLY', y=200)
    nt.links.new(col, b.inputs['Base Color'])
    n2 = _noise(nt, vec, scale=9.0, detail=3.0, roughness=0.6, y=-300)               # fine render texture
    _bump(nt, n2.outputs['Factor'], b, strength=bump_strength, distance=0.01)
    rr = _map_range(nt, n2.outputs['Factor'], rough - 0.06, rough + 0.06, y=-100)
    nt.links.new(rr, b.inputs['Roughness'])


def _upgrade_copper(m, base, rough, metallic, rough_const=0.7, spec_level=0.15, spec_tint=(1.0, 0.85, 0.55), light_mul=1.8,
                    sheen=0.0, sheen_tint=(1.0, 0.8, 0.45), sheen_rough=0.4):
    """Patina: dark olive-green with mild vertical streaks (anisotropic noise), low metallic.
    Fixer r2: the dome read as flat olive-grey on the W half and 2x too light / teal on the E half (photo: golden-olive
    limb falling to near-black teal). Ramp multipliers 0.8/1.35/2.4-2.7 -> 0.8/1.2/1.3, constant roughness (the
    -0.15..+0.05 map made the streaks glossy sky-mirrors), Specular IOR Level 0.75 -> 0.35; spec.copper_green base
    (0.04,0.07,0.055) -> olive (0.035,0.055,0.035) + warm Specular Tint (dome crop: W half (69,72,57) vs photo
    (94,90,65), E half (26,40,44) vs (17,35,42); the teal base gave (62,70,65) / (22,39,50)).
    Fixer r3: the lit limb was still too dark and not golden (main dome W (78,80,66) vs photo (131,117,78)) while the
    shade sides matched. Measured on the scene: roughness 0.42-0.5 with spec 0.35-0.5 mirrors the sky at BOTH grazing
    limbs (E limb (55,69,75) B/R 1.36 vs photo (19,37,44)); roughness 0.7 / spec 0.15 removes that (limb W B/R 0.60 =
    photo; a rough lobe at spec 0.3 still integrated the blue sky over the S face). Base (0.055,0.072,0.040) via spec,
    light stop x1.8; the golden limb brightness comes from LOOK['copper_sun']."""
    nt, b = _reset_tree(m, base, rough_const, metallic)
    vec = _coords(nt, scale=(1.0, 1.0, 0.18))                                        # stretched along Z -> streaks
    n1 = _noise(nt, vec, scale=1.6, detail=3.0, roughness=0.6, distortion=0.4, y=200)
    r, g, bl = base
    dark = (r * 0.8, g * 0.8, bl * 0.8)
    mid = (r * 1.2, g * 1.2, bl * 1.2)
    light = (r * light_mul, g * light_mul, bl * light_mul)
    rp = _ramp(nt, n1.outputs['Factor'], [(0.3, dark), (0.52, mid), (0.75, light)], y=200)
    col = _mix(nt, 0.7, base, rp.outputs['Color'], blend='MIX', y=200)
    nt.links.new(col, b.inputs['Base Color'])
    vec2 = _coords(nt, scale=(1.0, 1.0, 1.0), y=-500)
    n2 = _noise(nt, vec2, scale=6.0, detail=3.0, roughness=0.55, y=-300)
    _bump(nt, n2.outputs['Factor'], b, strength=0.08, distance=0.01)
    b.inputs['Specular IOR Level'].default_value = spec_level
    b.inputs['Specular Tint'].default_value = tuple(spec_tint) + (1.0,)
    if sheen > 0:      # warm velvet-like rim: brightens the sun-lit limb seen at grazing angles (the patina's golden sheen)
        b.inputs['Sheen Weight'].default_value = sheen
        b.inputs['Sheen Roughness'].default_value = sheen_rough
        b.inputs['Sheen Tint'].default_value = tuple(sheen_tint) + (1.0,)


def _upgrade_roof(m, base, rough):
    """Dark roofing (arm gables, return slabs, flat roofs): a ROUGH dielectric. Fixer r2: through _upgrade_copper
    (roughness 0.6, metallic 0.05, spec 0.75) the gable wedge above the raking cornice mirrored the bright sky at the
    grazing view angle and read as a pale second pediment; the photo shows dark olive there."""
    nt, b = _reset_tree(m, base, max(0.88, rough), 0.0, spec_level=0.2)
    vec = _coords(nt)
    n1 = _noise(nt, vec, scale=1.2, detail=3.0, roughness=0.6, y=200)
    rp = _ramp(nt, n1.outputs['Factor'], [(0.35, (0.85, 0.85, 0.85)), (0.65, (1.12, 1.12, 1.1))], y=200)
    col = _mix(nt, 0.6, base, rp.outputs['Color'], blend='MULTIPLY', y=200)
    nt.links.new(col, b.inputs['Base Color'])
    _bump(nt, n1.outputs['Factor'], b, strength=0.05, distance=0.01)
    b.inputs['Coat Weight'].default_value = 0.0


def _upgrade_gold(m, base, rough):
    """Gilded orbs / crosses / stars: polished metal. Polish r4: with the spec roughness spread by noise (0.17-0.35)
    plus a coat, the main orb rendered (127,111,52) - the sun smeared over half the sphere - vs the photo's (71,65,40):
    a dark gold ball with ONE crisp sun highlight. Now constant roughness GOLD_ROUGH (no roughness map), no coat,
    base x GOLD_BASE_MUL; `rough` (spec) is ignored on purpose."""
    base = tuple(c * GOLD_BASE_MUL for c in base)
    nt, b = _reset_tree(m, base, GOLD_ROUGH, 1.0)
    b.inputs['Specular Tint'].default_value = tuple(GOLD_F82_TINT) + (1.0,)
    b.inputs['Coat Weight'].default_value = 0.0


def _upgrade_granite(m, base, rough):
    """Granite (podium walls, stair side walls / copings / newels, wedge): fine grain + block-to-block tone and
    (polish r4, for close-ups) a Brick block pattern GRANITE_BLOCK in object space - vertical faces keyed on
    (x + y, z) so walls of either orientation show courses, near-horizontal faces (copings, podium top) on (x, y) -
    with per-block tone 0.9-1.1, darker recessed joints. The stair steps have their own 'granite_step' /
    'granite_nosing' trees in mod_statues_site (same palette entry, re-tinted below)."""
    nt, b = _reset_tree(m, base, rough)
    vec = _coords(nt)
    n1 = _noise(nt, vec, scale=28.0, detail=5.0, roughness=0.7, y=200)               # fine grain
    n2 = _noise(nt, vec, scale=0.9, detail=2.0, roughness=0.5, y=400)                # block-to-block tone
    rp1 = _ramp(nt, n1.outputs['Factor'], [(0.3, (0.78, 0.78, 0.80)), (0.7, (1.18, 1.16, 1.14))], y=200)
    rp2 = _ramp(nt, n2.outputs['Factor'], [(0.35, (0.85, 0.85, 0.87)), (0.65, (1.12, 1.10, 1.08))], y=400)
    c1 = _mix(nt, 1.0, base, rp1.outputs['Color'], blend='MULTIPLY', y=200)
    c2 = _mix(nt, 1.0, c1, rp2.outputs['Color'], blend='MULTIPLY', x=-200, y=300, a_is_socket=True)
    # block courses: Brick texture on (x + y, z) for vertical faces, (x, y) for near-horizontal ones
    sp = nt.nodes.new('ShaderNodeSeparateXYZ'); sp.location = (-1000, 800)
    nt.links.new(vec, sp.inputs['Vector'])
    xy = nt.nodes.new('ShaderNodeMath'); xy.operation = 'ADD'; xy.location = (-800, 850)
    nt.links.new(sp.outputs['X'], xy.inputs[0]); nt.links.new(sp.outputs['Y'], xy.inputs[1])
    cv = nt.nodes.new('ShaderNodeCombineXYZ'); cv.location = (-650, 850)
    nt.links.new(xy.outputs['Value'], cv.inputs['X']); nt.links.new(sp.outputs['Z'], cv.inputs['Y'])
    ch = nt.nodes.new('ShaderNodeCombineXYZ'); ch.location = (-650, 700)
    nt.links.new(sp.outputs['X'], ch.inputs['X']); nt.links.new(sp.outputs['Y'], ch.inputs['Y'])
    geo = nt.nodes.new('ShaderNodeNewGeometry'); geo.location = (-1000, 1050)
    sn = nt.nodes.new('ShaderNodeSeparateXYZ'); sn.location = (-800, 1050)
    nt.links.new(geo.outputs['True Normal'], sn.inputs['Vector'])
    up = nt.nodes.new('ShaderNodeMath'); up.operation = 'ABSOLUTE'; up.location = (-650, 1050)
    nt.links.new(sn.outputs['Z'], up.inputs[0])
    isflat = nt.nodes.new('ShaderNodeMath'); isflat.operation = 'GREATER_THAN'; isflat.location = (-500, 1050)
    isflat.inputs[1].default_value = 0.7
    nt.links.new(up.outputs['Value'], isflat.inputs[0])
    sw = nt.nodes.new('ShaderNodeMix'); sw.data_type = 'VECTOR'; sw.location = (-500, 800)
    nt.links.new(isflat.outputs['Value'], _sock(sw, 'Factor', 'VALUE'))
    nt.links.new(cv.outputs['Vector'], _sock(sw, 'A', 'VECTOR'))
    nt.links.new(ch.outputs['Vector'], _sock(sw, 'B', 'VECTOR'))
    brick = nt.nodes.new('ShaderNodeTexBrick'); brick.location = (-350, 800)
    brick.offset = 0.5; brick.offset_frequency = 2; brick.squash = 1.0
    brick.inputs['Scale'].default_value = 1.0
    brick.inputs['Brick Width'].default_value = GRANITE_BLOCK[0]
    brick.inputs['Row Height'].default_value = GRANITE_BLOCK[1]
    brick.inputs['Mortar Size'].default_value = GRANITE_BLOCK[2]
    brick.inputs['Mortar Smooth'].default_value = 0.2
    brick.inputs['Bias'].default_value = 0.0
    brick.inputs['Color1'].default_value = (1.10, 1.10, 1.10, 1.0)
    brick.inputs['Color2'].default_value = (0.90, 0.90, 0.90, 1.0)
    brick.inputs['Mortar'].default_value = (0.60, 0.60, 0.60, 1.0)
    nt.links.new(_sock(sw, 'Result', 'VECTOR', out=True), brick.inputs['Vector'])
    c3 = _mix(nt, 1.0, c2, brick.outputs['Color'], blend='MULTIPLY', x=-100, y=500, a_is_socket=True)
    nt.links.new(c3, b.inputs['Base Color'])
    # bump: grain + recessed joints
    inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.location = (-350, 600)
    inv.inputs[0].default_value = 1.0
    nt.links.new(brick.outputs['Factor'], inv.inputs[1])
    hgt = nt.nodes.new('ShaderNodeMath'); hgt.operation = 'MULTIPLY_ADD'; hgt.location = (-200, 600)
    hgt.inputs[1].default_value = 0.5
    nt.links.new(n1.outputs['Factor'], hgt.inputs[0]); nt.links.new(inv.outputs['Value'], hgt.inputs[2])
    _bump(nt, hgt.outputs['Value'], b, strength=0.25, distance=0.006)
    rr = _map_range(nt, n1.outputs['Factor'], rough - 0.1, min(1.0, rough + 0.1), y=-100)
    nt.links.new(rr, b.inputs['Roughness'])


def _upgrade_zinc(m, base, rough):
    nt, b = _reset_tree(m, base, rough, 0.08)
    vec = _coords(nt)
    n1 = _noise(nt, vec, scale=4.0, detail=3.0, roughness=0.6, y=200)
    rp = _ramp(nt, n1.outputs['Factor'], [(0.35, (0.86, 0.86, 0.88)), (0.65, (1.0, 1.0, 1.0))], y=200)
    col = _mix(nt, 0.5, base, rp.outputs['Color'], blend='MULTIPLY', y=200)
    nt.links.new(col, b.inputs['Base Color'])
    _bump(nt, n1.outputs['Factor'], b, strength=0.05, distance=0.01)


def _upgrade_glass(m, base, rough):
    """Dark, reflective window glass: plain dielectric (IOR 1.5 -> F0 4 %). spec level 1.0 + a coat (the first version)
    doubled the reflectance and made the panes read as pale sky-mirrors instead of the photo's dark grey-blue."""
    nt, b = _reset_tree(m, base, min(rough, 0.08), 0.0, spec_level=0.5)
    b.inputs['IOR'].default_value = 1.5


def _upgrade_wood(m, base, rough):
    nt, b = _reset_tree(m, base, rough)
    vec = _coords(nt, scale=(1.0, 1.0, 0.08))
    n1 = _noise(nt, vec, scale=8.0, detail=3.0, roughness=0.6, y=200)
    rp = _ramp(nt, n1.outputs['Factor'], [(0.3, (0.7, 0.68, 0.66)), (0.7, (1.15, 1.1, 1.05))], y=200)
    col = _mix(nt, 0.6, base, rp.outputs['Color'], blend='MULTIPLY', y=200)
    nt.links.new(col, b.inputs['Base Color'])
    _bump(nt, n1.outputs['Factor'], b, strength=0.08, distance=0.005)


def _upgrade_ground(m, base, rough):
    """Cobbles: Voronoi cells for the sett pattern (bump + per-stone tone)."""
    nt, b = _reset_tree(m, base, rough)
    vec = _coords(nt)
    vo = nt.nodes.new('ShaderNodeTexVoronoi'); vo.location = (-1000, 200)
    vo.feature = 'F1'; vo.distance = 'EUCLIDEAN'
    vo.inputs['Scale'].default_value = 5.0; vo.inputs['Randomness'].default_value = 0.6
    nt.links.new(vec, vo.inputs['Vector'])
    vo2 = nt.nodes.new('ShaderNodeTexVoronoi'); vo2.location = (-1000, -200)
    vo2.feature = 'DISTANCE_TO_EDGE'
    vo2.inputs['Scale'].default_value = 5.0; vo2.inputs['Randomness'].default_value = 0.6
    nt.links.new(vec, vo2.inputs['Vector'])
    rp = _ramp(nt, vo.outputs['Color'], [(0.3, (0.8, 0.8, 0.82)), (0.7, (1.15, 1.13, 1.1))], y=200)
    col = _mix(nt, 0.6, base, rp.outputs['Color'], blend='MULTIPLY', y=200)
    nt.links.new(col, b.inputs['Base Color'])
    rp2 = _ramp(nt, vo2.outputs['Distance'], [(0.0, (0, 0, 0)), (0.06, (1, 1, 1))], y=-200)
    _bump(nt, rp2.outputs['Color'], b, strength=0.35, distance=0.02)


def _retint_derived(spec):
    """Materials other modules derive from a palette entry ('granite_step' = granite + per-step gradient in
    mod_statues_site, 'white_paint.001' duplicates, ...) keep their own node trees; only their colour constants
    (RGB nodes, unlinked Principled Base Color / Roughness / Metallic) are pointed at the spec palette, so the
    stairs come out right even if main built statues_site before apply_spec_materials() ran."""
    mats = spec.get('materials', {})
    names = sorted((n for n in LOOK_MATERIALS if n in mats), key=len, reverse=True)
    done = []
    for m in bpy.data.materials:
        if m.name in LOOK_MATERIALS or not m.use_nodes or m.node_tree is None:
            continue
        base = next((n for n in names if m.name.startswith(n + '_') or m.name.startswith(n + '.')), None)
        if base is None:
            continue
        v = mats[base]
        rgb = tuple(v['rgb'])[:3] + (1.0,)
        for n in m.node_tree.nodes:
            if n.bl_idname == 'ShaderNodeRGB':
                n.outputs[0].default_value = rgb
            elif n.bl_idname == 'ShaderNodeBsdfPrincipled':
                if not n.inputs['Base Color'].is_linked:
                    n.inputs['Base Color'].default_value = rgb
                if not n.inputs['Roughness'].is_linked and 'roughness' in v:
                    n.inputs['Roughness'].default_value = float(v['roughness'])
                if not n.inputs['Metallic'].is_linked and 'metallic' in v:
                    n.inputs['Metallic'].default_value = float(v['metallic'])
        m['look_retinted'] = base
        done.append(m)
    return done


def upgrade_materials(spec):
    """Create (if missing) and upgrade the shared materials in place. Returns the list of materials."""
    apply_spec_materials(spec)
    out = []
    for name in LOOK_MATERIALS:
        m = mat(name)
        base, rough, metallic = _spec_rgb(spec, name, MATERIAL_SPECS.get(name, MATERIAL_SPECS['default'])['Base Color'][:3])
        if rough is None:
            rough = MATERIAL_SPECS.get(name, {}).get('Roughness', 0.6)
        if name == 'white_paint':
            # slightly warm white, faint variation
            base = (base[0] * 1.0, base[1] * 0.995, base[2] * 0.975)
            _upgrade_paint(m, base, rough, variation=0.30, greyer=(0.91, 0.905, 0.90), bump_strength=0.05)
        elif name == 'wall':
            # wall field a touch darker/greyer than the trim (two-tone as in the photo)
            base = (base[0] * 0.985, base[1] * 0.985, base[2] * 1.0)
            _upgrade_paint(m, base, rough, variation=0.45, greyer=(0.88, 0.88, 0.89), bump_strength=0.08)
        elif name == 'copper_green':
            # warm specular tint: the sun-grazed W limb of the dome reads golden-olive in the photo, not teal
            _upgrade_copper(m, base, rough, 0.0 if metallic is None else metallic)
        elif name == 'roof_dark':
            _upgrade_roof(m, base, rough)
        elif name == 'gold':
            _upgrade_gold(m, base, rough)
        elif name == 'granite':
            _upgrade_granite(m, base, rough)
        elif name == 'zinc':
            # light WARM grey (polish r4: ZINC_TINT, the corner apostle rendered neutral (145,140,134) vs the photo's
            # beige (155,139,110); was (1.0, 0.99, 0.96))
            base = (base[0] * ZINC_TINT[0], base[1] * ZINC_TINT[1], base[2] * ZINC_TINT[2])
            _upgrade_zinc(m, base, rough)
        elif name == 'glass':
            _upgrade_glass(m, base, rough)
        elif name == 'wood_door':
            _upgrade_wood(m, base, rough)
        elif name == 'ground':
            _upgrade_ground(m, base, rough)
        m['look_upgraded'] = 1
        out.append(m)
    _retint_derived(spec)
    return out


def _blocker_box(name, sb, gz, col):
    old = bpy.data.objects.get(name)
    if old is not None:                      # idempotent: build() may be called more than once
        return old
    x0, x1 = sb['x_range']; y0, y1 = sb['y_range']
    z0 = gz - LOOK.get('shadow_sink', 0.5)
    ob = add_box(name, (x1 - x0, y1 - y0, sb['top_z'] - z0), ((x0 + x1) / 2, (y0 + y1) / 2, (sb['top_z'] + z0) / 2),
                 material='wall', collection=col)
    ob.visible_camera = False
    ob.visible_glossy = False
    ob.visible_transmission = False
    return ob


def _shadow_slab(name, sb, col):
    """Shadow-ONLY slab: seen by shadow rays alone (camera/diffuse/glossy/transmission off), so it darkens nothing
    but the direct sun. Fixer r2: in the photo the S portico east of column 2 stands in the shadow of the buildings
    west of the square; at az 269 the sun rays run parallel to the facade through the 6 m gap between the W and NW
    blockers (y -39..-33), so no distant caster can shade it. This thin slab between columns 2 and 3 shades columns
    3-6 and the back wall east of x~-4 below top_z as a horizontal line (the photo's diagonal is not reproducible
    with a static caster at this azimuth)."""
    old = bpy.data.objects.get(name)
    if old is not None:
        return old
    x0, x1 = sb['x_range']; y0, y1 = sb['y_range']; z0, z1 = sb['z_range']
    ob = add_box(name, (x1 - x0, y1 - y0, z1 - z0), ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                 material='roof_dark', collection=col)
    ob.visible_camera = False
    ob.visible_diffuse = False
    ob.visible_glossy = False
    ob.visible_transmission = False
    ob.visible_volume_scatter = False
    ob.visible_shadow = True
    return ob


def _bounce_card(name, sb, col):
    """Diffuse-only bounce box (fixer r3): stands for the sunlit ochre west facade of the Government Palace on the east
    side of Senate Square, which warms every shaded south face in the photo. Camera and glossy rays never see it;
    diffuse and shadow rays do (it also keeps the sun off the ground behind it, as the real building does)."""
    old = bpy.data.objects.get(name)
    if old is not None:
        return old
    x0, x1 = sb['x_range']; y0, y1 = sb['y_range']; z0, z1 = sb['z_range']
    ob = add_box(name, (x1 - x0, y1 - y0, z1 - z0), ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                 material=sb.get('material', 'ochre_facade'), collection=col)
    ob.visible_camera = False
    ob.visible_glossy = False
    ob.visible_transmission = False
    ob.visible_volume_scatter = False
    ob.visible_diffuse = True
    ob.visible_shadow = True
    return ob


def shadow_blocker(spec, col):
    """Off-camera boxes standing for the buildings on the west / north-west side of Senate Square: they cast the
    long golden-hour shadow over the square, the stairs, the lower portico and the west wing (as in the photo),
    invisible to camera rays; plus the ochre bounce card for the palace east of the square. Returns the list."""
    gz = spec['square_ground_z']
    out = [_blocker_box('look_shadow_buildings_W', LOOK['shadow_building'], gz, col)]
    if LOOK.get('shadow_building_NW'):
        out.append(_blocker_box('look_shadow_buildings_NW', LOOK['shadow_building_NW'], gz, col))
    if LOOK.get('shadow_portico'):
        out.append(_shadow_slab('look_shadow_portico', LOOK['shadow_portico'], col))
    if LOOK.get('bounce_palace_E'):
        out.append(_bounce_card('look_bounce_palace_E', LOOK['bounce_palace_E'], col))
    return out


def build(spec, col):
    """Module contract: upgrades the shared materials in place; optionally adds the off-camera shadow caster."""
    upgrade_materials(spec)
    objs = []
    if LOOK.get('square_shadow'):
        objs += shadow_blocker(spec, col)
    return objs


# ----------------------------------------------------------------------------- world / camera / render settings
def setup_look(spec):
    """World via setup_sun_sky(**spec['sun']) + view look + camera from spec['camera'] + Cycles final settings."""
    sc = bpy.context.scene
    import inspect
    allowed = set(inspect.signature(setup_sun_sky).parameters)
    sun = {k: v for k, v in spec['sun'].items() if k in allowed}      # spec.sun may carry notes one day
    lampspec = LOOK.get('sun_lamp')
    if lampspec:
        # fixer r3: explicit warm Sun lamp, sky disc off (the sky node itself is untouched -> same blue sky)
        world, lamp = setup_sun_sky(**sun, sun_disc=False, sun_strength=float(lampspec['strength']),
                                    sun_color=tuple(lampspec['color']))
    else:
        world, lamp = setup_sun_sky(**sun)
    sky = next((n for n in world.node_tree.nodes if n.bl_idname == 'ShaderNodeTexSky'), None)
    if sky is not None:
        sky.sun_intensity = LOOK['sun_intensity']          # only matters with the sky disc (sun_lamp None)
        try:
            sky.ground_albedo = LOOK['sky_ground_albedo']
        except Exception:
            pass
    _copper_sun(sun, lamp if lampspec else None)
    vs = sc.view_settings
    try:
        vs.view_transform = LOOK['view_transform']
    except Exception:
        pass
    try:
        vs.look = LOOK['look']
    except Exception:
        try:
            vs.look = 'None'
        except Exception:
            pass
    vs.exposure = sun.get('exposure', -4.0)
    vs.gamma = 1.0
    try:
        vs.use_white_balance = LOOK['white_balance']
        vs.white_balance_temperature = LOOK['wb_temperature']
        vs.white_balance_tint = LOOK['wb_tint']
    except Exception:
        pass
    cam = spec['camera']
    setup_camera(cam['location'], cam['target'], lens=cam['lens'], shift_y=cam.get('shift_y', 0.0),
                 shift_x=cam.get('shift_x', 0.0))
    res = cam.get('resolution', [1536, 2048])
    sc.render.resolution_x, sc.render.resolution_y = int(res[0]), int(res[1])   # portrait 3:4
    sc.render.resolution_percentage = 100
    sc.render.pixel_aspect_x = sc.render.pixel_aspect_y = 1.0
    cycles_final_settings(sc, samples=LOOK['final_samples'])
    return world, sc.camera


def _copper_sun(sun, main_lamp):
    """Second Sun lamp received ONLY by the copper_green objects (Cycles light linking), see LOOK['copper_sun']."""
    sc = bpy.context.scene
    old = bpy.data.objects.get('Sun_copper')
    cs = LOOK.get('copper_sun')
    if not cs or main_lamp is None:
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        return None
    recv = bpy.data.collections.get('look_copper_receivers') or bpy.data.collections.new('look_copper_receivers')
    for ob in list(recv.objects):
        recv.objects.unlink(ob)
    n = 0
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and any(sl.material is not None and sl.material.name == 'copper_green' for sl in ob.material_slots):
            recv.objects.link(ob); n += 1
    ld = bpy.data.lights.get('Sun_copper') or bpy.data.lights.new('Sun_copper', 'SUN')
    ld.energy = float(cs['boost']) * float(LOOK['sun_lamp']['strength'])
    ld.angle = main_lamp.data.angle
    ld.color = tuple(cs['color'])
    if old is None:
        old = bpy.data.objects.new('Sun_copper', ld); sc.collection.objects.link(old)
    old.rotation_euler = main_lamp.rotation_euler
    try:
        old.light_linking.receiver_collection = recv
    except Exception as e:                    # no light linking (very old bpy): do not double-light the whole scene
        print('[look] light linking unavailable, copper sun off:', e)
        bpy.data.objects.remove(old, do_unlink=True)
        return None
    print(f'[look] copper sun {ld.energy:.1f} W/m2 -> {n} copper objects')
    return old


def cycles_final_settings(sc=None, samples=None):
    sc = sc or bpy.context.scene
    sc.render.engine = 'CYCLES'
    cy = sc.cycles
    cy.device = 'CPU'
    cy.samples = int(samples or LOOK['final_samples'])
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = LOOK['adaptive_threshold']
    cy.adaptive_min_samples = 0
    cy.time_limit = 0.0
    cy.use_denoising = True
    try:
        cy.denoiser = 'OPENIMAGEDENOISE'
        cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
        cy.denoising_prefilter = 'ACCURATE'
        cy.denoising_use_gpu = False
    except Exception:
        pass
    cy.max_bounces = 8
    cy.diffuse_bounces = 4
    cy.glossy_bounces = 4
    cy.transmission_bounces = 6
    cy.volume_bounces = 0
    cy.transparent_max_bounces = 8
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = 10.0
    cy.use_light_tree = True
    cy.light_sampling_threshold = 0.01
    cy.pixel_filter_type = 'BLACKMAN_HARRIS'
    cy.filter_width = 1.5
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    sc.render.image_settings.color_depth = '8'
    sc.render.image_settings.compression = 50
    return cy


def final_render(path, res=None, samples=None):
    """Final-quality render of the current camera. res defaults to spec camera resolution (1536x2048)."""
    sc = bpy.context.scene
    if res is None:
        res = (sc.render.resolution_x, sc.render.resolution_y)
    cycles_final_settings(sc, samples=samples or LOOK['final_samples'])
    return render(path, res=res, samples=samples or LOOK['final_samples'], denoise=True, time_limit=0.0)


# ----------------------------------------------------------------------------- stand-in massing (tests only; the real
# geometry comes from mod_body / mod_portico / mod_domes / mod_statues_site)
def _standin_massing(spec, col):
    objs = []
    W, Wl = 'white_paint', 'wall'
    gz = spec['square_ground_z']
    objs.append(add_box('t_ground', (600, 600, 0.2), (0, 0, gz - 0.1), material='ground', collection=col))
    p = spec['podium']
    y0, y1 = p['south_y'], p['north_y']
    objs.append(add_box('t_podium', (2 * p['half_w'], y1 - y0, p['height']), (0, (y0 + y1) / 2, gz + p['height'] / 2), material='granite', collection=col))
    s = spec['stairs']
    for k in range(s['n_steps']):
        ztop = s['top_z'] - s['step_rise'] * k
        ys = s['top_y'] - s['step_run'] * (k + 1)
        depth = s['top_y'] - ys
        objs.append(add_box(f't_step_{k:02d}', (s['width'], depth, s['step_rise']), (0, ys + depth / 2, ztop - s['step_rise'] / 2), material='granite', collection=col))
    sw = s['side_walls']
    for sx in (-1, 1):
        objs.append(add_box(f't_stairwall_{sx}', (sw['thickness'], s['top_y'] - s['bottom_y'], 1.0),
                            (sx * (sw['x_outer'] - sw['thickness'] / 2), (s['top_y'] + s['bottom_y']) / 2, -3.0), material='granite', collection=col))
    c = spec['core']
    objs.append(add_box_on('t_core', (2 * c['half_w'], 2 * c['half_d'], c['parapet_top_z']), (0, 0, 0), material=Wl, collection=col))
    a = c['attic']
    H, D, h, d = a['half_w'], a['half_d'], a['arm_half_w'], a['arm_half_d']
    plus = [(h, D), (-h, D), (-h, d), (-H, d), (-H, -d), (-h, -d), (-h, -D), (h, -D), (h, -d), (H, -d), (H, d), (h, d)]
    objs.append(extrude_polygon('t_attic', plus, a['top_z'] - a['z_base'], a['z_base'], material=Wl, collection=col))
    b = a['balustrade']
    for i, (cx, cy, sx, sy) in enumerate([(0, -D + 0.15, 2 * h, 0.3), (0, D - 0.15, 2 * h, 0.3), (-H + 0.15, 0, 0.3, 2 * d), (H - 0.15, 0, 0.3, 2 * d)]):
        objs.append(add_box_on(f't_attic_bal_{i}', (sx, sy, b['height']), (cx, cy, b['z_base']), material=W, collection=col))
    ar = spec['arms']; com = ar['common']
    for name in ('south', 'north', 'east', 'west'):
        dd = ar[name]
        x0, x1 = dd['x_range']; y0, y1 = dd['y_range']
        objs.append(add_box_on(f't_arm_{name}', (x1 - x0, y1 - y0, com['parapet']['z_top']), ((x0 + x1) / 2, (y0 + y1) / 2, 0), material=Wl, collection=col))
        # white entablature band + pilasters on the arm (so the two-tone shows)
        ez0, ez1 = com['entablature']['z_bottom'], com['entablature']['z_top']
        objs.append(add_box_on(f't_arm_{name}_ent', (x1 - x0 + 0.6, y1 - y0 + 0.6, ez1 - ez0), ((x0 + x1) / 2, (y0 + y1) / 2, ez0), material=W, collection=col))
        r = com['roof']; hw = com['half_w']
        prof = [(-hw + 0.6, r['eaves_z']), (hw - 0.6, r['eaves_z']), (0, r['ridge_z'])]
        ro = prism(f't_roof_{name}', prof, dd['length_from_core_face'], material='roof_dark', collection=col)
        if name in ('south', 'north'):
            place(ro, (0, y0, 0), (0, 0, math.radians(90)))
        else:
            place(ro, (x0, 0, 0), (0, 0, 0))
        objs.append(ro)
    # pilasters + windows on the south arm end wall and flanks (stand-in)
    for xo in (-9.0, -5.0, 5.0, 9.0):
        objs.append(add_box_on(f't_S_pil_{xo}', (1.0, 0.25, 11.5), (xo, -33.5 - 0.1, 0), material=W, collection=col))
    for xo in (-7.0, 7.0):
        objs.append(add_box(f't_S_win_lo_{xo}', (2.2, 0.1, 3.6), (xo, -33.5 - 0.02, 2.8), material='glass', collection=col))
        objs.append(add_box(f't_S_win_up_{xo}', (2.2, 0.1, 2.0), (xo, -33.5 - 0.02, 7.6), material='glass', collection=col))
    objs.append(add_box('t_S_door', (1.65, 0.1, 4.5), (0, -33.5 - 0.02, 2.25 + 0.2), material='wood_door', collection=col))
    for xo in (-20.5, -23.5):
        objs.append(add_box(f't_W_win_lo_{xo}', (2.2, 0.1, 3.6), (xo, -11.0 - 0.02, 2.8), material='glass', collection=col))
        objs.append(add_box(f't_W_win_up_{xo}', (2.2, 0.1, 2.0), (xo, -11.0 - 0.02, 7.6), material='glass', collection=col))
    po = spec['portico']; e, pd, ap = po['entablature'], po['pediment'], po['acroteria_pedestals']
    for inst in po['instances']:
        n = inst['name']; cl, wall = inst['column_line'], inst['wall']
        along_x = n in ('S', 'N')
        front = cl - math.copysign(e['front_face_offset_from_column_line'], wall - cl)
        for i, off in enumerate(po['column_offsets']):
            pos = (off, cl, 0) if along_x else (cl, off, 0)
            objs.append(add_cylinder(f't_{n}_col_{i}', po['r_bottom'], po['column_h'], pos, segments=24, material=W, collection=col))
            objs.append(add_box_on(f't_{n}_plinth_{i}', (po['plinth_w'], po['plinth_w'], po['plinth_h']), pos, material=W, collection=col))
        depth = abs(wall - front); mid = (front + wall) / 2
        size = (2 * e['half_w'], depth, e['z_top'] - e['z_bottom']) if along_x else (depth, 2 * e['half_w'], e['z_top'] - e['z_bottom'])
        ctr = (0, mid, e['z_bottom'] + size[2] / 2) if along_x else (mid, 0, e['z_bottom'] + size[2] / 2)
        objs.append(add_box(f't_{n}_entab', size, ctr, material=W, collection=col))
        tri = [(-pd['half_w'], pd['base_z']), (pd['half_w'], pd['base_z']), (0, pd['apex_z'])]
        t = prism(f't_{n}_pediment', tri, 1.2, material=W, collection=col)
        if n == 'S':
            place(t, (0, front + 1.2, 0), (0, 0, math.radians(-90)))
        elif n == 'N':
            place(t, (0, front - 1.2, 0), (0, 0, math.radians(90)))
        elif n == 'E':
            place(t, (front - 1.2, 0, 0), (0, 0, 0))
        else:
            place(t, (front, 0, 0), (0, 0, 0))
        objs.append(t)
        for lab, offs, pedk in (('apex', [0.0], 'apex'), ('corner', [-ap['corners']['offset_along_facade'], ap['corners']['offset_along_facade']], 'corners')):
            P = ap[pedk]
            for off in offs:
                pos = (off, cl, P['z_base']) if along_x else (cl, off, P['z_base'])
                objs.append(add_box_on(f't_{n}_ped_{lab}_{off}', (P['size'], P['size'], P['z_top'] - P['z_base']), pos, material=W, collection=col))
    dr = spec['drum']
    for key in ('pedestal', 'base_ring'):
        dd = dr[key]
        objs.append(add_cylinder(f't_drum_{key}', dd['radius'], dd['z_top'] - dd['z_bottom'], (0, 0, dd['z_bottom']), material=W, collection=col))
    f = dr['foot']
    objs.append(add_cylinder('t_drum_foot', f['radius_bottom'], f['z_top'] - f['z_bottom'], (0, 0, f['z_bottom']), radius_top=f['radius_top'], material=W, collection=col))
    objs.append(add_cylinder('t_drum_shaft', dr['radius'], dr['entablature']['z_bottom'] - dr['shaft_z'][0], (0, 0, dr['shaft_z'][0]), material=W, collection=col))
    dc = dr['columns']
    for i in range(dc['count']):
        az = math.radians(dc['azimuth_offset_deg'] + i * 360.0 / dc['count'])
        objs.append(add_cylinder(f't_drum_col_{i}', dc['radius'], dc['z_top'] - dc['z_base'], (dc['r_axis'] * math.sin(az), dc['r_axis'] * math.cos(az), dc['z_base']), segments=16, material=W, collection=col))
        azb = math.radians(i * 360.0 / dc['count'])     # bay centres: tall window
        tw_ = dr['windows']['tall']
        wb = add_box(f't_drum_win_{i}', (tw_['width'], 0.1, tw_['height']), (0, 0, 0), material='glass', collection=col)
        wb.rotation_euler = (0, 0, -azb)
        wb.location = ((dr['radius'] + 0.03) * math.sin(azb), (dr['radius'] + 0.03) * math.cos(azb), tw_['z_bottom'] + tw_['height'] / 2)
        objs.append(wb)
    en, co, at = dr['entablature'], dr['cornice'], dr['attic_ring']
    objs.append(add_cylinder('t_drum_entab', en['radius'], en['z_top'] - en['z_bottom'], (0, 0, en['z_bottom']), material=W, collection=col))
    objs.append(add_cylinder('t_drum_cornice', co['radius'], co['z_top'] - co['z_bottom'], (0, 0, co['z_bottom']), material=W, collection=col))
    objs.append(add_cylinder('t_drum_attic', at['radius'], at['z_top'] - at['z_bottom'], (0, 0, at['z_bottom']), material=W, collection=col))
    ck = dr['clock']
    clk = add_cylinder('t_clock', ck['diameter'] / 2, 0.15, (0, 0, 0), segments=24, material='glass', collection=col)
    clk.rotation_euler = (math.radians(-90), 0, 0); clk.location = (0, -(dr['radius'] + 0.02), ck['z'])
    objs.append(clk)
    dm = spec['dome']
    prof = [(0.0, dm['z_base'])] + dome_profile(dm['radius'], dm['rise'], dm['z_base'])
    objs.append(lathe('t_dome', prof, material='copper_green', collection=col))
    la = dm['lantern']
    objs.append(add_cylinder('t_lantern', la['r_base'], la['z_top'] - la['z_bottom'], (0, 0, la['z_bottom']), radius_top=la['r_neck'], material='copper_green', collection=col))
    objs.append(add_cylinder('t_orb_neck', dm['orb']['neck_r'], dm['orb']['z'] - la['z_top'], (0, 0, la['z_top']), segments=12, material='gold', collection=col))
    objs.append(add_sphere('t_orb', dm['orb']['r'], (0, 0, dm['orb']['z']), material='gold', collection=col))
    cr = dm['cross']
    objs.append(add_box_on('t_cross_v', (cr['thickness'], cr['thickness'], cr['h']), (0, 0, cr['z_base']), material='gold', collection=col))
    objs.append(add_box('t_cross_h', (cr['w'], cr['thickness'], cr['thickness']), (0, 0, cr['crossbar_z']), material='gold', collection=col))
    tw = spec['towers']
    for name, (tx, ty) in zip(tw['names'], tw['positions']):
        P = tw['pedestal']
        objs.append(add_box_on(f't_tw_{name}_ped', (2 * P['half_w'], 2 * P['half_w'], P['z_top'] - P['z_bottom']), (tx, ty, P['z_bottom']), material=W, collection=col))
        S = tw['shaft']
        objs.append(add_box_on(f't_tw_{name}_shaft', (2 * S['half_w'], 2 * S['half_w'], S['z_top'] - S['z_bottom']), (tx, ty, S['z_bottom']), material=Wl, collection=col))
        E = tw['entablature']
        objs.append(add_box_on(f't_tw_{name}_ent', (2 * E['half_w'], 2 * E['half_w'], E['z_top'] - E['z_bottom']), (tx, ty, E['z_bottom']), material=W, collection=col))
        U = tw['upper_block']
        objs.append(add_box_on(f't_tw_{name}_upper', (2 * U['half_w'], 2 * U['half_w'], U['z_top'] - U['z_bottom']), (tx, ty, U['z_bottom']), material=W, collection=col))
        C = tw['cornice']
        objs.append(add_box_on(f't_tw_{name}_corn', (2 * C['half_w'], 2 * C['half_w'], C['z_top'] - C['z_bottom']), (tx, ty, C['z_bottom']), material=W, collection=col))
        Dd = tw['dome']
        prof = [(0.0, Dd['z_base'])] + dome_profile(Dd['r'], Dd['rise'], Dd['z_base'])
        objs.append(lathe(f't_tw_{name}_dome', prof, segments=32, center=(tx, ty, 0), material='copper_green', collection=col))
        O = tw['orb']
        objs.append(add_sphere(f't_tw_{name}_orb', O['r'], (tx, ty, O['z']), segments=24, rings=12, material='gold', collection=col))
        X = tw['cross']
        objs.append(add_box_on(f't_tw_{name}_cross', (X['thickness'], X['thickness'], X['h']), (tx, ty, X['z_base']), material='gold', collection=col))
        objs.append(add_box(f't_tw_{name}_crossbar', (X['w'], X['thickness'], X['thickness']), (tx, ty, X['z_base'] + X['h'] * 0.68), material='gold', collection=col))
    for st in spec['statues']:
        x, y, z = st['pos']
        objs.append(add_box_on(f"t_statue_{st['name']}", (0.7, 0.7, st['height']), (x, y, z), material='zinc', collection=col))
    return objs


def _material_sheet(spec, col):
    """Spheres + boxes of every material at ~10 m from the camera, lit by the scene sky."""
    names = list(LOOK_MATERIALS)
    objs = []
    n = len(names)
    cols = 5
    for i, name in enumerate(names):
        r, c = divmod(i, cols)
        x = (c - (cols - 1) / 2) * 2.4
        z = 3.6 - r * 2.6
        objs.append(add_sphere(f'ms_sph_{name}', 0.75, (x, 0.0, z + 0.9), material=name, collection=col))
        objs.append(add_box(f'ms_box_{name}', (1.6, 1.6, 0.5), (x, 0.0, z - 0.3), material=name, collection=col))
    objs.append(add_box('ms_floor', (40, 40, 0.2), (0, 0, -2.0), material='ground', collection=col))
    return objs


def _photo_metrics(render_path, spec):
    """Compare a few colour samples of the render with the same spots of the photo (sRGB 0-255)."""
    from PIL import Image
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    rd = Image.open(render_path).convert('RGB'); ph = Image.open(os.path.join(WORK, 'ref', 'photo_small.jpg')).convert('RGB')
    def samp(im, fx, fy, r=3):
        w, h = im.size; x, y = int(fx * w), int(fy * h)
        px = [im.getpixel((min(w - 1, max(0, x + i)), min(h - 1, max(0, y + j)))) for i in range(-r, r + 1) for j in range(-r, r + 1)]
        return tuple(int(sum(p[k] for p in px) / len(px)) for k in range(3))
    def proj(pt):
        v = world_to_camera_view(sc, sc.camera, Vector(pt)); return v.x, 1 - v.y
    dr = spec['drum']
    tw = spec['towers']; twx, twy = tw['positions'][1]          # SW tower
    spots = {   # name: (render fractional coords, photo fractional coords)  photo spots measured on photo_small
        'sky_top': ((0.5, 0.03), (0.5, 0.03)),
        'sky_left_mid': ((0.06, 0.52), (0.06, 0.52)),
        'sky_right_low': ((0.93, 0.60), (0.93, 0.60)),
        'drum_W_lit': (proj(((dr['radius'] + 0.06) * math.sin(math.radians(268)), (dr['radius'] + 0.06) * math.cos(math.radians(268)), 40.0)), (0.40, 0.47)),
        'drum_S_shade': (proj(((dr['radius'] + 0.06) * math.sin(math.radians(175)), (dr['radius'] + 0.06) * math.cos(math.radians(175)), 40.0)), (0.53, 0.52)),
        'towerSW_W_lit': (proj((twx - tw['shaft']['half_w'] - 0.05, twy, 21.5)), (0.28, 0.615)),
        'towerSW_S_shade': (proj((twx, twy - tw['shaft']['half_w'] - 0.05, 21.5)), (0.33, 0.60)),
        'tympanum': (proj((0.0, -37.4 - 0.01, 15.6)), (0.49, 0.700)),
        'col1_shaft': (proj((-6.2 - 0.3, -36.5 - 0.55, 6.0)), (0.445, 0.810)),
        'stairs': ((0.3, 0.96), (0.3, 0.96)),
        'dome_lit': (proj((-4.2, -1.0, 52.0)), (0.43, 0.43)),
        'dome_shade': (proj((3.0, -2.0, 52.0)), (0.50, 0.43)),
    }
    lines = []
    for k, (rf, pf) in spots.items():
        a, b = samp(rd, *rf), samp(ph, *pf)
        lines.append(f'{k:14s} render {a}  photo {b}')
    return '\n'.join(lines)


if __name__ == '__main__':
    import sys as _sys
    args = _sys.argv[1:]
    spec = load_spec()
    sc = reset_scene()
    col = get_collection('Cathedral')
    build(spec, col)                     # materials
    prev = tuple(spec['camera'].get('preview_resolution', [480, 640]))

    if args and args[0] == 'sweep':
        # low-res sun/sky sweep:  python mod_look.py sweep "az=269,el=5,ex=-3.2,du=0.4,oz=1.5,air=1,wb=8000,tint=10,look=Punchy;..."
        _standin_massing(spec, col)
        paths, labels = [], []
        import copy as _copy
        LOOK0, SUN0 = _copy.deepcopy(LOOK), _copy.deepcopy(spec['sun'])
        for combo in args[1].split(';'):
            kv = dict(t.split('=') for t in combo.split(',') if t)
            LOOK.update(_copy.deepcopy(LOOK0)); spec['sun'] = _copy.deepcopy(SUN0)
            sun = spec['sun']
            for key, name in (('az', 'azimuth_deg'), ('el', 'elevation_deg'), ('ex', 'exposure'), ('du', 'dust'), ('oz', 'ozone'), ('air', 'air')):
                if key in kv:
                    sun[name] = float(kv[key])
            if 'wb' in kv: LOOK['wb_temperature'] = float(kv['wb'])
            if 'tint' in kv: LOOK['wb_tint'] = float(kv['tint'])
            if 'vt' in kv: LOOK['view_transform'] = kv['vt'].replace('_', ' ')
            if 'look' in kv: LOOK['look'] = kv['look'].replace('_', ' ')
            if 'alb' in kv: LOOK['sky_ground_albedo'] = float(kv['alb'])
            if 'sun' in kv: LOOK['sun_intensity'] = float(kv['sun'])
            setup_look(spec)
            tag = combo.replace('=', '').replace(',', '_')
            p = render(os.path.join(PREVIEWS, f'look_sweep_{tag}.png'), res=(480, 640) if 'big' in kv else (240, 320), samples=16)
            print('==', tag); print(_photo_metrics(p, spec))
            paths.append(p); labels.append(tag)
        contact_sheet([os.path.join(WORK, 'ref', 'photo_small.jpg')] + paths, os.path.join(PREVIEWS, 'look_sweep_contact.png'), ['PHOTO'] + labels, height=480)
        _sys.exit(0)

    # (1) photo viewpoint with the stand-in massing
    objs = _standin_massing(spec, col)
    setup_look(spec)
    print('standin objects', len(objs), 'count_scene', count_scene())
    p1 = render(os.path.join(PREVIEWS, 'mod_look_1.png'), res=prev, samples=LOOK['preview_samples'])
    print(compare_with_photo(p1))
    print(_photo_metrics(p1, spec))

    # (2) three-quarter close-up of the drum / portico (materials in the real light)
    setup_camera((-70, -75, 20), (-2, -20, 30), lens=50)
    render(os.path.join(PREVIEWS, 'mod_look_2.png'), res=prev, samples=LOOK['preview_samples'])

    # (3) material sheet at 10 m (fresh scene, same sky/look)
    sc = reset_scene(); col = get_collection('Cathedral')
    build(spec, col)
    _material_sheet(spec, col)
    setup_look(spec)
    setup_camera((2.0, -10.0, 2.0), (0.0, 0.0, 1.4), lens=35)
    render(os.path.join(PREVIEWS, 'mod_look_3.png'), res=(640, 480), samples=LOOK['preview_samples'])
    print('done')
