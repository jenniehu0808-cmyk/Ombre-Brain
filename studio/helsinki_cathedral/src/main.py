"""main.py - integrator for the Helsinki Cathedral build (bpy 5.2, headless, Cycles CPU).

Build order (binding): mod_look.apply_spec_materials(spec) FIRST (so palette-derived materials such as
statues_site's 'granite_step' are born with the spec colours), then mod_body, mod_portico, mod_domes,
mod_statues_site, then mod_look.build (procedural material upgrade + off-camera shadow caster) and
mod_look.setup_look (world/sun, view transform, camera, Cycles settings). Then render.

CLI:  python main.py [--res W H] [--samples N] [--out path.png] [--blend path.blend]
                     [--aerial] [--aerial-out path.png] [--no-compare] [--no-render]
Defaults: previews/full_v1.png at 600x800, 48 samples, followed by compare_with_photo().
--aerial adds a high three-quarter check view from the south-west (35 deg elevation, 150 m away).
Works both as a script in WORK and as the `main` module of the single-file bundle (make_single_file.py
calls main.main()).
"""
import sys, os, time, math
from common import *
import mod_body, mod_portico, mod_domes, mod_statues_site, mod_look

DEFAULT_RES = (600, 800)
DEFAULT_SAMPLES = 48


def parse_args(argv):
    opts = {'res': DEFAULT_RES, 'samples': DEFAULT_SAMPLES, 'out': os.path.join(PREVIEWS, 'full_v1.png'),
            'blend': None, 'aerial': False, 'aerial_out': os.path.join(PREVIEWS, 'full_v1_aerial.png'),
            'compare': True, 'render': True}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--res' and i + 2 < len(argv):
            opts['res'] = (int(argv[i + 1]), int(argv[i + 2])); i += 3
        elif a == '--samples' and i + 1 < len(argv):
            opts['samples'] = int(argv[i + 1]); i += 2
        elif a == '--out' and i + 1 < len(argv):
            opts['out'] = os.path.abspath(argv[i + 1]); i += 2
        elif a == '--blend' and i + 1 < len(argv):
            opts['blend'] = os.path.abspath(argv[i + 1]); i += 2
        elif a == '--aerial':
            opts['aerial'] = True; i += 1
        elif a == '--aerial-out' and i + 1 < len(argv):
            opts['aerial_out'] = os.path.abspath(argv[i + 1]); opts['aerial'] = True; i += 2
        elif a == '--no-compare':
            opts['compare'] = False; i += 1
        elif a == '--no-render':
            opts['render'] = False; i += 1
        else:
            print('[main] ignoring argument', a); i += 1
    return opts


def build_all(spec):
    """Build the whole cathedral into collection 'Cathedral'. Returns dict module -> list of objects."""
    col = get_collection('Cathedral')
    mod_look.apply_spec_materials(spec)          # palette first (HARNESS/SPEC ownership: look owns materials)
    built = {}
    for name, mod in (('body', mod_body), ('portico', mod_portico), ('domes', mod_domes),
                      ('statues_site', mod_statues_site)):
        t = time.time()
        built[name] = mod.build(spec, col)
        print('[main] %-13s %4d objects  %.1fs  scene=%s' % (name, len(built[name]), time.time() - t, count_scene()))
    t = time.time()
    built['look'] = mod_look.build(spec, col)    # material upgrade + shadow caster
    print('[main] %-13s %4d objects  %.1fs' % ('look', len(built['look']), time.time() - t))
    return built


def aerial_camera(spec, distance=150.0, elevation_deg=35.0, azimuth_deg=225.0, target=(0.0, 0.0, 22.0), lens=35.0):
    """High three-quarter check view: camera `distance` from `target`, seen from compass `azimuth_deg`
    (225 = south-west) at `elevation_deg` above the horizontal."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    loc = Vector(target) + d * distance
    return setup_camera(tuple(loc), target, lens=lens, name='Camera_aerial', clip_end=60000.0)   # ground to the horizon


def main(argv=None):
    opts = parse_args(sys.argv[1:] if argv is None else argv)
    t0 = time.time()
    reset_scene()
    spec = load_spec()
    build_all(spec)
    mod_look.setup_look(spec)                    # world/sun, view transform, camera, Cycles settings
    n_obj, n_poly = count_scene()
    print('[main] count_scene: %d mesh objects, %d polygons  (build %.1fs)' % (n_obj, n_poly, time.time() - t0))

    # leave the final render settings in the scene even when not rendering now (F12 in the GUI)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = int(opts['res'][0]), int(opts['res'][1])
    sc.render.resolution_percentage = 100
    sc.cycles.samples = int(opts['samples'])
    sc.render.filepath = opts['out']
    if opts['blend']:
        save_blend(opts['blend'])
    if not opts['render']:
        print('[main] scene ready (no render requested): %dx%d, %d samples -> %s' %
              (opts['res'][0], opts['res'][1], opts['samples'], opts['out']))
        return

    t = time.time()
    p = render(opts['out'], res=opts['res'], samples=opts['samples'])
    print('[main] main view %.1fs -> %s' % (time.time() - t, p))
    if opts['compare']:
        cmp_path = compare_with_photo(p)
        if cmp_path:
            print('[main] compare ->', cmp_path)

    if opts['aerial']:
        sc = bpy.context.scene
        main_cam = sc.camera
        aerial_camera(spec)
        t = time.time()
        pa = render(opts['aerial_out'], res=(opts['res'][1], opts['res'][0]), samples=opts['samples'])
        print('[main] aerial view %.1fs -> %s' % (time.time() - t, pa))
        sc.camera = main_cam                     # restore the photo camera (e.g. before a later --blend save)


if __name__ == '__main__':
    main()
