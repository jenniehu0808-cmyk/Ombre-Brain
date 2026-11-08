#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Queen's Tower · Imperial College London (South Kensington)
===========================================================
A fully procedural Blender model (bpy API, no external assets) of the Queen's Tower –
the 87 m Portland-stone campanile with the copper dome that is all that remains of
T. E. Collcutt's Imperial Institute (1887–93) – standing on the Queen's Lawn, with the
two Imperial Institute lions at the foot of the south steps, the Sherfield Building and
the Library as background massing, London planes in November colour, and a low
south-western sun.

How to use
----------
* Blender GUI  : Scripting workspace → open this file → Run Script. The current scene is
                 replaced by an empty one, the model is built, cameras / sky / render
                 settings are configured. Press F12 to render (Cycles, CPU is fine).
* Command line : blender -b -P queens_tower.py -- --res 1536 2048 --samples 256 --out qt.png
* bpy wheel    : pip install bpy   (Blender 5.2 LTS = Python 3.13)
                 python queens_tower.py --res 1536 2048 --samples 256 --out qt.png --blend qt.blend

Options: --cam lawn|dome|lions|aerial|all   --quick (fewer balusters/segments)   --no-render
         --blend FILE (save .blend)    --exposure EV   --sun-el DEG --sun-az DEG
         --patina (verdigris dome instead of the 2025 fresh copper)

Coordinate convention: metres, Z up, +X = east, +Y = north. Origin = tower axis at
ground level (lawn/plaza level). The tower is 87.5 m to the tip of the gilded finial.
"""
import bpy
import bmesh
import math
import os
import sys
import random
import time
from math import pi, sin, cos, tan, atan, atan2, radians, degrees, sqrt
from mathutils import Vector, Matrix, Euler
from mathutils import noise as mnoise

# ----------------------------------------------------------------------------------
# Options
# ----------------------------------------------------------------------------------
RENDER_ON_RUN = 'auto'    # True / False / 'auto' (auto = render only when run from CLI)
OUT_DIR = os.environ.get('QT_OUT', os.path.join(os.path.expanduser('~'), 'queens_tower_out'))

OPTS = dict(res=(1536, 2048), samples=256, out=None, blend=None, cam='lawn', quick=False,
            render=None, exposure=None, sun_el=None, sun_az=None, patina=False, seed=1893)


def parse_cli():
    argv = sys.argv
    if '--' in argv:
        args = argv[argv.index('--') + 1:]
    elif argv and argv[0].endswith('.py'):
        args = argv[1:]
    else:
        args = []
    i = 0
    while i < len(args):
        a = args[i]
        nxt = lambda k=1: args[i + k]
        if a == '--res':
            OPTS['res'] = (int(nxt()), int(nxt(2))); i += 2
        elif a == '--samples':
            OPTS['samples'] = int(nxt()); i += 1
        elif a == '--out':
            OPTS['out'] = nxt(); i += 1
        elif a == '--blend':
            OPTS['blend'] = nxt(); i += 1
        elif a == '--cam':
            OPTS['cam'] = nxt(); i += 1
        elif a == '--quick':
            OPTS['quick'] = True
        elif a == '--no-render':
            OPTS['render'] = False
        elif a == '--render':
            OPTS['render'] = True
        elif a == '--exposure':
            OPTS['exposure'] = float(nxt()); i += 1
        elif a == '--sun-el':
            OPTS['sun_el'] = float(nxt()); i += 1
        elif a == '--sun-az':
            OPTS['sun_az'] = float(nxt()); i += 1
        elif a == '--patina':
            OPTS['patina'] = True
        elif a == '--seed':
            OPTS['seed'] = int(nxt()); i += 1
        i += 1
    return bool(args)


FROM_CLI = parse_cli()
Q = OPTS['quick']
random.seed(OPTS['seed'])

# ----------------------------------------------------------------------------------
# Scene bootstrap
# ----------------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene
SC.name = 'QueensTower'
SC.unit_settings.system = 'METRIC'
SC.unit_settings.length_unit = 'METERS'

COLS = {}


def collection(name, parent=None):
    if name in COLS:
        return COLS[name]
    c = bpy.data.collections.new(name)
    (parent or SC.collection).children.link(c)
    COLS[name] = c
    return c


COL_TOWER = collection('QueensTower')
COL_STAGE = {k: collection(k, COL_TOWER) for k in
             ['T0_base_steps', 'T1_lower_shaft', 'T2_upper_shaft', 'T3_belfry', 'T4_dome_stage', 'T5_lions']}
COL_SITE = collection('Site')
COL_CTX = collection('Context_buildings')
COL_TREES = collection('Trees')
COL_STUDIO = collection('Studio')

STATS = dict(objects=0)

# ----------------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------------
MATS = {}


def _node(nt, kind, **kw):
    n = nt.nodes.new(kind)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def _principled(mat):
    for n in mat.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            return n
    return None


def _xy_z_projection(nt, coord):
    """(x+y, z) vector so that both ±X and ±Y facing walls receive horizontal courses."""
    sep = _node(nt, 'ShaderNodeSeparateXYZ')
    nt.links.new(coord.outputs['Object'], sep.inputs[0])
    addxy = _node(nt, 'ShaderNodeMath', operation='ADD')
    nt.links.new(sep.outputs['X'], addxy.inputs[0])
    nt.links.new(sep.outputs['Y'], addxy.inputs[1])
    comb = _node(nt, 'ShaderNodeCombineXYZ')
    nt.links.new(addxy.outputs[0], comb.inputs['X'])
    nt.links.new(sep.outputs['Z'], comb.inputs['Y'])
    return comb


def new_mat(name, base=(0.8, 0.8, 0.8), rough=0.6, metal=0.0, **kw):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = _principled(m)
    p.inputs['Base Color'].default_value = (*base, 1.0)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    for k, v in kw.items():
        p.inputs[k].default_value = v
    MATS[name] = m
    return m


def mat_portland(name='M_Portland', tint=(0.74, 0.725, 0.685), dark=(0.54, 0.525, 0.50), block=(1.15, 0.58),
                 rough=0.78, grime=0.35):
    """Portland stone ashlar: large blocks, slight colour variation, AO-driven weathering."""
    m = new_mat(name, tint, rough)
    nt = m.node_tree
    p = _principled(m)
    coord = _node(nt, 'ShaderNodeTexCoord')
    comb = _xy_z_projection(nt, coord)
    brick = _node(nt, 'ShaderNodeTexBrick')
    brick.inputs['Scale'].default_value = 1.0
    brick.inputs['Mortar Size'].default_value = 0.012
    brick.inputs['Mortar Smooth'].default_value = 0.4
    brick.inputs['Bias'].default_value = 0.0
    brick.inputs['Brick Width'].default_value = block[0]
    brick.inputs['Row Height'].default_value = block[1]
    brick.offset = 0.5
    brick.inputs['Color1'].default_value = (*tint, 1)
    brick.inputs['Color2'].default_value = (tint[0] * 0.93, tint[1] * 0.93, tint[2] * 0.92, 1)
    brick.inputs['Mortar'].default_value = (tint[0] * 0.78, tint[1] * 0.77, tint[2] * 0.76, 1)
    nt.links.new(comb.outputs[0], brick.inputs['Vector'])
    noise = _node(nt, 'ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 0.35
    noise.inputs['Detail'].default_value = 3.0
    nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
    ramp = _node(nt, 'ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (dark[0] * 1.15, dark[1] * 1.15, dark[2] * 1.15, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    nt.links.new(noise.outputs['Fac'], ramp.inputs[0])
    mix1 = _node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY')
    mix1.inputs['Factor'].default_value = 0.6
    nt.links.new(brick.outputs['Color'], mix1.inputs[6])
    nt.links.new(ramp.outputs['Color'], mix1.inputs[7])
    ao = _node(nt, 'ShaderNodeAmbientOcclusion')
    ao.inputs['Distance'].default_value = 1.6
    ao.samples = 4
    ao.only_local = True
    aoramp = _node(nt, 'ShaderNodeValToRGB')
    aoramp.color_ramp.elements[0].position = 0.25
    aoramp.color_ramp.elements[0].color = (dark[0] * 0.7, dark[1] * 0.72, dark[2] * 0.7, 1)
    aoramp.color_ramp.elements[1].position = 0.85
    aoramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    nt.links.new(ao.outputs['AO'], aoramp.inputs[0])
    mix2 = _node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY')
    mix2.inputs['Factor'].default_value = grime
    nt.links.new(mix1.outputs[2], mix2.inputs[6])
    nt.links.new(aoramp.outputs['Color'], mix2.inputs[7])
    # vertical rain streaks (noise stretched along Z)
    mp = _node(nt, 'ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (2.5, 2.5, 0.12)
    nt.links.new(coord.outputs['Object'], mp.inputs['Vector'])
    streak = _node(nt, 'ShaderNodeTexNoise')
    streak.inputs['Scale'].default_value = 1.0
    streak.inputs['Detail'].default_value = 4
    nt.links.new(mp.outputs[0], streak.inputs['Vector'])
    sramp = _node(nt, 'ShaderNodeValToRGB')
    sramp.color_ramp.elements[0].position = 0.42
    sramp.color_ramp.elements[0].color = (0.70, 0.70, 0.68, 1)
    sramp.color_ramp.elements[1].position = 0.62
    sramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    nt.links.new(streak.outputs['Fac'], sramp.inputs[0])
    mix3 = _node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY')
    mix3.inputs['Factor'].default_value = 0.55
    nt.links.new(mix2.outputs[2], mix3.inputs[6])
    nt.links.new(sramp.outputs['Color'], mix3.inputs[7])
    nt.links.new(mix3.outputs[2], p.inputs['Base Color'])
    fine = _node(nt, 'ShaderNodeTexNoise')
    fine.inputs['Scale'].default_value = 60.0
    fine.inputs['Detail'].default_value = 2.0
    nt.links.new(coord.outputs['Object'], fine.inputs['Vector'])
    bmath = _node(nt, 'ShaderNodeMath', operation='MULTIPLY_ADD')
    nt.links.new(fine.outputs['Fac'], bmath.inputs[0])
    bmath.inputs[1].default_value = 0.25
    nt.links.new(brick.outputs['Fac'], bmath.inputs[2])
    bump = _node(nt, 'ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.25
    bump.inputs['Distance'].default_value = 0.02
    nt.links.new(bmath.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m


def mat_brick(name='M_RedBrick'):
    m = new_mat(name, (0.46, 0.21, 0.15), 0.85)
    nt = m.node_tree
    p = _principled(m)
    coord = _node(nt, 'ShaderNodeTexCoord')
    comb = _xy_z_projection(nt, coord)
    brick = _node(nt, 'ShaderNodeTexBrick')
    brick.inputs['Scale'].default_value = 1.0
    brick.inputs['Mortar Size'].default_value = 0.010
    brick.inputs['Brick Width'].default_value = 0.225
    brick.inputs['Row Height'].default_value = 0.075
    brick.inputs['Color1'].default_value = (0.42, 0.20, 0.15, 1)
    brick.inputs['Color2'].default_value = (0.33, 0.15, 0.12, 1)
    brick.inputs['Mortar'].default_value = (0.58, 0.54, 0.49, 1)
    nt.links.new(comb.outputs[0], brick.inputs['Vector'])
    nt.links.new(brick.outputs['Color'], p.inputs['Base Color'])
    bump = _node(nt, 'ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.4
    bump.inputs['Distance'].default_value = 0.01
    nt.links.new(brick.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m


def mat_copper(name='M_Copper', patina=False):
    """Fresh copper (dome re-covered 2025, slowly dulling) – or verdigris if patina=True."""
    if patina:
        m = new_mat(name, (0.33, 0.62, 0.53), 0.55, 0.0)
        nt = m.node_tree
        p = _principled(m)
        coord = _node(nt, 'ShaderNodeTexCoord')
        noise = _node(nt, 'ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 1.8
        noise.inputs['Detail'].default_value = 6
        nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
        ramp = _node(nt, 'ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[0].color = (0.22, 0.45, 0.40, 1)
        ramp.color_ramp.elements[1].position = 0.65
        ramp.color_ramp.elements[1].color = (0.42, 0.72, 0.60, 1)
        nt.links.new(noise.outputs['Fac'], ramp.inputs[0])
        nt.links.new(ramp.outputs['Color'], p.inputs['Base Color'])
        return m
    # ~18 months after re-covering: uniform dull chocolate-brown copper with a faint warm sheen
    m = new_mat(name, (0.36, 0.21, 0.14), 0.42, 1.0)
    nt = m.node_tree
    p = _principled(m)
    coord = _node(nt, 'ShaderNodeTexCoord')
    noise = _node(nt, 'ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 1.4
    noise.inputs['Detail'].default_value = 3
    noise.inputs['Roughness'].default_value = 0.5
    nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
    ramp = _node(nt, 'ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0.30, 0.17, 0.12, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (0.42, 0.25, 0.17, 1)
    nt.links.new(noise.outputs['Fac'], ramp.inputs[0])
    nt.links.new(ramp.outputs['Color'], p.inputs['Base Color'])
    rr = _node(nt, 'ShaderNodeMapRange')
    rr.inputs['From Min'].default_value = 0.3
    rr.inputs['From Max'].default_value = 0.7
    rr.inputs['To Min'].default_value = 0.48
    rr.inputs['To Max'].default_value = 0.38
    nt.links.new(noise.outputs['Fac'], rr.inputs['Value'])
    nt.links.new(rr.outputs[0], p.inputs['Roughness'])
    fine = _node(nt, 'ShaderNodeTexNoise')
    fine.inputs['Scale'].default_value = 25
    nt.links.new(coord.outputs['Object'], fine.inputs['Vector'])
    bump = _node(nt, 'ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.08
    nt.links.new(fine.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m


def mat_grass(name='M_Lawn'):
    m = new_mat(name, (0.13, 0.25, 0.07), 0.95)
    nt = m.node_tree
    p = _principled(m)
    coord = _node(nt, 'ShaderNodeTexCoord')
    n1 = _node(nt, 'ShaderNodeTexNoise')
    n1.inputs['Scale'].default_value = 0.25
    n1.inputs['Detail'].default_value = 4
    nt.links.new(coord.outputs['Object'], n1.inputs['Vector'])
    ramp = _node(nt, 'ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0.09, 0.17, 0.04, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.24, 0.33, 0.09, 1)   # November: a little straw
    nt.links.new(n1.outputs['Fac'], ramp.inputs[0])
    nt.links.new(ramp.outputs['Color'], p.inputs['Base Color'])
    n2 = _node(nt, 'ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = 45
    n2.inputs['Detail'].default_value = 8
    n2.inputs['Roughness'].default_value = 0.8
    nt.links.new(coord.outputs['Object'], n2.inputs['Vector'])
    bump = _node(nt, 'ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.6
    bump.inputs['Distance'].default_value = 0.05
    nt.links.new(n2.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m


def mat_paving(name='M_Paving', base=(0.42, 0.40, 0.37), size=(0.9, 0.6), mortar=0.02, rough=0.8):
    m = new_mat(name, base, rough)
    nt = m.node_tree
    p = _principled(m)
    coord = _node(nt, 'ShaderNodeTexCoord')
    brick = _node(nt, 'ShaderNodeTexBrick')
    brick.inputs['Scale'].default_value = 1.0
    brick.inputs['Mortar Size'].default_value = mortar
    brick.inputs['Brick Width'].default_value = size[0]
    brick.inputs['Row Height'].default_value = size[1]
    brick.inputs['Color1'].default_value = (*base, 1)
    brick.inputs['Color2'].default_value = (base[0] * 0.85, base[1] * 0.86, base[2] * 0.88, 1)
    brick.inputs['Mortar'].default_value = (base[0] * 0.6, base[1] * 0.6, base[2] * 0.6, 1)
    nt.links.new(coord.outputs['Object'], brick.inputs['Vector'])
    noise = _node(nt, 'ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 0.4
    nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
    mix = _node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY')
    mix.inputs['Factor'].default_value = 0.45
    nt.links.new(brick.outputs['Color'], mix.inputs[6])
    ramp = _node(nt, 'ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0.6, 0.6, 0.6, 1)
    ramp.color_ramp.elements[1].position = 0.7
    nt.links.new(noise.outputs['Fac'], ramp.inputs[0])
    nt.links.new(ramp.outputs['Color'], mix.inputs[7])
    nt.links.new(mix.outputs[2], p.inputs['Base Color'])
    bump = _node(nt, 'ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.3
    nt.links.new(brick.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m


def mat_facade(name, concrete=(0.62, 0.60, 0.56), glass=(0.03, 0.04, 0.05), bay=(3.2, 3.4), mullion=0.22):
    """1960s grid façade (Sherfield / Library): concrete grid with dark glazing."""
    m = new_mat(name, concrete, 0.5)
    nt = m.node_tree
    p = _principled(m)
    coord = _node(nt, 'ShaderNodeTexCoord')
    comb = _xy_z_projection(nt, coord)
    brick = _node(nt, 'ShaderNodeTexBrick')
    brick.offset = 0.0
    brick.inputs['Scale'].default_value = 1.0
    brick.inputs['Mortar Size'].default_value = mullion
    brick.inputs['Brick Width'].default_value = bay[0]
    brick.inputs['Row Height'].default_value = bay[1]
    brick.inputs['Color1'].default_value = (*glass, 1)
    brick.inputs['Color2'].default_value = (glass[0] * 1.5, glass[1] * 1.5, glass[2] * 1.5, 1)
    brick.inputs['Mortar'].default_value = (*concrete, 1)
    nt.links.new(comb.outputs[0], brick.inputs['Vector'])
    nt.links.new(brick.outputs['Color'], p.inputs['Base Color'])
    rr = _node(nt, 'ShaderNodeMapRange')
    rr.inputs['To Min'].default_value = 0.08
    rr.inputs['To Max'].default_value = 0.7
    nt.links.new(brick.outputs['Fac'], rr.inputs['Value'])
    nt.links.new(rr.outputs[0], p.inputs['Roughness'])
    bump = _node(nt, 'ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.5
    bump.inputs['Distance'].default_value = 0.15
    nt.links.new(brick.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m


def mat_foliage(name='M_Plane_Autumn'):
    m = new_mat(name, (0.45, 0.33, 0.10), 0.8)
    nt = m.node_tree
    p = _principled(m)
    coord = _node(nt, 'ShaderNodeTexCoord')
    n = _node(nt, 'ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = 11.0
    n.inputs['Detail'].default_value = 10
    n.inputs['Roughness'].default_value = 0.85
    nt.links.new(coord.outputs['Object'], n.inputs['Vector'])
    # density varies across the canopy: dense clumps and bare November patches
    dens = _node(nt, 'ShaderNodeTexNoise')
    dens.inputs['Scale'].default_value = 0.6
    dens.inputs['Detail'].default_value = 2
    nt.links.new(coord.outputs['Object'], dens.inputs['Vector'])
    thr = _node(nt, 'ShaderNodeMapRange')
    thr.inputs['From Min'].default_value = 0.3
    thr.inputs['From Max'].default_value = 0.7
    thr.inputs['To Min'].default_value = 0.45
    thr.inputs['To Max'].default_value = 0.56
    nt.links.new(dens.outputs['Fac'], thr.inputs['Value'])
    cmp = _node(nt, 'ShaderNodeMath', operation='GREATER_THAN')
    nt.links.new(n.outputs['Fac'], cmp.inputs[0])
    nt.links.new(thr.outputs[0], cmp.inputs[1])
    nt.links.new(cmp.outputs[0], p.inputs['Alpha'])
    c = _node(nt, 'ShaderNodeTexNoise')
    c.inputs['Scale'].default_value = 0.8
    nt.links.new(coord.outputs['Object'], c.inputs['Vector'])
    cr = _node(nt, 'ShaderNodeValToRGB')
    cr.color_ramp.elements[0].position = 0.35
    cr.color_ramp.elements[0].color = (0.30, 0.30, 0.07, 1)   # olive green leaves still on
    cr.color_ramp.elements[1].position = 0.7
    cr.color_ramp.elements[1].color = (0.62, 0.36, 0.09, 1)   # ochre / rust
    nt.links.new(c.outputs['Fac'], cr.inputs[0])
    nt.links.new(cr.outputs['Color'], p.inputs['Base Color'])
    return m


def build_materials():
    mat_portland()
    mat_portland('M_Portland_Base', tint=(0.70, 0.68, 0.64), dark=(0.50, 0.49, 0.46), block=(1.4, 0.7), grime=0.5)
    mat_portland('M_Lion', tint=(0.46, 0.44, 0.41), dark=(0.26, 0.25, 0.24), block=(8, 8), grime=0.8)
    mat_brick()
    mat_copper('M_Copper', patina=OPTS['patina'])
    mat_copper('M_Copper_fresh', patina=False)
    mat_copper('M_Copper_verdigris', patina=True)
    new_mat('M_Gold', (1.0, 0.76, 0.33), 0.22, 1.0)
    new_mat('M_Glass', (0.02, 0.03, 0.035), 0.06, 0.0)
    _principled(MATS['M_Glass']).inputs['IOR'].default_value = 1.6
    new_mat('M_Timber', (0.21, 0.16, 0.12), 0.75)
    new_mat('M_Door', (0.16, 0.10, 0.06), 0.55)
    new_mat('M_Iron', (0.05, 0.05, 0.055), 0.45, 0.6)
    new_mat('M_Bronze', (0.45, 0.33, 0.18), 0.4, 1.0)
    new_mat('M_Inscription', (0.30, 0.28, 0.25), 0.9)
    new_mat('M_Asphalt', (0.07, 0.07, 0.075), 0.92)
    new_mat('M_Kerb', (0.55, 0.53, 0.50), 0.8)
    new_mat('M_Bark', (0.30, 0.26, 0.22), 0.9)
    new_mat('M_Soil', (0.14, 0.10, 0.07), 0.95)
    new_mat('M_Bench', (0.25, 0.17, 0.10), 0.6)
    mat_grass()
    mat_paving('M_Paving', (0.46, 0.44, 0.41), (0.9, 0.6), 0.02)
    mat_paving('M_Setts', (0.36, 0.35, 0.34), (0.2, 0.1), 0.012, 0.75)
    mat_paving('M_York', (0.52, 0.49, 0.44), (1.2, 0.75), 0.015)
    mat_facade('M_Sherfield', (0.74, 0.72, 0.68), (0.04, 0.05, 0.06), (2.6, 3.5), 0.6)
    mat_facade('M_Library', (0.62, 0.60, 0.57), (0.03, 0.035, 0.04), (1.6, 3.4), 0.35)
    mat_facade('M_Chem', (0.58, 0.52, 0.45), (0.03, 0.03, 0.03), (2.4, 3.8), 0.5)
    mat_facade('M_RSM', (0.70, 0.64, 0.55), (0.03, 0.03, 0.03), (2.0, 4.2), 1.0)
    mat_foliage()


# ----------------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------------
def M(name):
    return MATS[name]


def _finish_mesh(me, smooth, sharp_angle):
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if smooth and sharp_angle is not None:
        thr = radians(sharp_angle)
        for e in bm.edges:
            if len(e.link_faces) == 2:
                try:
                    if e.calc_face_angle() > thr:
                        e.smooth = False
                except ValueError:
                    pass
            else:
                e.smooth = False
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    me.update()


def obj_from_pydata(name, verts, faces, mat=None, col=None, smooth=False, sharp_angle=30.0, loc=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    _finish_mesh(me, smooth, sharp_angle)
    if mat is not None:
        me.materials.append(mat if isinstance(mat, bpy.types.Material) else M(mat))
    ob = bpy.data.objects.new(name, me)
    (col or COL_TOWER).objects.link(ob)
    if loc is not None:
        ob.location = loc
    STATS['objects'] += 1
    return ob


def link_dup(src, name, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), col=None):
    ob = bpy.data.objects.new(name, src.data)
    ob.location = loc
    ob.rotation_euler = rot
    ob.scale = scale
    (col or src.users_collection[0]).objects.link(ob)
    STATS['objects'] += 1
    return ob


def rot_z(ob, theta):
    """Rotate an object about the world Z axis (through the origin), keeping its own transform."""
    base = Matrix.Translation(ob.location) @ ob.rotation_euler.to_matrix().to_4x4() @ Matrix.Diagonal((*ob.scale, 1.0))
    ob.matrix_world = Matrix.Rotation(theta, 4, 'Z') @ base
    return ob


def box(name, size, center, mat=None, col=None, rot=(0, 0, 0)):
    sx, sy, sz = size
    cx, cy, cz = center
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
         (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ob = obj_from_pydata(name, v, f, mat, col, loc=(cx, cy, cz))
    ob.rotation_euler = rot
    return ob


def ngon_pts(n, apothem, rot=None):
    """Regular n-gon; with the default rotation the flats are aligned to the axes."""
    if rot is None:
        rot = pi / n
    R = apothem / cos(pi / n)
    return [(R * cos(rot + 2 * pi * i / n), R * sin(rot + 2 * pi * i / n)) for i in range(n)]


def prism(name, pts, z0, z1, mat=None, col=None, cx=0.0, cy=0.0, smooth=False):
    n = len(pts)
    verts = [(cx + x, cy + y, z0) for x, y in pts] + [(cx + x, cy + y, z1) for x, y in pts]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return obj_from_pydata(name, verts, faces, mat, col, smooth=smooth, sharp_angle=40)


def cylinder(name, r, z0, z1, mat=None, col=None, cx=0.0, cy=0.0, segs=None, r2=None):
    segs = segs or (24 if Q else 48)
    r2 = r if r2 is None else r2
    pts0 = [(r * cos(2 * pi * i / segs), r * sin(2 * pi * i / segs)) for i in range(segs)]
    pts1 = [(r2 * cos(2 * pi * i / segs), r2 * sin(2 * pi * i / segs)) for i in range(segs)]
    verts = [(cx + x, cy + y, z0) for x, y in pts0] + [(cx + x, cy + y, z1) for x, y in pts1]
    n = segs
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return obj_from_pydata(name, verts, faces, mat, col, smooth=True, sharp_angle=40)


def lathe(name, profile, mat=None, col=None, segs=None, cx=0.0, cy=0.0, smooth=True, sharp=40.0):
    """Revolve a (r, z) profile (bottom→top) around the local Z axis. r=0 makes a pole."""
    segs = segs or (24 if Q else 48)
    prof = []
    for r, z in profile:
        if prof and abs(prof[-1][0] - r) < 1e-6 and abs(prof[-1][1] - z) < 1e-6:
            continue
        prof.append((r, z))
    verts, faces, rows = [], [], []
    for r, z in prof:
        if abs(r) < 1e-6:
            verts.append((cx, cy, z))
            rows.append(('pole', len(verts) - 1))
        else:
            base = len(verts)
            for i in range(segs):
                a = 2 * pi * i / segs
                verts.append((cx + r * cos(a), cy + r * sin(a), z))
            rows.append(('ring', base))
    for k in range(len(rows) - 1):
        ta, a = rows[k]
        tb, b = rows[k + 1]
        if ta == 'ring' and tb == 'ring':
            for i in range(segs):
                j = (i + 1) % segs
                faces.append((a + i, a + j, b + j, b + i))
        elif ta == 'pole' and tb == 'ring':
            for i in range(segs):
                j = (i + 1) % segs
                faces.append((a, b + i, b + j))
        elif ta == 'ring' and tb == 'pole':
            for i in range(segs):
                j = (i + 1) % segs
                faces.append((a + j, a + i, b))
    if rows[0][0] == 'ring':
        faces.append(tuple(range(rows[0][1] + segs - 1, rows[0][1] - 1, -1)))
    if rows[-1][0] == 'ring':
        faces.append(tuple(range(rows[-1][1], rows[-1][1] + segs)))
    return obj_from_pydata(name, verts, faces, mat, col, smooth=smooth, sharp_angle=sharp)


def sweep_ngon(name, profile, n, apothem, z0, mat=None, col=None, cx=0.0, cy=0.0, rot=None):
    """Sweep a moulding profile [(d, z), ...] (d = outward offset from the apothem) around a regular
    n-gon. Produces a closed ring solid with mitred corners."""
    rows = []
    for d, z in profile:
        rows.append([(cx + x, cy + y, z0 + z) for x, y in ngon_pts(n, apothem + d, rot)])
    verts, faces = [], []
    for row in rows:
        verts.extend(row)
    m = len(rows)
    for k in range(m - 1):
        for i in range(n):
            j = (i + 1) % n
            faces.append((k * n + i, k * n + j, (k + 1) * n + j, (k + 1) * n + i))
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range((m - 1) * n, m * n)))
    return obj_from_pydata(name, verts, faces, mat, col, smooth=False)


def sweep_square(name, profile, half, z0, mat=None, col=None, cx=0.0, cy=0.0):
    return sweep_ngon(name, profile, 4, half, z0, mat, col, cx, cy)


def sweep_rect_along(name, pts, w, h, mat=None, col=None, up=Vector((0, 0, 1)), smooth=True):
    """Extrude a w×h rectangle along a 3D polyline (frames from the given up vector)."""
    P = [Vector(p) for p in pts]
    n = len(P)
    verts, faces = [], []
    for i in range(n):
        if i == 0:
            t = (P[1] - P[0]).normalized()
        elif i == n - 1:
            t = (P[-1] - P[-2]).normalized()
        else:
            t = ((P[i + 1] - P[i]).normalized() + (P[i] - P[i - 1]).normalized()).normalized()
        u = up
        if abs(t.dot(u)) > 0.95:
            u = Vector((1, 0, 0))
        s = t.cross(u).normalized()
        nrm = s.cross(t).normalized()
        c = P[i]
        verts += [c - s * w / 2 - nrm * h / 2, c + s * w / 2 - nrm * h / 2,
                  c + s * w / 2 + nrm * h / 2, c - s * w / 2 + nrm * h / 2]
    for i in range(n - 1):
        a = 4 * i
        b = 4 * (i + 1)
        for k in range(4):
            k2 = (k + 1) % 4
            faces.append((a + k, a + k2, b + k2, b + k))
    faces.append((3, 2, 1, 0))
    e = 4 * (n - 1)
    faces.append((e, e + 1, e + 2, e + 3))
    return obj_from_pydata(name, verts, faces, mat, col, smooth=smooth, sharp_angle=35)


def arch_outline(w, h, off=0.0, n=None):
    """Round-arched opening outline (u horizontal, v vertical, v=0 at the sill): bottom-left, up,
    over the arch, down to bottom-right. 'off' offsets the outline outward."""
    n = n or (10 if Q else 18)
    r = w / 2 + off
    spring = h - w / 2
    pts = [(-r, 0.0), (-r, spring)]
    for i in range(1, n):
        a = pi - pi * i / n
        pts.append((r * cos(a), spring + r * sin(a)))
    pts += [(r, spring), (r, 0.0)]
    return pts


def face_angle(face):
    """Rotation about Z that takes the SOUTH-face template (outward normal -Y) to face
    0=S(-Y), 1=E(+X), 2=N(+Y), 3=W(-X)."""
    return face * pi / 2


def arch_cutter(name, w, h, depth, y_face, z0, x=0.0):
    """Prism shaped like a round-arched opening, cutting 'depth' into a wall whose outer plane is
    y = -y_face (south-face template); protrudes 0.3 m outside the wall."""
    o = arch_outline(w, h)
    pts = [(x + u, v) for u, v in o]
    y_out = -y_face - 0.3
    y_in = -y_face + depth
    n = len(pts)
    verts = [(u, y_out, z0 + v) for u, v in pts] + [(u, y_in, z0 + v) for u, v in pts]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((j, i, n + i, n + j))
    return obj_from_pydata(name, verts, faces, None, COL_STUDIO)


def rect_cutter(name, w, h, depth, y_face, z0, x=0.0):
    return box(name, (w, depth + 0.3, h), (x, -y_face + (depth - 0.3) / 2, z0 + h / 2), None, COL_STUDIO)


def boolean_cut(target, cutters):
    """Difference boolean (exact) of target by a list of cutter objects, applied immediately."""
    if not cutters:
        return target
    bpy.context.view_layer.update()
    bm = bmesh.new()
    for c in cutters:
        tmp = c.data.copy()
        tmp.transform(c.matrix_world)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    me = bpy.data.meshes.new(target.name + '_cut')
    bm.to_mesh(me)
    bm.free()
    cut = bpy.data.objects.new(target.name + '_cut', me)
    COL_STUDIO.objects.link(cut)
    mod = target.modifiers.new('cut', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cut
    apply_modifiers(target)
    bpy.data.objects.remove(cut)
    bpy.data.meshes.remove(me)
    for c in cutters:
        md = c.data
        bpy.data.objects.remove(c)
        if md.users == 0:
            bpy.data.meshes.remove(md)
    return target


def apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ob_eval = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ob_eval)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    me.name = old.name
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return ob


def arch_surround(name, w, h, band, thick, y_face, z0, mat='M_Portland', x=0.0, col=None, proud=0.0):
    """Moulded archivolt + jambs around an opening on the south-face template. Sits on the wall
    plane (y = -y_face) and projects 'thick' outward."""
    inner = arch_outline(w, h, 0.0)
    outer = arch_outline(w, h, band)
    n = len(inner)
    yA = -y_face - proud
    yB = yA - thick
    verts = []
    for u, v in inner:
        verts.append((x + u, yA, z0 + v))
    for u, v in outer:
        verts.append((x + u, yA, z0 + v))
    for u, v in inner:
        verts.append((x + u, yB, z0 + v))
    for u, v in outer:
        verts.append((x + u, yB, z0 + v))
    I0, O0, I1, O1 = 0, n, 2 * n, 3 * n
    faces = []
    for i in range(n - 1):
        faces.append((O1 + i, O1 + i + 1, I1 + i + 1, I1 + i))
        faces.append((I0 + i, I0 + i + 1, O0 + i + 1, O0 + i))
        faces.append((I1 + i, I1 + i + 1, I0 + i + 1, I0 + i))
        faces.append((O0 + i, O0 + i + 1, O1 + i + 1, O1 + i))
    faces.append((I0, O0, O1, I1))
    faces.append((I1 + n - 1, O1 + n - 1, O0 + n - 1, I0 + n - 1))
    return obj_from_pydata(name, verts, faces, mat, col, smooth=True, sharp_angle=35)


def baluster_profile(h=0.82):
    p = [(0.0, 0.0), (0.075, 0.0), (0.075, 0.05), (0.055, 0.06), (0.055, 0.10), (0.075, 0.12),
         (0.085, 0.18), (0.083, 0.26), (0.078, 0.34), (0.062, 0.42), (0.050, 0.50),
         (0.045, 0.58), (0.050, 0.64), (0.068, 0.68), (0.07, 0.72), (0.058, 0.74), (0.072, 0.77),
         (0.072, 0.80), (0.0, 0.80)]
    return [(r, z / 0.80 * h) for r, z in p]


_BALUSTER = {}


def balustrade(name, corners, z0, height=1.08, spacing=0.36, rail_w=0.26, mat='M_Portland', col=None,
               pedestal=0.42):
    """Stone balustrade along a closed polygon (corners in order, XY). Linked-duplicate balusters."""
    key = round(height, 2)
    if key not in _BALUSTER:
        src = lathe('baluster_src_%s' % key, baluster_profile(height - 0.26), mat, COL_STUDIO,
                    segs=10 if Q else 14)
        _BALUSTER[key] = src
    src = _BALUSTER[key]
    col = col or COL_TOWER
    k = 0
    for i in range(len(corners)):
        a = Vector((*corners[i], 0))
        b = Vector((*corners[(i + 1) % len(corners)], 0))
        d = b - a
        L = d.length
        dn = d / L
        ang = atan2(dn.y, dn.x)
        mid = (a + b) / 2
        box('%s_plinth_%d' % (name, i), (L + rail_w, rail_w, 0.14), (mid.x, mid.y, z0 + 0.07), mat, col, rot=(0, 0, ang))
        box('%s_coping_%d' % (name, i), (L + rail_w, rail_w + 0.04, 0.12), (mid.x, mid.y, z0 + height - 0.06), mat, col,
            rot=(0, 0, ang))
        box('%s_ped_%d' % (name, i), (pedestal, pedestal, height + 0.12), (a.x, a.y, z0 + (height + 0.12) / 2), mat, col)
        usable = L - pedestal
        nb = max(1, int(usable / spacing))
        step = usable / nb
        for j in range(nb):
            s = pedestal / 2 + step * (j + 0.5)
            p = a + dn * s
            link_dup(src, '%s_b%d' % (name, k), (p.x, p.y, z0 + 0.14), col=col)
            k += 1
    return k


def column(name, r, z0, z1, mat='M_Portland', col=None, cx=0.0, cy=0.0):
    """Simple classical column: moulded base, shaft with entasis, capital."""
    H = z1 - z0
    s = r / 0.3
    base_h = 0.30 * s
    prof = [(0, 0), (r * 1.55, 0), (r * 1.55, 0.06 * s), (r * 1.3, 0.10 * s), (r * 1.18, 0.16 * s), (r * 1.02, 0.26 * s),
            (r, base_h)]
    cap_h = 0.44 * s
    shaft1 = H - cap_h - 0.04
    prof += [(r, base_h + (shaft1 - base_h) * 0.33), (r * 0.9, shaft1 - 0.04), (r * 0.95, shaft1)]
    prof += [(r * 1.05, shaft1 + 0.08 * s), (r * 1.25, shaft1 + 0.22 * s), (r * 1.45, shaft1 + 0.36 * s),
             (r * 1.55, H - 0.02), (r * 1.6, H), (0, H)]
    prof = [(a, z0 + b) for a, b in prof]
    return lathe(name, prof, mat, col, segs=14 if Q else 24, cx=cx, cy=cy)


def cornice_profile(h, proj, kind='classical'):
    """(d, z) moulding profile from the wall (d=0) at z=0 up to the top, back to d=0 at z=h."""
    if kind == 'classical':
        return [(0, 0), (proj * 0.18, 0), (proj * 0.18, h * 0.12), (proj * 0.30, h * 0.18), (proj * 0.30, h * 0.30),
                (proj * 0.48, h * 0.36), (proj * 0.55, h * 0.46), (proj * 0.55, h * 0.56), (proj * 0.80, h * 0.62),
                (proj * 0.95, h * 0.82), (proj, h * 0.9), (proj, h), (0, h)]
    if kind == 'string':
        return [(0, 0), (proj * 0.4, 0), (proj * 0.7, h * 0.3), (proj, h * 0.75), (proj, h), (0, h)]
    if kind == 'plinth':
        return [(0, 0), (proj, 0), (proj, h * 0.55), (proj * 0.7, h * 0.65), (proj * 0.45, h * 0.8), (proj * 0.2, h * 0.9),
                (0, h)]
    if kind == 'cyma':
        return [(0, 0), (proj * 0.25, 0), (proj * 0.25, h * 0.25), (proj * 0.5, h * 0.4), (proj * 0.85, h * 0.7),
                (proj, h * 0.9), (proj, h), (0, h)]
    raise ValueError(kind)


def face_template(objs, face):
    """Rotate a list of south-face template objects to the given tower face."""
    th = face_angle(face)
    for o in objs:
        if th:
            rot_z(o, th)
        o.name = '%s_%s' % (o.name, 'SENW'[face])
    return objs


# ----------------------------------------------------------------------------------
# Tower dimensions (metres, cumulative heights)
# ----------------------------------------------------------------------------------
STEP_N = 9
STEP_RISE = 0.165
STEP_TREAD = 0.42
Z_TERRACE = STEP_N * STEP_RISE            # 1.485
H1 = 6.35          # half-width of the lower shaft (12.7 m square)
TERRACE_W = 3.6    # terrace width around the plinth
PLINTH_H = 1.1
Z_SHAFT0 = Z_TERRACE + PLINTH_H           # ~2.6
Z_BALC1 = 32.6     # first balustraded balcony floor (top of stage 1)
H2 = 5.95          # upper shaft half-width
Z_BALC2 = 45.6     # second balcony (top of stage 2)
H3 = 5.60          # belfry half-width
Z_BALC3 = 59.6     # third balcony = viewing gallery at the base of the dome stage (324 steps)
OCT_A = 4.9        # octagonal drum apothem (drum nearly as wide as the belfry stage)
Z_DRUM_TOP = 68.4  # top of the drum cornice
DOME_R = 5.3
Z_DOME0 = 68.7     # dome springing
Z_DOME_TOP = 75.9  # dome meets the lantern seat
Z_LANTERN_TOP = 83.2
Z_FINIAL_TOP = 87.5
BAL_H = 1.1


def _catmull_rom(pts, n):
    """Centripetal-ish Catmull-Rom through (t, r) control points → n+1 samples."""
    P = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    segs = len(pts) - 1
    for i in range(n + 1):
        u = i / n * segs
        k = min(int(u), segs - 1)
        s = u - k
        p0, p1, p2, p3 = P[k], P[k + 1], P[k + 2], P[k + 3]
        a = [(-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * 0.5 for j in range(2)]
        b = [(2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * 0.5 for j in range(2)]
        c = [(-p0[j] + p2[j]) * 0.5 for j in range(2)]
        d = [p1[j] for j in range(2)]
        out.append(tuple(((a[j] * s + b[j]) * s + c[j]) * s + d[j] for j in range(2)))
    return out


def build_base_steps():
    col = COL_STAGE['T0_base_steps']
    base_half = H1 + 0.45 + TERRACE_W
    prof = [(0, 0)]
    for i in range(STEP_N):
        d_out = STEP_N * STEP_TREAD - i * STEP_TREAD
        prof.append((d_out, i * STEP_RISE))
        prof.append((d_out, (i + 1) * STEP_RISE))
    prof.append((0, Z_TERRACE))
    sweep_square('steps', prof, base_half, 0.0, 'M_Portland_Base', col)
    prism('terrace', ngon_pts(4, base_half), Z_TERRACE - 0.02, Z_TERRACE + 0.01, 'M_York', col)
    sweep_square('plinth_course', cornice_profile(PLINTH_H, 0.45, 'plinth'), H1, Z_TERRACE, 'M_Portland_Base', col)
    return base_half


def brick_bands(col, half, z_from, z_to, period=2.6, band_h=0.165, gaps=(), faces=(0, 1, 2, 3)):
    """Thin red-brick bands (12 mm proud) on each face; 'gaps' = list of (x0, x1) to leave out."""
    z = z_from
    k = 0
    depth = 0.03
    while z + band_h < z_to:
        segs = [(-half - 0.012, half + 0.012)]
        for g0, g1 in gaps:
            new = []
            for a, b in segs:
                if g1 <= a or g0 >= b:
                    new.append((a, b))
                else:
                    if a < g0:
                        new.append((a, g0))
                    if g1 < b:
                        new.append((g1, b))
            segs = new
        for f in faces:
            objs = []
            for a, b in segs:
                objs.append(box('band%d' % k, (b - a, depth, band_h), ((a + b) / 2, -half - 0.006, z + band_h / 2), 'M_RedBrick', col))
            face_template(objs, f)
        z += period
        k += 1


def stage1_lower_shaft():
    """Plain lower shaft (the part rebuilt 1966-68 plus the original shaft above): one modest
    round-arched doorway on the south, slit windows, two string courses, thin brick bands, and a
    single arched window per face under the first gallery."""
    col = COL_STAGE['T1_lower_shaft']
    z0, z1 = Z_SHAFT0, Z_BALC1
    shaft = prism('shaft1', ngon_pts(4, H1), z0, z1 - 0.9, 'M_Portland', col)
    ARCH_W, ARCH_H, ARCH_Z = 2.4, 5.4, Z_SHAFT0 + 0.3
    SLITS = [(-1.6, 12.2), (1.6, 12.2), (-1.6, 19.4), (1.6, 19.4)]       # (x, z_bottom), 0.6 × 2.4
    SLIT_W, SLIT_H = 0.6, 2.4
    TOP_Z, TOP_W, TOP_H = 25.0, 1.5, 5.2                                 # arched window under gallery 1
    cutters = []
    for f in range(4):
        c = []
        if f == 0:
            c.append(arch_cutter('cut_arch1', ARCH_W, ARCH_H, 1.2, H1, ARCH_Z))
        else:
            c.append(rect_cutter('cut_base_w', 0.9, 1.4, 0.8, H1, Z_SHAFT0 + 3.2))
        for (wx, wz) in SLITS:
            c.append(rect_cutter('cut_slit', SLIT_W, SLIT_H, 0.8, H1, wz, wx))
        c.append(arch_cutter('cut_top', TOP_W, TOP_H, 0.9, H1, TOP_Z))
        cutters += face_template(c, f)
    boolean_cut(shaft, cutters)
    for f in range(4):
        g = []
        if f == 0:
            g.append(arch_surround('arch1_surround', ARCH_W, ARCH_H, 0.34, 0.16, H1, ARCH_Z, 'M_Portland_Base', col=col))
            g.append(box('arch1_key', (0.42, 0.3, 0.75), (0, -H1 - 0.22, ARCH_Z + ARCH_H - 0.12), 'M_Portland_Base', col))
            g.append(box('door', (2.3, 0.12, 3.6), (0, -H1 + 1.15, ARCH_Z + 1.8), 'M_Door', col))
            g.append(box('door_fan', (2.3, 0.06, 1.9), (0, -H1 + 1.15, ARCH_Z + 3.6 + 0.85), 'M_Glass', col))
            for i in range(-2, 3):
                g.append(box('door_mull%d' % i, (0.06, 0.08, 1.8), (i * 0.46, -H1 + 1.1, ARCH_Z + 4.4), 'M_Iron', col))
            g.append(box('door_rail', (2.3, 0.08, 0.12), (0, -H1 + 1.1, ARCH_Z + 3.6), 'M_Iron', col))
            # a flight of steps from the terrace up to the door sill
            nst = 8
            rise = (ARCH_Z - Z_TERRACE) / nst
            tread = 0.3
            for k in range(nst):
                depth = (nst - k) * tread + 0.45
                g.append(box('door_step%d' % k, (3.6, depth, rise), (0, -H1 - depth / 2, Z_TERRACE + rise * (k + 0.5)),
                             'M_Portland_Base', col))
            for sx in (-1, 1):
                g.append(box('door_cheek%s' % ('L' if sx < 0 else 'R'), (0.35, nst * tread + 0.6, ARCH_Z - Z_TERRACE + 0.25),
                             (sx * 1.95, -H1 - (nst * tread + 0.6) / 2, Z_TERRACE + (ARCH_Z - Z_TERRACE + 0.25) / 2), 'M_Portland_Base', col))
        else:
            g.append(box('base_w_glass', (0.85, 0.05, 1.35), (0, -H1 + 0.6, Z_SHAFT0 + 3.2 + 0.7), 'M_Glass', col))
            g.append(box('base_w_sill', (1.2, 0.3, 0.1), (0, -H1 - 0.05, Z_SHAFT0 + 3.15), 'M_Portland', col))
        for (wx, wz) in SLITS:
            g.append(box('slit_glass', (SLIT_W - 0.05, 0.05, SLIT_H - 0.05), (wx, -H1 + 0.6, wz + SLIT_H / 2), 'M_Glass', col))
            g.append(box('slit_sill', (SLIT_W + 0.3, 0.26, 0.1), (wx, -H1 - 0.04, wz - 0.05), 'M_Portland', col))
        g.append(arch_surround('top_surround', TOP_W, TOP_H, 0.2, 0.12, H1, TOP_Z, col=col))
        g.append(box('top_glass', (TOP_W - 0.1, 0.05, TOP_H - 0.4), (0, -H1 + 0.7, TOP_Z + TOP_H / 2 - 0.2), 'M_Glass', col))
        g.append(box('top_mull', (0.06, 0.08, TOP_H - 0.4), (0, -H1 + 0.6, TOP_Z + TOP_H / 2 - 0.2), 'M_Iron', col))
        for k in range(1, 4):
            g.append(box('top_tr%d' % k, (TOP_W - 0.1, 0.08, 0.06), (0, -H1 + 0.6, TOP_Z + k * 1.2), 'M_Iron', col))
        g.append(box('top_sill', (TOP_W + 0.6, 0.34, 0.2), (0, -H1 - 0.1, TOP_Z - 0.1), 'M_Portland', col))
        face_template(g, f)
    sweep_square('string1a', cornice_profile(0.35, 0.18, 'string'), H1, 10.6, 'M_Portland', col)
    sweep_square('string1b', cornice_profile(0.35, 0.18, 'string'), H1, 23.4, 'M_Portland', col)
    # thin red brick bands: interrupted by the doorway low down, by the slits higher up
    brick_bands(col, H1, Z_SHAFT0 + 1.6, 10.4, gaps=[(-ARCH_W / 2 - 0.45, ARCH_W / 2 + 0.45), (-0.7, 0.7)])
    brick_bands(col, H1, 11.4, 23.2, gaps=[(-2.05, -1.15), (1.15, 2.05)])
    sweep_square('cornice1', cornice_profile(0.9, 0.85, 'classical'), H1, z1 - 0.9, 'M_Portland', col)
    hb = H1 + 0.85 + 0.15
    prism('balc1_slab', ngon_pts(4, hb), z1 - 0.05, z1 + 0.08, 'M_Portland', col)
    balustrade('balc1', ngon_pts(4, hb - 0.2), z1 + 0.08, BAL_H, 0.36, col=col)


def stage2_upper_shaft():
    col = COL_STAGE['T2_upper_shaft']
    z0, z1 = Z_BALC1 + 0.08, Z_BALC2
    shaft = prism('shaft2', ngon_pts(4, H2), z0, z1 - 0.8, 'M_Portland', col)
    W2, H2W, Z2 = 1.7, 7.2, z0 + 2.0
    Z_OC = z0 + 10.9
    cutters = []
    for f in range(4):
        c = [arch_cutter('cut_w2', W2, H2W, 0.9, H2, Z2, wx) for wx in (-1.55, 1.55)]
        oc = cylinder('cut_oculus', 0.7, -H2 - 0.3, -H2 + 0.8, None, COL_STUDIO, 0, 0, 24)
        oc.rotation_euler = (-pi / 2, 0, 0)
        oc.location = (0, 0, Z_OC)
        c.append(oc)
        cutters += face_template(c, f)
    boolean_cut(shaft, cutters)
    for f in range(4):
        g = []
        for wx in (-1.55, 1.55):
            g.append(arch_surround('w2_surround', W2, H2W, 0.22, 0.14, H2, Z2, col=col, x=wx))
            g.append(box('w2_glass', (1.6, 0.05, 6.8), (wx, -H2 + 0.7, Z2 + 3.4), 'M_Glass', col))
            g.append(box('w2_mull', (0.07, 0.09, 6.8), (wx, -H2 + 0.6, Z2 + 3.4), 'M_Iron', col))
            for k in range(1, 6):
                g.append(box('w2_tr%d' % k, (1.6, 0.09, 0.06), (wx, -H2 + 0.6, Z2 + k * 1.15), 'M_Iron', col))
        g.append(column('w2_col', 0.19, Z2, Z2 + H2W - 0.85, col=col, cx=0, cy=-H2 - 0.1))
        g.append(box('w2_sill', (5.0, 0.36, 0.22), (0, -H2 - 0.1, Z2 - 0.1), 'M_Portland', col))
        g.append(lathe('oculus_ring', [(0.7, 0), (0.95, 0), (0.95, 0.12), (0.7, 0.12)], 'M_Portland', col, segs=24))
        g[-1].rotation_euler = (-pi / 2, 0, 0)
        g[-1].location = (0, -H2 - 0.02, Z_OC)
        g.append(box('oculus_glass', (1.3, 0.05, 1.3), (0, -H2 + 0.6, Z_OC), 'M_Glass', col))
        for sx in (-1, 1):
            g.append(box('pil2', (0.55, 0.14, z1 - 0.8 - z0), (sx * (H2 - 0.275), -H2 - 0.07, (z0 + z1 - 0.8) / 2), 'M_Portland', col))
        face_template(g, f)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * (H2 - 0.1), sy * (H2 - 0.1)
            prism('corner2_%d%d' % (sx, sy), ngon_pts(8, 0.42), z0, z1 - 0.8, 'M_Portland', col, cx, cy)
            lathe('corner2cap_%d%d' % (sx, sy), [(0.52, z1 - 0.8), (0.52, z1 - 0.6), (0.4, z1 - 0.3), (0.2, z1 - 0.05), (0, z1 + 0.05)],
                  'M_Portland', col, segs=16, cx=cx, cy=cy)
    brick_bands(col, H2, z0 + 0.5, z0 + 1.9, period=1.0, band_h=0.2)
    sweep_square('string2', cornice_profile(0.3, 0.16, 'string'), H2, Z2 + H2W + 0.4, 'M_Portland', col)
    sweep_square('cornice2', cornice_profile(0.8, 0.8, 'classical'), H2, z1 - 0.8, 'M_Portland', col)
    hb = H2 + 0.8 + 0.15
    prism('balc2_slab', ngon_pts(4, hb), z1 - 0.05, z1 + 0.08, 'M_Portland', col)
    balustrade('balc2', ngon_pts(4, hb - 0.2), z1 + 0.08, BAL_H, 0.36, col=col)


def louvres(name, w, h, y_face, z0, col, x=0.0, pitch=0.34, mat='M_Timber'):
    """Slanted timber louvre boards filling an arched belfry opening (south-face template)."""
    objs = []
    n = int(h / pitch)
    spring = h - w / 2
    for i in range(n):
        z = z0 + 0.2 + i * pitch
        vv = z - z0
        ww = w if vv < spring else 2 * sqrt(max(0.0, (w / 2) ** 2 - (vv - spring) ** 2))
        if ww < 0.2:
            break
        b = box('%s_%d' % (name, i), (ww - 0.05, 0.05, 0.40), (x, -y_face + 0.7, z), mat, col)
        b.rotation_euler = (radians(35), 0, 0)
        objs.append(b)
    return objs


def stage3_belfry():
    col = COL_STAGE['T3_belfry']
    z0, z1 = Z_BALC2 + 0.08, Z_BALC3
    shaft = prism('shaft3', ngon_pts(4, H3), z0, z1 - 1.0, 'M_Portland', col)
    W_B, H_B, Z_B = 2.15, 9.3, z0 + 1.7
    cutters = []
    for f in range(4):
        cutters += face_template([arch_cutter('cut_bell', W_B, H_B, 1.6, H3, Z_B, wx) for wx in (-1.6, 1.6)], f)
    boolean_cut(shaft, cutters)
    for f in range(4):
        g = []
        for wx in (-1.6, 1.6):
            g.append(arch_surround('bell_surround', W_B, H_B, 0.28, 0.18, H3, Z_B, col=col, x=wx))
            g += louvres('louvre', W_B, H_B, H3, Z_B, col, x=wx)
            g.append(box('bell_rail', (W_B + 0.3, 0.05, 0.9), (wx, -H3 - 0.15, Z_B + 0.5), 'M_Iron', col))
        for cx in (-H3 + 0.5, 0.0, H3 - 0.5):
            g.append(column('bell_col', 0.26, Z_B, Z_B + H_B + 0.2, col=col, cx=cx, cy=-H3 - 0.35))
        g.append(box('bell_sill', (2 * H3, 0.5, 0.3), (0, -H3 - 0.15, Z_B - 0.15), 'M_Portland', col))
        face_template(g, f)
    sweep_square('entab3', [(0, 0), (0.62, 0), (0.62, 0.55), (0.7, 0.6), (0.7, 1.0), (0, 1.0)], H3, Z_B + H_B + 0.2, 'M_Portland', col)
    sweep_square('cornice3', cornice_profile(1.0, 1.05, 'classical'), H3, z1 - 1.0, 'M_Portland', col)
    hb = H3 + 1.05 + 0.15
    prism('balc3_slab', ngon_pts(4, hb), z1 - 0.05, z1 + 0.08, 'M_Portland', col)
    balustrade('balc3', ngon_pts(4, hb - 0.2), z1 + 0.08, BAL_H, 0.36, col=col)
    # the Alexandra Peal – a hint of bronze visible through the louvres
    for i in range(5):
        a = 2 * pi * i / 5
        b = lathe('bell_%d' % i, [(0, 0), (0.25, 0), (0.3, 0.1), (0.45, 0.45), (0.62, 0.95), (0.68, 1.05), (0.55, 1.1), (0.0, 1.1)],
                  'M_Bronze', col, segs=20, cx=1.6 * cos(a), cy=1.6 * sin(a))
        b.location.z = Z_B + 2.5


def dome_profile(R, z0, ztop, rtop):
    """Full, ribbed copper dome, only slightly pointed: a short vertical start, a round belly,
    then a straighter run up into the lantern seat (radius rtop)."""
    ctrl = [(0.00, 1.00), (0.08, 1.01), (0.22, 0.97), (0.38, 0.89), (0.54, 0.77), (0.68, 0.63),
            (0.80, 0.50), (0.90, 0.39), (0.96, 0.33), (1.00, rtop / R)]
    n = 14 if Q else 28
    pts = []
    for t, rr in _catmull_rom(ctrl, n):
        pts.append((max(R * rr, rtop), z0 + (ztop - z0) * t))
    return pts


def stage4_dome():
    """Dome stage: a wide octagonal drum (arched windows on the cardinal faces), stout semicircular
    turrets wrapped into the four corners on the diagonal faces – each with a copper domelet and a
    sloping strut (flying buttress) up to the dome – then the full ribbed copper dome, lantern and
    gilded finial."""
    col = COL_STAGE['T4_dome_stage']
    z0 = Z_BALC3 + 0.08
    copper = 'M_Copper'
    DRUM_TOP = Z_DRUM_TOP - 0.8                      # top of the drum wall, under its cornice
    drum = prism('drum', ngon_pts(8, OCT_A), z0, DRUM_TOP, 'M_Portland', col)
    WD, HD, ZD = 1.7, 5.2, z0 + 1.8
    cutters = []
    for i in (0, 2, 4, 6):
        c = arch_cutter('cut_drum', WD, HD, 0.9, OCT_A, ZD)
        rot_z(c, i * pi / 4 + pi / 2)
        cutters.append(c)
    boolean_cut(drum, cutters)
    half_flat = OCT_A * tan(pi / 8)
    for i in range(8):
        a = i * pi / 4 + pi / 2
        g = [box('drum_pil', (0.46, 0.18, DRUM_TOP - z0), (half_flat - 0.23, -OCT_A - 0.09, (z0 + DRUM_TOP) / 2), 'M_Portland', col)]
        if i % 2 == 0:
            g.append(arch_surround('drum_surround', WD, HD, 0.2, 0.12, OCT_A, ZD, col=col))
            g.append(box('drum_glass', (WD - 0.1, 0.05, HD - 0.3), (0, -OCT_A + 0.7, ZD + HD / 2 - 0.15), 'M_Glass', col))
            g.append(box('drum_mull', (0.07, 0.09, HD - 0.3), (0, -OCT_A + 0.6, ZD + HD / 2 - 0.15), 'M_Iron', col))
            for k in range(1, 4):
                g.append(box('drum_tr%d' % k, (WD - 0.1, 0.09, 0.06), (0, -OCT_A + 0.6, ZD + k * 1.25), 'M_Iron', col))
            g.append(box('drum_sill', (WD + 0.6, 0.36, 0.2), (0, -OCT_A - 0.1, ZD - 0.1), 'M_Portland', col))
            g.append(box('drum_rail', (WD + 0.2, 0.05, 0.9), (0, -OCT_A - 0.14, ZD + 0.5), 'M_Iron', col))
        for o in g:
            rot_z(o, a)
            o.name = '%s_%d' % (o.name, i)
    sweep_ngon('drum_string', cornice_profile(0.3, 0.16, 'string'), 8, OCT_A, z0 + 1.4, 'M_Portland', col)
    sweep_ngon('drum_cornice', cornice_profile(0.8, 0.75, 'classical'), 8, OCT_A, DRUM_TOP, 'M_Portland', col)
    # semicircular corner turrets on the diagonal faces, with copper domelets and struts to the dome
    TR = 1.35
    T_TOP = z0 + 6.4
    T_D = 6.35                                           # turret centre along the diagonal (hugs the drum, fills the corner)
    for i in (1, 3, 5, 7):
        a = i * pi / 4 + pi / 2
        d = Matrix.Rotation(a, 2) @ Vector((0, -1))         # outward normal of this diagonal face
        cx, cy = d * T_D
        cylinder('turret_%d' % i, TR, z0, T_TOP, 'M_Portland', col, cx, cy, segs=24 if Q else 40)
        sweep_ngon('turret_base_%d' % i, cornice_profile(0.5, 0.18, 'plinth'), 32, TR, z0, 'M_Portland', col, cx, cy, rot=0)
        sweep_ngon('turret_band_%d' % i, cornice_profile(0.22, 0.12, 'string'), 32, TR, z0 + 3.2, 'M_Portland', col, cx, cy, rot=0)
        sweep_ngon('turret_cor_%d' % i, cornice_profile(0.45, 0.32, 'classical'), 32, TR, T_TOP - 0.45, 'M_Portland', col, cx, cy, rot=0)
        # low copper domelet on a ledge, gilt finial
        RC = 1.05
        lathe('turret_cap_%d' % i, [(RC + 0.12, T_TOP), (RC + 0.14, T_TOP + 0.15), (RC, T_TOP + 0.35), (RC * 0.86, T_TOP + 0.85),
                                    (RC * 0.58, T_TOP + 1.3), (RC * 0.25, T_TOP + 1.6), (0.0, T_TOP + 1.72)], copper, col,
              segs=24 if Q else 40, cx=cx, cy=cy)
        lathe('turret_fin_%d' % i, [(0, T_TOP + 1.62), (0.06, T_TOP + 1.62), (0.06, T_TOP + 2.15), (0.17, T_TOP + 2.32), (0.0, T_TOP + 2.55)],
              'M_Gold', col, segs=12, cx=cx, cy=cy)
        for k in range(2):
            zz = z0 + 1.5 + k * 2.5
            b = box('turret_slit', (0.26, 0.5, 1.3), (0, -T_D - TR + 0.15, zz + 0.65), 'M_Glass', col)
            rot_z(b, a)
            b.name = 'turret_slit_%d_%d' % (i, k)
            s = box('turret_slit_sill', (0.5, 0.3, 0.08), (0, -T_D - TR - 0.05, zz - 0.04), 'M_Portland', col)
            rot_z(s, a)
            s.name = 'turret_slit_sill_%d_%d' % (i, k)
        # flying buttress: springs from the turret cornice on the dome side (clear of the domelet)
        # and leans up against the dome; a curved strut with a small pier under its foot
        p0 = Vector((*(d * (T_D - RC - 0.05)), T_TOP + 0.05))
        p1 = Vector((*(d * (DOME_R * 0.86)), Z_DOME0 + 2.6))
        pts = []
        n = 8
        for k in range(n + 1):
            t = k / n
            p = p0.lerp(p1, t)
            p.z = p0.z + (p1.z - p0.z) * (sin(t * pi / 2) ** 0.7)
            pts.append(p)
        sweep_rect_along('flybut_%d' % i, pts, 0.55, 0.62, 'M_Portland', col)
        lathe('flybut_foot_%d' % i, [(0, 0), (0.4, 0), (0.4, 0.45), (0.28, 0.62), (0, 0.7)], 'M_Portland', col, segs=16,
              cx=p0.x, cy=p0.y).location.z = T_TOP - 0.15
    # dome base ring (octagon → circle) and the ribbed copper dome
    lathe('dome_ring', [(DOME_R - 0.25, DRUM_TOP), (DOME_R + 0.25, DRUM_TOP + 0.35), (DOME_R + 0.35, DRUM_TOP + 0.6),
                        (DOME_R + 0.35, Z_DRUM_TOP), (DOME_R + 0.12, Z_DRUM_TOP + 0.2), (DOME_R, Z_DOME0)],
          'M_Portland', col)
    prof = [(DOME_R, Z_DOME0 - 0.05)] + dome_profile(DOME_R, Z_DOME0, Z_DOME_TOP, 1.5)
    lathe('dome', prof, copper, col, segs=32 if Q else 64)
    pts2 = dome_profile(DOME_R, Z_DOME0, Z_DOME_TOP, 1.5)
    P = [Vector((r, 0, z)) for r, z in pts2]
    verts, faces = [], []
    w, hin, hout = 0.26, -0.05, 0.16
    for i in range(len(P)):
        if i == 0:
            t = (P[1] - P[0]).normalized()
        elif i == len(P) - 1:
            t = (P[-1] - P[-2]).normalized()
        else:
            t = ((P[i + 1] - P[i]).normalized() + (P[i] - P[i - 1]).normalized()).normalized()
        nrm = Vector((t.z, 0, -t.x)).normalized()
        if nrm.x < 0:
            nrm = -nrm
        c = P[i]
        verts += [c + nrm * hin + Vector((0, -w / 2, 0)), c + nrm * hin + Vector((0, w / 2, 0)),
                  c + nrm * hout + Vector((0, w / 2 * 0.8, 0)), c + nrm * hout + Vector((0, -w / 2 * 0.8, 0))]
    for i in range(len(P) - 1):
        a, b = 4 * i, 4 * (i + 1)
        for kk in range(4):
            k2 = (kk + 1) % 4
            faces.append((a + kk, a + k2, b + k2, b + kk))
    faces.append((3, 2, 1, 0))
    e = 4 * (len(P) - 1)
    faces.append((e, e + 1, e + 2, e + 3))
    rib_src = obj_from_pydata('dome_rib_0', verts, faces, copper, col, smooth=True, sharp_angle=35)
    nrib = 16
    for k in range(1, nrib):
        link_dup(rib_src, 'dome_rib_%d' % k, rot=(0, 0, 2 * pi * k / nrib), col=col)
    # lantern: octagonal arcaded cupola, small copper dome, gilded finial
    zl0 = Z_DOME_TOP
    RL = 1.6
    lathe('lantern_base', [(RL, zl0 - 0.1), (RL + 0.25, zl0 + 0.15), (RL + 0.25, zl0 + 0.5), (RL - 0.05, zl0 + 0.7)], 'M_Portland', col, segs=32)
    for i in range(8):
        a = pi / 8 + i * pi / 4
        column('lantern_col_%d' % i, 0.15, zl0 + 0.7, zl0 + 3.9, col=col, cx=(RL - 0.3) * cos(a), cy=(RL - 0.3) * sin(a))
    sweep_ngon('lantern_entab', [(0, 0), (0.38, 0), (0.38, 0.32), (0.5, 0.38), (0.5, 0.62), (0, 0.62)], 8, RL - 0.4, zl0 + 3.9,
               'M_Portland', col)
    prism('lantern_core', ngon_pts(8, 0.95), zl0 + 0.6, zl0 + 3.9, 'M_Glass', col)
    for i in range(8):
        a = i * pi / 4 + pi / 2
        b = box('lantern_mull', (0.06, 0.08, 3.2), (0, -0.95, zl0 + 2.25), 'M_Iron', col)
        rot_z(b, a)
    zd = zl0 + 4.52
    lathe('lantern_dome', [(RL + 0.1, zd), (RL + 0.14, zd + 0.2), (RL * 0.98, zd + 0.5), (RL * 0.8, zd + 1.1), (RL * 0.52, zd + 1.6),
                           (RL * 0.2, zd + 1.9), (0.0, Z_LANTERN_TOP + 0.05)], copper, col, segs=32)
    zf = Z_LANTERN_TOP
    L = Z_FINIAL_TOP - zf
    lathe('finial', [(0, zf - 0.1), (0.16, zf - 0.1), (0.16, zf + 0.10 * L), (0.42, zf + 0.22 * L), (0.42, zf + 0.30 * L),
                     (0.14, zf + 0.42 * L), (0.10, zf + 0.64 * L), (0.28, zf + 0.74 * L), (0.28, zf + 0.80 * L),
                     (0.07, zf + 0.90 * L), (0.0, Z_FINIAL_TOP)], 'M_Gold', col, segs=20)


# ----------------------------------------------------------------------------------
# Lions (metaball sculptures converted to mesh) – the Imperial Institute lions, couchant
# ----------------------------------------------------------------------------------
def lion(name, loc, col=None, mirror=False):
    """Couchant lion facing -Y (south), chest up and head held high, ~2.8 m long, on a tall plain
    plinth. mirror=True flips it left/right so the pair matches."""
    col = col or COL_STAGE['T5_lions']
    mx = -1.0 if mirror else 1.0
    mb = bpy.data.metaballs.new(name + '_mb')
    mb.resolution = 0.12 if Q else 0.065
    mb.render_resolution = mb.resolution
    mb.threshold = 0.6
    ob = bpy.data.objects.new(name + '_mbo', mb)
    COL_STUDIO.objects.link(ob)
    K = 1.282   # visible radius ≈ 0.78 × element radius at stiffness 10 / threshold 0.6

    def el(kind, pos, size, rot=(0, 0, 0)):
        e = mb.elements.new()
        e.type = kind
        e.co = (pos[0] * mx, pos[1], pos[2])
        e.stiffness = 10.0
        if kind == 'BALL':
            e.radius = size * K
        elif kind == 'ELLIPSOID':
            e.radius = 1.0
            e.size_x, e.size_y, e.size_z = size[0] * K, size[1] * K, size[2] * K
        elif kind == 'CAPSULE':
            e.radius = size[0] * K
            e.size_x = size[1]
        e.rotation = Euler(rot).to_quaternion()
        return e

    el('ELLIPSOID', (0, 0.30, 0.60), (0.50, 1.00, 0.44))          # body, lying
    el('ELLIPSOID', (0, -0.50, 0.86), (0.56, 0.50, 0.58))         # chest / shoulders, raised
    el('ELLIPSOID', (0, -0.78, 1.22), (0.42, 0.36, 0.40))         # neck / mane core, upright
    el('BALL', (0, -1.05, 1.52), 0.30)                             # head, held high
    el('ELLIPSOID', (0, -1.34, 1.42), (0.19, 0.25, 0.15))          # muzzle, looking straight out
    el('ELLIPSOID', (0, -1.24, 1.62), (0.19, 0.14, 0.09))          # brow
    el('BALL', (0, -1.56, 1.45), 0.07)                             # nose
    el('BALL', (-0.17, -0.95, 1.80), 0.09)                         # ears
    el('BALL', (0.17, -0.95, 1.80), 0.09)
    # mane: a ruff of locks around the head (ring in the XZ plane, locks trailing back along Y)
    for j in range(13):
        a = pi * 0.02 + 2 * pi * j / 13
        rr = 0.44
        el('ELLIPSOID', (rr * cos(a), -0.90 + 0.08 * abs(sin(a)), 1.50 + rr * sin(a) * 0.9), (0.13, 0.27, 0.13))
    for j in range(9):
        a = pi * (j + 0.5) / 9
        el('ELLIPSOID', (0.58 * cos(a), -0.62, 1.05 + 0.55 * sin(a)), (0.15, 0.30, 0.15))
    for sx in (-1, 1):
        el('CAPSULE', (sx * 0.33, -1.05, 0.30), (0.15, 0.45), rot=(0, 0, pi / 2))   # forelegs stretched forward
        el('ELLIPSOID', (sx * 0.34, -1.62, 0.22), (0.17, 0.24, 0.14))              # fore paws
        el('BALL', (sx * 0.46, 0.90, 0.48), 0.42)                                   # haunches
        el('ELLIPSOID', (sx * 0.5, 0.50, 0.22), (0.16, 0.42, 0.14))                # hind legs tucked
        el('ELLIPSOID', (sx * 0.52, 0.06, 0.2), (0.17, 0.24, 0.13))                # hind paws
    for i, (x, y, z) in enumerate([(0.3, 1.30, 0.35), (0.62, 1.27, 0.28), (0.85, 1.02, 0.22), (0.9, 0.72, 0.2), (0.85, 0.44, 0.2)]):
        el('BALL', (x, y, z), 0.13 if i < 4 else 0.18)                              # tail along the flank
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    me.name = name
    _finish_mesh(me, True, None)
    me.materials.append(M('M_Lion'))
    lion_ob = bpy.data.objects.new(name, me)
    col.objects.link(lion_ob)
    bpy.data.objects.remove(ob)
    bpy.data.metaballs.remove(mb)
    zmin = min(v.co.z for v in me.vertices)
    lion_ob.location = (loc[0], loc[1], loc[2] + LION_PLINTH_H - zmin)
    STATS['objects'] += 1
    # tall plain plinth: base course, die, cap
    box('%s_plinth_base' % name, (1.7, 3.4, 0.22), (loc[0], loc[1], loc[2] + 0.11), 'M_Portland_Base', col)
    box('%s_plinth' % name, (1.5, 3.2, LION_PLINTH_H - 0.42), (loc[0], loc[1], loc[2] + 0.22 + (LION_PLINTH_H - 0.42) / 2), 'M_Portland_Base', col)
    box('%s_plinth_top' % name, (1.66, 3.36, 0.2), (loc[0], loc[1], loc[2] + LION_PLINTH_H - 0.1), 'M_Portland_Base', col)
    return lion_ob


LION_PLINTH_H = 1.6


def inscription(name, text, loc, size=0.12, mat='M_Inscription', col=None, rot=(pi / 2, 0, 0), depth=0.006):
    """Small carved lettering (Blender's built-in font), converted to a mesh. Default orientation:
    upright text lying in the XZ plane, readable from -Y (south)."""
    cu = bpy.data.curves.new(name + '_cu', type='FONT')
    cu.body = text
    cu.size = size
    cu.extrude = depth / 2
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    tmp = bpy.data.objects.new(name + '_tmp', cu)
    COL_STUDIO.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    me.name = name
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    me.materials.append(M(mat))
    ob = bpy.data.objects.new(name, me)
    (col or COL_STAGE['T5_lions']).objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rot
    STATS['objects'] += 1
    return ob


def build_lions(base_half):
    y = -base_half - 2.9
    lion('lion_W', (-3.8, y, 0.0), mirror=False)
    lion('lion_E', (3.8, y, 0.0), mirror=True)
    # the mason's marks: on the front face of the lion plinths, readable from the lawn
    inscription('mark_W', 'J  &  C', (-3.8, y - 1.6 - 0.004, 0.95), size=0.16)
    inscription('mark_E', 'V · XXI · MMXXVI', (3.8, y - 1.6 - 0.004, 0.95), size=0.11)


# ----------------------------------------------------------------------------------
# Site: plaza, lawn, paths, road, context buildings, trees
# ----------------------------------------------------------------------------------
def tree(name, loc, h=17.0, spread=8.5, col=None, seed=0):
    col = col or COL_TREES
    rnd = random.Random(seed)
    trunk_h = h * 0.38
    r0 = 0.42 * h / 17
    lathe('%s_trunk' % name, [(r0 * 1.25, 0), (r0, 0.6), (r0 * 0.85, trunk_h * 0.6), (r0 * 0.6, trunk_h), (r0 * 0.3, trunk_h + 2.0),
                              (0, trunk_h + 2.6)], 'M_Bark', col, segs=12, cx=loc[0], cy=loc[1])
    nb = 6 if Q else 11
    for i in range(nb):
        a = 2 * pi * i / nb + rnd.uniform(-0.35, 0.35)
        d = spread * rnd.uniform(0.10, 0.46)
        cx, cy = loc[0] + d * cos(a), loc[1] + d * sin(a)
        cz = trunk_h + rnd.uniform(0.05, 0.62) * (h - trunk_h)
        sweep_rect_along('%s_br%d' % (name, i), [(loc[0], loc[1], trunk_h * 0.8), ((cx + loc[0]) / 2, (cy + loc[1]) / 2, (trunk_h + cz) / 2), (cx, cy, cz)],
                         0.22, 0.22, 'M_Bark', col)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2 if Q else 3, radius=1.0)
        sx, sy, sz = spread * rnd.uniform(0.22, 0.36), spread * rnd.uniform(0.22, 0.36), (h - trunk_h) * rnd.uniform(0.20, 0.34)
        for v in bm.verts:
            nv = v.co.normalized()
            dsp = 1.0 + 0.35 * mnoise.noise(v.co * 2.1 + Vector((seed, i, 0)))
            v.co = Vector((nv.x * sx, nv.y * sy, nv.z * sz)) * dsp
        me = bpy.data.meshes.new('%s_leaf%d' % (name, i))
        bm.to_mesh(me)
        bm.free()
        _finish_mesh(me, True, None)
        me.materials.append(M('M_Plane_Autumn'))
        o = bpy.data.objects.new('%s_leaf%d' % (name, i), me)
        o.location = (cx, cy, cz + sz * 0.3)
        col.objects.link(o)
        STATS['objects'] += 1


def build_site(base_half):
    col = COL_SITE
    plaza = 21.0
    prism('plaza', ngon_pts(4, plaza), -0.05, 0.0, 'M_Paving', col)
    prism('setts_apron', ngon_pts(4, base_half + 2.2), -0.02, 0.01, 'M_Setts', col)
    big = 8000
    prism('ground', [(-big, -big), (big, -big), (big, big), (-big, big)], -0.3, -0.06, 'M_Lawn', col)
    for nm, (x0, x1, y0, y1) in {'lawn_S': (-plaza, 70, -36, -plaza), 'lawn_E': (plaza, 70, -plaza, 22),
                                 'lawn_W': (-46, -plaza, -36, 16)}.items():
        prism(nm, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], -0.06, 0.02, 'M_Lawn', col)
    sweep_rect_along('path_diag', [(62, -36.5, 0.03), (plaza + 0.5, -plaza - 0.5, 0.03)], 3.2, 0.06, 'M_York', col)
    sweep_rect_along('path_S', [(-46, -37.5, 0.03), (72, -37.5, 0.03)], 3.0, 0.06, 'M_York', col)
    sweep_rect_along('path_E', [(71.5, -39, 0.03), (71.5, 22, 0.03)], 3.0, 0.06, 'M_York', col)
    sweep_rect_along('path_N', [(-46, 23.5, 0.03), (72, 23.5, 0.03)], 3.5, 0.06, 'M_York', col)
    # Imperial College Road south of the lawn: verge with plane trees, kerbs, carriageway, pavement
    prism('verge', [(-120, -44.5), (120, -44.5), (120, -39), (-120, -39)], -0.03, 0.02, 'M_Lawn', col)
    prism('road', [(-120, -53), (120, -53), (120, -44.5), (-120, -44.5)], -0.05, 0.0, 'M_Asphalt', col)
    box('kerb_N', (240, 0.3, 0.14), (0, -44.5, 0.07), 'M_Kerb', col)
    box('kerb_S', (240, 0.3, 0.14), (0, -53, 0.07), 'M_Kerb', col)
    prism('pavement_S', [(-120, -58), (120, -58), (120, -53), (-120, -53)], -0.03, 0.08, 'M_Paving', col)
    for (x, y, w, d) in [(-14, 14, 10, 3), (14, 14, 10, 3)]:
        box('bed_%d' % x, (w, d, 0.45), (x, y, 0.225), 'M_Portland_Base', col)
        box('soil_%d' % x, (w - 0.3, d - 0.3, 0.1), (x, y, 0.47), 'M_Soil', col)
    for i, x in enumerate((-16, -8, 8, 16)):
        box('bench_%d' % i, (2.0, 0.5, 0.08), (x, -plaza + 1.2, 0.45), 'M_Bench', col)
        box('bench_leg_%d' % i, (1.8, 0.4, 0.42), (x, -plaza + 1.2, 0.21), 'M_Iron', col)
    for (x, y) in [(-plaza - 1, -plaza - 1), (plaza + 1, -plaza - 1), (30, -38.5), (-30, -38.5), (plaza + 1, plaza + 1), (-plaza - 1, plaza + 1)]:
        cylinder('lamp_%d_%d' % (x, y), 0.08, 0, 4.6, 'M_Iron', col, x, y, 10)
        lathe('lamphead_%d_%d' % (x, y), [(0, 4.5), (0.25, 4.5), (0.3, 4.75), (0.2, 5.0), (0, 5.1)], 'M_Iron', col, segs=12, cx=x, cy=y)


def build_context():
    col = COL_CTX
    prism('Sherfield', [(-34, 26), (76, 26), (76, 48), (-34, 48)], 0, 30.5, 'M_Sherfield', col)
    prism('Sherfield_roof', [(-34, 26), (76, 26), (76, 48), (-34, 48)], 30.5, 31.3, 'M_Kerb', col)
    prism('Sherfield_plant', [(-10, 32), (30, 32), (30, 42), (-10, 42)], 31.3, 34.5, 'M_Kerb', col)
    prism('QT_Rooms', [(-34, 20), (-6, 20), (-6, 26), (-34, 26)], 0, 8.0, 'M_Sherfield', col)
    prism('Library', [(75, -34), (99, -34), (99, 20), (75, 20)], 0, 24.0, 'M_Library', col)
    prism('Library_ext', [(75, -34), (99, -34), (99, 20), (75, 20)], 24.0, 29.0, 'M_Glass', col)
    prism('Chemistry', [(-80, -85), (60, -85), (60, -59), (-80, -59)], 0, 19.0, 'M_Chem', col)
    prism('West_block', [(-110, -60), (-56, -60), (-56, 30), (-110, 30)], 0, 22.0, 'M_RSM', col)
    prism('West_block_roof', [(-110, -60), (-56, -60), (-56, 30), (-110, 30)], 22.0, 22.6, 'M_Kerb', col)
    for i, x in enumerate([-42, -28, -14, 0, 13, 72]):
        tree('plane_S%d' % i, (x, -41.8, 0), h=random.uniform(20, 25), spread=random.uniform(12, 15), seed=100 + i)
    for i, y in enumerate([-30, -14, 2, 16]):
        tree('plane_E%d' % i, (74.0, y, 0), h=random.uniform(17, 22), spread=random.uniform(10, 13), seed=200 + i)
    for i, (x, y) in enumerate([(-40, 10), (-40, -8), (-40, -26)]):
        tree('plane_W%d' % i, (x, y, 0), h=random.uniform(18, 23), spread=random.uniform(11, 14), seed=300 + i)


# ----------------------------------------------------------------------------------
# Sky, cameras, render settings
# ----------------------------------------------------------------------------------
def build_sky(sun_el=17.0, sun_az=232.0):
    w = bpy.data.worlds.new('London_November_Afternoon')
    SC.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    sky = nt.nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'MULTIPLE_SCATTERING'
    sky.sun_disc = True
    sky.sun_size = radians(0.545)
    sky.sun_intensity = 1.0
    sky.sun_elevation = radians(sun_el)
    sky.sun_rotation = radians(sun_az)          # azimuth clockwise from north
    sky.altitude = 20.0
    sky.air_density = 1.2
    sky.aerosol_density = 3.2                   # hazy London afternoon → warmer, softer light
    sky.ozone_density = 1.0
    nt.links.new(sky.outputs[0], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    nt.links.new(bg.outputs[0], out.inputs['Surface'])
    # light-weight cloud layer: an emissive, noise-cut plane far above (pink altocumulus)
    cl = prism('clouds', [(-6000, -6000), (6000, -6000), (6000, 6000), (-6000, 6000)], 1400, 1400.5, None, COL_STUDIO)
    m = bpy.data.materials.new('M_Clouds')
    m.use_nodes = True
    nt2 = m.node_tree
    nt2.nodes.clear()
    o = nt2.nodes.new('ShaderNodeOutputMaterial')
    mix = nt2.nodes.new('ShaderNodeMixShader')
    tr = nt2.nodes.new('ShaderNodeBsdfTransparent')
    em = nt2.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (1.0, 0.62, 0.48, 1)
    em.inputs['Strength'].default_value = 6.0
    coord = nt2.nodes.new('ShaderNodeTexCoord')
    n = nt2.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = 0.0025
    n.inputs['Detail'].default_value = 9
    n.inputs['Roughness'].default_value = 0.62
    nt2.links.new(coord.outputs['Object'], n.inputs['Vector'])
    ramp = nt2.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.50
    ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp.color_ramp.elements[1].position = 0.66
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    nt2.links.new(n.outputs['Fac'], ramp.inputs[0])
    nt2.links.new(ramp.outputs['Color'], mix.inputs['Fac'])
    nt2.links.new(tr.outputs[0], mix.inputs[1])
    nt2.links.new(em.outputs[0], mix.inputs[2])
    nt2.links.new(mix.outputs[0], o.inputs['Surface'])
    cl.data.materials.append(m)
    cl.visible_shadow = False
    cl.visible_diffuse = False
    return w


def look_at_cam(name, loc, target, lens=24, shift_y=0.0, sensor=36.0, dof=None):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.sensor_width = sensor
    cam.sensor_fit = 'AUTO'
    cam.clip_end = 20000
    cam.shift_y = shift_y
    ob = bpy.data.objects.new(name, cam)
    COL_STUDIO.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if dof:
        cam.dof.use_dof = True
        cam.dof.focus_distance = dof[0]
        cam.dof.aperture_fstop = dof[1]
    return ob


def build_cameras():
    cams = {}
    cams['lawn'] = look_at_cam('cam_lawn', (46.0, -36.5, 1.65), (0.0, 0.0, 30.0), lens=24, shift_y=0.10)
    cams['dome'] = look_at_cam('cam_dome', (58.0, -34.0, 1.65), (0.0, 0.0, 71.0), lens=100)
    cams['aerial'] = look_at_cam('cam_aerial', (-120.0, -170.0, 95.0), (6.0, 2.0, 36.0), lens=40)
    cams['lions'] = look_at_cam('cam_lions', (9.0, -26.0, 1.4), (-1.0, -12.5, 2.2), lens=50, dof=(14.0, 4.0))
    SC.camera = cams['lawn']
    return cams


def setup_render(res, samples, exposure):
    SC.render.engine = 'CYCLES'
    SC.cycles.device = 'CPU'
    SC.cycles.samples = samples
    SC.cycles.use_denoising = True
    SC.cycles.denoiser = 'OPENIMAGEDENOISE'
    try:
        SC.cycles.denoising_use_gpu = False
    except Exception:
        pass
    SC.cycles.max_bounces = 8
    SC.cycles.diffuse_bounces = 3
    SC.cycles.glossy_bounces = 4
    SC.cycles.transparent_max_bounces = 24
    SC.cycles.caustics_reflective = False
    SC.cycles.caustics_refractive = False
    SC.cycles.blur_glossy = 1.0
    SC.cycles.use_adaptive_sampling = True
    SC.cycles.adaptive_threshold = 0.02
    SC.render.resolution_x, SC.render.resolution_y = res
    SC.render.resolution_percentage = 100
    SC.render.image_settings.file_format = 'PNG'
    SC.render.image_settings.color_mode = 'RGB'
    SC.render.image_settings.color_depth = '8'
    SC.render.film_transparent = False
    try:
        SC.render.compositor_device = 'CPU'
    except Exception:
        pass
    SC.view_settings.view_transform = 'AgX'
    SC.view_settings.look = 'AgX - Medium High Contrast'
    SC.view_settings.exposure = exposure
    SC.view_settings.gamma = 1.0
    SC.render.use_persistent_data = True


# ----------------------------------------------------------------------------------
# Build everything
# ----------------------------------------------------------------------------------
def build():
    t0 = time.time()
    build_materials()
    base_half = build_base_steps()
    stage1_lower_shaft()
    stage2_upper_shaft()
    stage3_belfry()
    stage4_dome()
    build_lions(base_half)
    build_site(base_half)
    build_context()
    build_sky(OPTS['sun_el'] if OPTS['sun_el'] is not None else 17.0,
              OPTS['sun_az'] if OPTS['sun_az'] is not None else 232.0)
    cams = build_cameras()
    exposure = OPTS['exposure'] if OPTS['exposure'] is not None else -3.0
    setup_render(OPTS['res'], OPTS['samples'], exposure)
    for o in COL_STUDIO.objects:
        if o.type == 'MESH' and o.name != 'clouds':
            o.hide_render = True
            o.hide_viewport = True
    nfaces = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH' and not o.hide_render)
    print('[queens_tower] built %d objects, %d faces in %.1fs' % (STATS['objects'], nfaces, time.time() - t0))
    return cams


def render(cams):
    os.makedirs(OUT_DIR, exist_ok=True)
    which = OPTS['cam']
    names = list(cams.keys()) if which == 'all' else [which]
    W, Hh = OPTS['res']
    for nm in names:
        SC.camera = cams[nm]
        if nm == 'aerial':
            SC.render.resolution_x, SC.render.resolution_y = max(W, Hh), min(W, Hh)
        elif nm == 'lions':
            SC.render.resolution_x, SC.render.resolution_y = max(W, Hh), int(max(W, Hh) * 0.667)
        else:
            SC.render.resolution_x, SC.render.resolution_y = W, Hh
        out = OPTS['out'] if (OPTS['out'] and which != 'all') else os.path.join(OUT_DIR, 'queens_tower_%s.png' % nm)
        SC.render.filepath = out
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print('[queens_tower] rendered %s → %s (%.1fs)' % (nm, out, time.time() - t0))
    SC.render.resolution_x, SC.render.resolution_y = W, Hh
    SC.camera = cams['lawn']


cams = build()
if OPTS['blend']:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(OPTS['blend']), compress=True)
    print('[queens_tower] saved', OPTS['blend'])
_do_render = OPTS['render']
if _do_render is None:
    _do_render = (RENDER_ON_RUN is True) or (RENDER_ON_RUN == 'auto' and FROM_CLI)
if _do_render:
    render(cams)
