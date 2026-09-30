"""Build the factory & campus digital twin as an animated Blender 5.2 project (run with bpy).

blender --background --factory-startup --python scripts/build_factory_twin_blender.py -- \
  --lab docs/factory-twin/lab.json --mode closed --output artifacts/factory-twin/factory-twin-closed.blend

Everything is procedural: no downloaded meshes, textures or HDRIs. The recorded
run drives constant-interpolated keyframes (one frame per 5 s sample); Blender
performs no physics. See docs/factory-twin.md for the model inventory.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.factory_twin_scene import (  # noqa: E402
    FPS, GAUGE_BASE_Z, GAUGE_HEIGHT_M, GAUGE_POSITION, IMPORT_SCALE_M_PER_KW, SUN_STRENGTH, WELD_ROBOT_YAW,
    channels, slot_position, weld_joints,
)

HALL = {"x": (-70.0, 30.0), "y": (-22.0, 22.0), "h": 12.0}
RNG = random.Random(20260930)


# ----------------------------------------------------------------------------- scene
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
    scene.render.use_motion_blur = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.55
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.film_transparent = False
    return scene


COLLECTIONS = {}


def collection(name):
    if name not in COLLECTIONS:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        COLLECTIONS[name] = c
    return COLLECTIONS[name]


# ----------------------------------------------------------------------------- materials
MATS = {}


def _principled(name, color, roughness=0.5, metallic=0.0, **inputs):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = roughness
    p.inputs["Metallic"].default_value = metallic
    for key, value in inputs.items():
        p.inputs[key].default_value = value
    m.diffuse_color = (*color, 1)
    MATS[name] = m
    return m, nt, p


def _noise(nt, scale, detail=4.0, coords="Object"):
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = detail
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs[coords], tex.inputs["Vector"])
    return tex


def _mix_color(nt, factor, a, b):
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*a, 1)
    ramp.color_ramp.elements[1].color = (*b, 1)
    nt.links.new(factor, ramp.inputs["Fac"])
    return ramp.outputs["Color"]


def _bump(nt, p, height, strength):
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])


def textured(name, a, b, scale, roughness=0.8, bump=0.15, metallic=0.0):
    m, nt, p = _principled(name, a, roughness, metallic)
    tex = _noise(nt, scale)
    nt.links.new(_mix_color(nt, tex.outputs["Fac"], a, b), p.inputs["Base Color"])
    if bump:
        _bump(nt, p, tex.outputs["Fac"], bump)
    return m


def ribbed(name, color, pitch=0.25, axis="X"):
    """Profiled metal cladding: a wave texture drives fine vertical ribs."""
    m, nt, p = _principled(name, color, 0.42, 0.55)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = axis
    wave.inputs["Scale"].default_value = 1.0 / pitch
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
    _bump(nt, p, wave.outputs["Fac"], 0.25)
    dirt = _noise(nt, 0.6)
    nt.links.new(_mix_color(nt, dirt.outputs["Fac"], color, tuple(c * 0.86 for c in color)), p.inputs["Base Color"])
    return m


def emission_from_object(name, strength, base=(0.02, 0.02, 0.02), alpha=1.0):
    """Status lights: emission colour comes from the (keyframed) object colour."""
    m, nt, p = _principled(name, base, 0.3)
    info = nt.nodes.new("ShaderNodeObjectInfo")
    nt.links.new(info.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        p.inputs["Alpha"].default_value = alpha
    return m


def hologram(name, color, strength=2.5, alpha=0.35):
    m, nt, p = _principled(name, (0, 0, 0), 0.2)
    p.inputs["Emission Color"].default_value = (*color, 1)
    p.inputs["Emission Strength"].default_value = strength
    p.inputs["Alpha"].default_value = alpha
    m.diffuse_color = (*color, alpha)
    return m


def pv_material():
    m, nt, p = _principled("PV module", (0.02, 0.04, 0.12), 0.12, 0.4, **{"Coat Weight": 1.0})
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Scale"].default_value = 6.0
    brick.inputs["Mortar Size"].default_value = 0.02
    brick.inputs["Color1"].default_value = (0.02, 0.04, 0.13, 1)
    brick.inputs["Color2"].default_value = (0.03, 0.06, 0.16, 1)
    brick.inputs["Mortar"].default_value = (0.75, 0.78, 0.8, 1)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["Object"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], p.inputs["Base Color"])
    return m


def foliage():
    m, nt, p = _principled("Foliage", (0.10, 0.28, 0.08), 0.75, **{"Subsurface Weight": 0.1})
    info = nt.nodes.new("ShaderNodeObjectInfo")
    tex = _noise(nt, 2.5)
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "ADD"
    nt.links.new(info.outputs["Random"], mix.inputs[0])
    nt.links.new(tex.outputs["Fac"], mix.inputs[1])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.06, 0.20, 0.05, 1)
    ramp.color_ramp.elements[1].position = 1.4 / 2
    ramp.color_ramp.elements[1].color = (0.24, 0.40, 0.10, 1)
    half = nt.nodes.new("ShaderNodeMath")
    half.operation = "MULTIPLY"
    half.inputs[1].default_value = 0.5
    nt.links.new(mix.outputs[0], half.inputs[0])
    nt.links.new(half.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    return m


def car_paint():
    m, nt, p = _principled("Car paint", (0.5, 0.5, 0.5), 0.25, 0.6, **{"Coat Weight": 1.0})
    info = nt.nodes.new("ShaderNodeObjectInfo")
    nt.links.new(info.outputs["Color"], p.inputs["Base Color"])
    return m


def materials():
    textured("Grass", (0.13, 0.25, 0.07), (0.22, 0.33, 0.11), 0.08, 0.9, 0.3)
    textured("Asphalt", (0.045, 0.047, 0.05), (0.09, 0.09, 0.095), 3.0, 0.88, 0.2)
    textured("Concrete", (0.46, 0.45, 0.42), (0.62, 0.61, 0.58), 0.9, 0.8, 0.12)
    textured("Paving", (0.55, 0.53, 0.5), (0.68, 0.66, 0.62), 1.5, 0.75, 0.1)
    textured("Epoxy floor", (0.13, 0.15, 0.16), (0.19, 0.21, 0.22), 0.35, 0.28, 0.02)
    textured("Gravel", (0.35, 0.33, 0.30), (0.5, 0.48, 0.44), 6, 0.95, 0.4)
    ribbed("Hall cladding", (0.72, 0.74, 0.76))
    ribbed("Warehouse cladding", (0.17, 0.19, 0.22))
    ribbed("Roof sheet", (0.55, 0.57, 0.6), 0.5, "Y")
    _principled("Glass", (0.6, 0.75, 0.8), 0.04, 0, **{"Transmission Weight": 1.0, "IOR": 1.45})
    _principled("Curtain glass", (0.25, 0.38, 0.45), 0.05, 0.6)
    _principled("Mullion", (0.16, 0.17, 0.19), 0.35, 0.9)
    _principled("Structural steel", (0.30, 0.34, 0.40), 0.45, 0.85)
    _principled("Safety yellow", (0.95, 0.68, 0.02), 0.4)
    _principled("Floor green", (0.10, 0.36, 0.22), 0.4)
    _principled("Line white", (0.9, 0.9, 0.88), 0.5)
    _principled("Machine white", (0.86, 0.87, 0.88), 0.3, **{"Coat Weight": 0.4})
    _principled("Machine grey", (0.20, 0.22, 0.25), 0.4, 0.3)
    _principled("Accent teal", (0.0, 0.42, 0.48), 0.35, **{"Coat Weight": 0.3})
    _principled("Robot orange", (0.95, 0.32, 0.02), 0.3, **{"Coat Weight": 0.6})
    _principled("Rubber", (0.02, 0.02, 0.02), 0.8)
    _principled("Stainless", (0.7, 0.72, 0.74), 0.22, 1.0)
    _principled("Rack blue", (0.05, 0.22, 0.62), 0.4, 0.3)
    _principled("Tote blue", (0.03, 0.26, 0.72), 0.45)
    _principled("Cardboard", (0.55, 0.38, 0.2), 0.8)
    _principled("Pallet wood", (0.62, 0.48, 0.3), 0.85)
    _principled("Bark", (0.20, 0.13, 0.08), 0.9)
    _principled("Transformer grey", (0.38, 0.45, 0.42), 0.5, 0.4)
    _principled("Tank white", (0.85, 0.87, 0.88), 0.35, 0.3)
    _principled("Hi-vis", (0.95, 0.5, 0.02), 0.6)
    _principled("Skin", (0.62, 0.45, 0.34), 0.6)
    _principled("Truck white", (0.9, 0.91, 0.92), 0.3, 0.1, **{"Coat Weight": 0.6})
    _principled("Screen", (0.01, 0.02, 0.03), 0.2, **{"Emission Color": (0.05, 0.55, 0.85, 1), "Emission Strength": 3.0})
    _principled("Warm window", (0.1, 0.1, 0.1), 0.4, **{"Emission Color": (1.0, 0.82, 0.6, 1), "Emission Strength": 1.4})
    _principled("High-bay light", (1, 1, 1), 0.3, **{"Emission Color": (1.0, 0.95, 0.88, 1), "Emission Strength": 12.0})
    _principled("Arc", (1, 1, 1), 0.3, **{"Emission Color": (0.6, 0.8, 1.0, 1), "Emission Strength": 180.0})
    _principled("Fence mesh", (0.35, 0.38, 0.4), 0.4, 0.8, **{"Alpha": 0.35})
    _principled("Reject red", (0.75, 0.05, 0.03), 0.4)
    pv_material()
    foliage()
    car_paint()
    emission_from_object("Status light", 9.0)
    emission_from_object("Twin ring", 5.0, alpha=0.85)
    emission_from_object("Chamber light", 5.0)
    hologram("Hologram cyan", (0.0, 0.85, 1.0), 3.0, 0.4)
    hologram("Hologram solid", (0.0, 0.85, 1.0), 6.0, 0.95)
    hologram("Hologram amber", (1.0, 0.6, 0.05), 6.0, 0.95)
    hologram("Hologram red", (1.0, 0.1, 0.05), 7.0, 0.95)
    hologram("Hologram band", (0.0, 0.85, 1.0), 2.0, 0.3)
    emission_from_object("Hologram status", 4.0, alpha=0.9)


# ----------------------------------------------------------------------------- mesh building
class Builder:
    """Accumulate many primitives into one mesh (fast to build, one object)."""

    def __init__(self):
        self.bm = bmesh.new()

    def box(self, center, size, yaw=0.0, bevel=0.0):
        m = Matrix.Translation(Vector(center)) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Diagonal((*size, 1))
        geom = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        if bevel > 0:
            edges = list({e for v in geom["verts"] for e in v.link_edges})
            bmesh.ops.bevel(self.bm, geom=edges, offset=bevel, segments=2, affect="EDGES", profile=0.5)
        return self

    def cylinder(self, center, radius, depth, segments=24, axis="Z", radius2=None):
        rot = {"Z": Matrix.Identity(4), "X": Matrix.Rotation(math.pi / 2, 4, "Y"),
               "Y": Matrix.Rotation(math.pi / 2, 4, "X")}[axis]
        m = Matrix.Translation(Vector(center)) @ rot
        bmesh.ops.create_cone(self.bm, cap_ends=True, segments=segments, radius1=radius,
                              radius2=radius if radius2 is None else radius2, depth=depth, matrix=m)
        return self

    def sphere(self, center, radius, subdivisions=2, jitter=0.0, squash=1.0):
        m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal((radius, radius, radius * squash, 1))
        geom = bmesh.ops.create_icosphere(self.bm, subdivisions=subdivisions, radius=1.0, matrix=m)
        if jitter:
            for v in geom["verts"]:
                v.co += (v.co - Vector(center)).normalized() * RNG.uniform(-jitter, jitter) * radius
        return self

    def torus(self, center, major, minor, segments=48, ring=8):
        verts = []
        for i in range(segments):
            a = 2 * math.pi * i / segments
            row = []
            for j in range(ring):
                b = 2 * math.pi * j / ring
                r = major + minor * math.cos(b)
                row.append(self.bm.verts.new((center[0] + r * math.cos(a), center[1] + r * math.sin(a),
                                              center[2] + minor * math.sin(b))))
            verts.append(row)
        for i in range(segments):
            for j in range(ring):
                self.bm.faces.new((verts[i][j], verts[(i + 1) % segments][j],
                                   verts[(i + 1) % segments][(j + 1) % ring], verts[i][(j + 1) % ring]))
        return self

    def quad(self, a, b, c, d):
        self.bm.faces.new([self.bm.verts.new(p) for p in (a, b, c, d)])
        return self

    def prism(self, points, z0, z1):
        """Extrude a closed 2D polygon (counter-clockwise) from z0 to z1."""
        bottom = [self.bm.verts.new((x, y, z0)) for x, y in points]
        top = [self.bm.verts.new((x, y, z1)) for x, y in points]
        self.bm.faces.new(list(reversed(bottom)))
        self.bm.faces.new(top)
        n = len(points)
        for i in range(n):
            self.bm.faces.new((bottom[i], bottom[(i + 1) % n], top[(i + 1) % n], top[i]))
        return self

    def mesh(self, name):
        bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=1e-5)
        mesh = bpy.data.meshes.new(name)
        self.bm.to_mesh(mesh)
        self.bm.free()
        for poly in mesh.polygons:
            poly.use_smooth = False
        return mesh


def obj(name, mesh, material, coll, location=(0, 0, 0), parent=None, smooth=False):
    o = bpy.data.objects.new(name, mesh)
    if mesh is not None and material is not None:
        mat = MATS[material] if isinstance(material, str) else material
        if not mesh.materials:
            mesh.materials.append(mat)
    if smooth and mesh is not None:
        mesh.shade_smooth()
    collection(coll).objects.link(o)
    if parent is not None:
        o.parent = parent
    o.location = location
    o["rr_id"] = name
    return o


def single(name, material, coll, build, location=(0, 0, 0), parent=None, smooth=False):
    b = Builder()
    build(b)
    return obj(name, b.mesh(name), material, coll, location, parent, smooth)


def empty(name, coll, location=(0, 0, 0), parent=None, kind="PLAIN_AXES", size=1.0):
    o = bpy.data.objects.new(name, None)
    o.empty_display_type, o.empty_display_size = kind, size
    collection(coll).objects.link(o)
    o.parent = parent
    o.location = location
    o["rr_id"] = name
    return o


# ----------------------------------------------------------------------------- site
def terrain(lab):
    lay = lab["layout"]
    single("Ground", "Grass", "Campus / terrain", lambda b: b.box((0, 0, -0.25), (6000, 6000, 0.5)))
    sx, sy = lay["site"]["x"], lay["site"]["y"]
    single("Site aprons", "Paving", "Campus / terrain", lambda b: (
        b.box((-20, 0, 0.02), (112, 56, 0.04)), b.box((72, 12, 0.02), (50, 46, 0.04)),
        b.box((-22, 56, 0.02), (66, 26, 0.04)), b.box((-100, 20, 0.02), (36, 84, 0.04))))
    single("Gravel yard", "Gravel", "Campus / terrain", lambda b: b.box((-108, -40, 0.03), (22, 60, 0.02)))

    def roads(b):
        for r in lay["roads"]:
            b.box((r["center"][0], r["center"][1], 0.05), (r["size"][0], r["size"][1], 0.06))
        p = lay["parking"]
        b.box((p["center"][0], p["center"][1], 0.05), (p["size"][0], p["size"][1], 0.06))
    single("Roads & parking", "Asphalt", "Campus / roads & parking", roads)

    def markings(b):
        for r in lay["roads"]:
            (cx, cy), (w, h) = r["center"], r["size"]
            if w > h:
                for x in range(int(cx - w / 2) + 2, int(cx + w / 2) - 2, 6):
                    b.box((x, cy, 0.085), (3.0, 0.15, 0.01))
            else:
                for y in range(int(cy - h / 2) + 2, int(cy + h / 2) - 2, 6):
                    b.box((cx, y, 0.085), (0.15, 3.0, 0.01))
        p = lay["parking"]
        (cx, cy), (w, h) = p["center"], p["size"]
        for row in range(3):
            y = cy - h / 2 + 5 + row * 10
            for i in range(24):
                b.box((cx - w / 2 + 3 + i * 2.6, y, 0.085), (0.12, 5.0, 0.01))
        for x in (-3.0, -1.5, 0.0, 1.5, 3.0):  # zebra crossing to the office
            b.box((-22 + x, 34, 0.085), (0.8, 7.5, 0.01))
    single("Road markings", "Line white", "Campus / roads & parking", markings)

    def curbs(b):
        for r in lay["roads"]:
            (cx, cy), (w, h) = r["center"], r["size"]
            if w > h:
                for s in (-1, 1):
                    b.box((cx, cy + s * (h / 2 + 0.15), 0.08), (w, 0.3, 0.16))
            else:
                for s in (-1, 1):
                    b.box((cx + s * (w / 2 + 0.15), cy, 0.08), (0.3, h, 0.16))
    single("Curbs", "Concrete", "Campus / roads & parking", curbs)

    def fence(b):
        x0, x1, y0, y1 = sx[0] + 2, sx[1] - 2, sy[0] + 2, sy[1] - 2
        for x in range(int(x0), int(x1) + 1, 3):
            for y in (y0, y1):
                b.box((x, y, 1.1), (0.08, 0.08, 2.2))
        for y in range(int(y0), int(y1) + 1, 3):
            for x in (x0, x1):
                if x == x1 and -22 < y < 0:
                    continue
                b.box((x, y, 1.1), (0.08, 0.08, 2.2))
        for z in (0.3, 1.2, 2.1):
            b.box(((x0 + x1) / 2, y0, z), (x1 - x0, 0.04, 0.04))
            b.box(((x0 + x1) / 2, y1, z), (x1 - x0, 0.04, 0.04))
            b.box((x0, (y0 + y1) / 2, z), (0.04, y1 - y0, 0.04))
            b.box((x1, (y0 - 22) / 2, z), (0.04, -22 - y0, 0.04))
            b.box((x1, y1 / 2, z), (0.04, y1, 0.04))
    single("Perimeter fence", "Structural steel", "Campus / roads & parking", fence)

    def lamps(b):
        for x in range(-120, 125, 24):
            for y in (-39.5, 39.5):
                b.cylinder((x, y, 4.5), 0.09, 9.0, 8)
                b.box((x, y + (0.8 if y < 0 else -0.8), 9.0), (0.3, 1.8, 0.15))
    single("Street lights", "Structural steel", "Campus / roads & parking", lamps)


def trees(lab):
    variants = []
    for v in range(4):
        b = Builder()
        b.sphere((0, 0, 4.6), 2.6, 2, 0.18, 1.05)
        b.sphere((0.9, 0.4, 5.8), 1.8, 2, 0.2)
        b.sphere((-0.7, -0.6, 5.5), 1.7, 2, 0.2)
        canopy = b.mesh(f"Tree canopy {v}")
        canopy.materials.append(MATS["Foliage"])
        variants.append(canopy)
    trunk = Builder().cylinder((0, 0, 1.6), 0.22, 3.2, 10, radius2=0.14).mesh("Tree trunk")
    trunk.materials.append(MATS["Bark"])
    for i, (x, y, s) in enumerate(lab["layout"]["trees"]):
        t = obj(f"Tree {i + 1:03d}", trunk, None, "Vegetation", (x, y, 0))
        c = obj(f"Tree {i + 1:03d} / canopy", variants[i % 4], None, "Vegetation", (0, 0, 0), t)
        t.scale = (s, s, s)
        t.rotation_euler.z = RNG.uniform(0, 2 * math.pi)
        c["rr_id"] = c.name
    hedge = Builder()
    for x in range(-44, 0, 2):
        hedge.box((x, 45.5, 0.5), (2.1, 1.2, 1.0), bevel=0.3)
    obj("Office hedge", hedge.mesh("Office hedge"), "Foliage", "Vegetation")


# ----------------------------------------------------------------------------- buildings
def hall():
    x0, x1 = HALL["x"]
    y0, y1 = HALL["y"]
    h = HALL["h"]
    shell, cut = "Buildings / hall shell", "Buildings / hall cutaway"
    single("Hall floor slab", "Epoxy floor", shell, lambda b: b.box(((x0 + x1) / 2, 0, 0.1), (x1 - x0, y1 - y0, 0.2)))

    def north_west_walls(b):
        b.box(((x0 + x1) / 2, y1, h / 2), (x1 - x0, 0.3, h))
        b.box((x0, 0, h / 2), (0.3, y1 - y0, h))
        b.box((x1, (y1 + 1.0) / 2, h / 2), (0.3, y1 - 1.0, h))  # east wall north of AMR door
        b.box((x1, -16.0, h / 2), (0.3, 12.0, h))
        b.box((x1, -4.5, 9.5), (0.3, 11, 5))  # over the AMR and dock opening
    single("Hall walls", "Hall cladding", shell, north_west_walls)
    single("Hall south wall", "Hall cladding", cut, lambda b: b.box(((x0 + x1) / 2, y0, h / 2), (x1 - x0, 0.3, h)))

    def plinth(b):
        for y in (y0, y1):
            b.box(((x0 + x1) / 2, y, 0.6), (x1 - x0 + 0.4, 0.45, 1.2))
        b.box((x0, 0, 0.6), (0.45, y1 - y0, 1.2))
    single("Hall plinth", "Concrete", shell, plinth)

    def window_bands(b):
        b.box(((x0 + x1) / 2, y1 + 0.02, 9.2), (x1 - x0 - 2, 0.3, 1.6))
        b.box((x0 - 0.02, 0, 9.2), (0.3, y1 - y0 - 2, 1.6))
    single("Hall window bands", "Curtain glass", shell, window_bands)
    single("Hall south window band", "Curtain glass", cut,
           lambda b: b.box(((x0 + x1) / 2, y0 - 0.02, 9.2), (x1 - x0 - 2, 0.3, 1.6)))

    def pilasters(b):
        for x in range(int(x0), int(x1) + 1, 10):
            b.box((x, y1 + 0.25, h / 2), (0.5, 0.4, h + 0.3))
    single("Hall pilasters", "Structural steel", shell, pilasters)

    def roof(b):
        b.box(((x0 + x1) / 2, 0, h + 0.2), (x1 - x0 + 0.6, y1 - y0 + 0.6, 0.4))
        for s in (-1, 1):
            b.box(((x0 + x1) / 2, s * (y1 + 0.2), h + 0.7), (x1 - x0 + 0.6, 0.2, 0.7))
        b.box((x0 - 0.2, 0, h + 0.7), (0.2, y1 - y0 + 0.6, 0.7))
        b.box((x1 + 0.2, 0, h + 0.7), (0.2, y1 - y0 + 0.6, 0.7))
    single("Hall roof", "Roof sheet", cut, roof)

    def monitors(b):
        for y in (-15, -5, 5, 15):
            b.box(((x0 + x1) / 2, y, h + 1.2), (x1 - x0 - 12, 3.0, 1.6))
    single("Hall roof monitors", "Glass", cut, monitors)
    single("Hall roof monitor caps", "Roof sheet", cut, lambda b: [
        b.box(((x0 + x1) / 2, y, h + 2.1), (x1 - x0 - 11, 3.6, 0.2)) for y in (-15, -5, 5, 15)])

    def structure(b):
        for x in range(int(x0) + 10, int(x1), 10):
            for y in (-16.0, 16.0):
                b.box((x, y, h / 2), (0.45, 0.45, h))
        for y in (-16.0, 16.0):
            b.box(((x0 + x1) / 2, y, 8.6), (x1 - x0, 0.5, 0.6))  # crane runway beams
    single("Hall steel frame", "Structural steel", shell, structure)
    single("Hall roof girders", "Structural steel", cut, lambda b: [
        b.box((x, 0, h - 0.6), (0.35, y1 - y0, 0.9)) for x in range(int(x0) + 10, int(x1), 10)])
    single("Bridge crane", "Safety yellow", shell, lambda b: (
        b.box((-26, 0, 8.9), (1.0, 32.6, 0.8), bevel=0.05), b.box((-26, 2, 8.2), (1.4, 1.6, 0.8), bevel=0.05)))

    def lights(b):
        for x in range(int(x0) + 5, int(x1), 10):
            for y in (-10, 0, 10):
                b.cylinder((x, y, h - 1.4), 0.35, 0.12, 20)
    single("High-bay lights", "High-bay light", cut, lights)

    def floor_lines(b):
        for y in (-3.2, 3.2, -11.5, 11.5):
            b.box(((x0 + x1) / 2, y, 0.205), (x1 - x0 - 4, 0.12, 0.01))
        for sx, sy, w, d in ((-60, 0, 7, 5), (-44, 7, 7.5, 5), (-44, -7, 7.5, 5), (-26, 0, 10, 9), (-8, 0, 9, 5),
                             (8, 0, 7, 5), (17.3, -5, 8.5, 6)):
            for s in (-1, 1):
                b.box((sx, sy + s * d / 2, 0.206), (w, 0.1, 0.01))
                b.box((sx + s * w / 2, sy, 0.206), (0.1, d, 0.01))
    single("Floor safety lines", "Safety yellow", shell, floor_lines)
    single("Walkways", "Floor green", shell, lambda b: [
        b.box(((x0 + x1) / 2, y, 0.203), (x1 - x0 - 4, 2.2, 0.01)) for y in (-14.5, 14.5)])

    def doors(b):
        for x in (-50, -30, -10, 10):
            b.box((x, y1 + 0.18, 2.5), (4.0, 0.1, 5.0))
        b.box((x1 + 0.18, -5, 2.6), (0.1, 3.0, 0.1))
    single("Dock doors", "Machine grey", shell, doors)


def warehouse(lab):
    b0 = next(b for b in lab["layout"]["buildings"] if b["id"] == "warehouse")
    (cx, cy), (w, d), h = b0["center"], b0["size"], b0["height"]
    coll = "Buildings / campus"

    def walls(b):
        b.box((cx, cy + d / 2, h / 2), (w, 0.3, h))
        b.box((cx, cy - d / 2, h / 2), (w, 0.3, h))
        b.box((cx + w / 2, cy, h / 2), (0.3, d, h))
        b.box((cx - w / 2, cy + (d / 2 + 2) / 2, h / 2), (0.3, d / 2 - 2, h))
        b.box((cx - w / 2, cy - (d / 2 + 2) / 2, h / 2), (0.3, d / 2 - 2, h))
        b.box((cx - w / 2, cy, (h + 3.2) / 2), (0.3, 4, h - 3.2))
    single("Warehouse walls", "Warehouse cladding", coll, walls)
    single("Warehouse roof", "Roof sheet", coll, lambda b: (
        b.box((cx, cy, h + 0.2), (w + 0.6, d + 0.6, 0.4)), b.box((cx, cy, h + 0.9), (w + 0.6, d + 0.6, 0.12))))
    single("Warehouse floor", "Concrete", coll, lambda b: b.box((cx, cy, 0.1), (w, d, 0.2)))
    single("Warehouse accent band", "Accent teal", coll, lambda b: [
        b.box((cx, cy + s * (d / 2 + 0.05), h - 1.2), (w, 0.3, 1.0)) for s in (-1, 1)])

    def docks(b):
        for i in range(5):
            y = cy - d / 2 + 5 + i * 6.5
            b.box((cx + w / 2 + 0.2, y, 2.3), (0.1, 3.2, 3.6))
            b.box((cx + w / 2 + 0.8, y, 0.6), (1.4, 3.6, 1.2))
    single("Warehouse dock doors", "Machine grey", coll, docks)

    def racks(b):
        for i in range(5):
            x = cx - w / 2 + 12 + i * 5.5
            for y in range(int(cy - d / 2 + 3), int(cy + d / 2 - 3), 3):
                b.box((x, y, 4.5), (0.1, 0.1, 9))
            for z in (1.5, 3.5, 5.5, 7.5):
                b.box((x, cy, z), (1.2, d - 6, 0.12))
    single("Warehouse racks", "Rack blue", coll, racks)
    single("Warehouse stock", "Cardboard", coll, lambda b: [
        b.box((cx - w / 2 + 12 + i * 5.5, y + 0.5, z + 0.55), (1.0, 1.1, 0.9))
        for i in range(5) for y in range(int(cy - d / 2 + 3), int(cy + d / 2 - 4), 3)
        for z in (1.5, 3.5, 5.5) if (i + y + int(z)) % 3])
    # Trucks at the docks.
    trailer = Builder().box((0, 0, 2.55), (13.6, 2.55, 2.9), bevel=0.05).mesh("Trailer box")
    trailer.materials.append(MATS["Truck white"])
    chassis = Builder()
    for x in (-5.4, -4.1, 4.2):
        for y in (-1.05, 1.05):
            chassis.cylinder((x, y, 0.5), 0.5, 0.35, 16, "Y")
    chassis.box((0, 0, 1.05), (13.4, 1.0, 0.25))
    chassis = chassis.mesh("Trailer chassis")
    chassis.materials.append(MATS["Rubber"])
    for i, y in enumerate((cy - d / 2 + 5, cy - d / 2 + 11.5, cy - d / 2 + 24.5)):
        t = obj(f"Truck {i + 1}", trailer, None, coll, (cx + w / 2 + 8.6, y, 0))
        obj(f"Truck {i + 1} / chassis", chassis, None, coll, (0, 0, 0), t)


def office(lab):
    b0 = next(b for b in lab["layout"]["buildings"] if b["id"] == "office")
    (cx, cy), (w, d), h = b0["center"], b0["size"], b0["height"]
    coll = "Buildings / campus"
    floors = 4
    single("Office slabs", "Concrete", coll, lambda b: [
        b.box((cx, cy, i * h / floors + 0.2), (w + 0.8, d + 0.8, 0.4)) for i in range(floors + 1)])
    single("Office curtain wall", "Curtain glass", coll, lambda b: b.box((cx, cy, h / 2), (w - 0.2, d - 0.2, h)))

    def mullions(b):
        for i in range(int(w / 1.5) + 1):
            x = cx - w / 2 + i * 1.5
            for s in (-1, 1):
                b.box((x, cy + s * (d / 2 + 0.05), h / 2), (0.08, 0.14, h))
        for i in range(int(d / 1.5) + 1):
            y = cy - d / 2 + i * 1.5
            for s in (-1, 1):
                b.box((cx + s * (w / 2 + 0.05), y, h / 2), (0.14, 0.08, h))
    single("Office mullions", "Mullion", coll, mullions)
    single("Office lit interiors", "Warm window", coll, lambda b: [
        b.box((cx, cy, i * h / floors + 2.2), (w - 1.2, d - 1.2, 0.05)) for i in range(floors - 1)])
    single("Twin operations video wall", "Screen", coll, lambda b: b.box((cx + 18, cy - d / 2 + 1.2, 13.6), (14, 0.2, 2.6)))
    single("Office roof plant", "Machine grey", coll, lambda b: (
        b.box((cx - 12, cy, h + 1.2), (8, 5, 2.0), bevel=0.1), b.box((cx + 10, cy + 2, h + 0.9), (6, 4, 1.4), bevel=0.1),
        b.box((cx, cy, h + 0.8), (w + 0.8, 0.2, 0.2))))
    single("Office entrance canopy", "Structural steel", coll, lambda b: (
        b.box((cx, cy - d / 2 - 3, 4.2), (14, 6, 0.3)), b.cylinder((cx - 6, cy - d / 2 - 5.5, 2.1), 0.15, 4.2, 12),
        b.cylinder((cx + 6, cy - d / 2 - 5.5, 2.1), 0.15, 4.2, 12)))
    font = bpy.data.curves.new("Office sign", "FONT")
    font.body = "PLANT 01 · DIGITAL TWIN OPERATIONS"
    font.size, font.align_x, font.extrude = 1.1, "CENTER", 0.05
    sign = bpy.data.objects.new("Office sign", font)
    sign.location = (cx, cy - d / 2 - 0.35, h - 0.9)
    sign.rotation_euler = (math.pi / 2, 0, 0)
    font.materials.append(MATS["Screen"])
    collection(coll).objects.link(sign)
    sign["rr_id"] = sign.name

    gate = next(b for b in lab["layout"]["buildings"] if b["id"] == "gate")
    (gx, gy), (gw, gd), gh = gate["center"], gate["size"], gate["height"]
    single("Gatehouse", "Machine white", coll, lambda b: (b.box((gx, gy, gh / 2), (gw, gd, gh), bevel=0.1),
                                                           b.box((gx, gy, gh + 0.2), (gw + 1.6, gd + 1.6, 0.3))))
    single("Gatehouse glazing", "Curtain glass", coll, lambda b: b.box((gx, gy, gh * 0.6), (gw + 0.05, gd + 0.05, 1.4)))
    single("Gate barrier", "Reject red", coll, lambda b: b.box((gx, gy + 11, 1.0), (0.15, 9, 0.15)))


def energy_center(lab):
    b0 = next(b for b in lab["layout"]["buildings"] if b["id"] == "energy")
    (cx, cy), (w, d), h = b0["center"], b0["size"], b0["height"]
    u = lab["layout"]["utilities"]
    coll = "Energy"
    single("Energy center building", "Concrete", coll, lambda b: (b.box((cx, cy, h / 2), (w, d, h)),
                                                                  b.box((cx, cy, h + 0.15), (w + 0.4, d + 0.4, 0.3))))
    single("Energy center louvres", "Machine grey", coll, lambda b: [
        b.box((cx - w / 2 + 3 + i * 4, cy - d / 2 - 0.05, h * 0.6), (2.4, 0.1, 2.4)) for i in range(5)])
    tx, ty = u["transformer"]

    def transformers(b):
        for dx in (-4, 4):
            b.box((tx + dx, ty, 1.6), (3.2, 2.4, 3.2), bevel=0.05)
            for i in range(9):
                b.box((tx + dx - 1.8, ty - 1.0 + i * 0.25, 1.5), (0.4, 0.05, 2.4))
            for i in range(3):
                b.cylinder((tx + dx - 0.9 + i * 0.9, ty, 3.8), 0.18, 1.2, 12)
    single("Transformers", "Transformer grey", coll, transformers)

    def gantry(b):
        for dx in (-8, 8):
            for dy in (-6, 6):
                b.box((tx + dx, ty + dy, 5), (0.35, 0.35, 10))
        for dy in (-6, 6):
            b.box((tx, ty + dy, 9.8), (16.4, 0.3, 0.4))
    single("Substation gantry", "Structural steel", coll, gantry)
    single("Substation fence", "Fence mesh", coll, lambda b: [
        b.box((tx + dx, ty, 1.2), (0.05, 16, 2.4)) for dx in (-10, 10)] + [
        b.box((tx, ty + dy, 1.2), (20, 0.05, 2.4)) for dy in (-8, 8)])

    def chillers(b):
        for x, y in u["chillers"]:
            b.box((x, y, 1.4), (10, 2.6, 2.8), bevel=0.05)
    single("Chillers", "Machine white", coll, chillers)
    single("Chiller fans", "Machine grey", coll, lambda b: [
        b.cylinder((x - 3.75 + i * 2.5, y, 2.85), 0.95, 0.12, 24) for x, y in u["chillers"] for i in range(4)])

    def towers(b):
        for x, y in u["cooling_towers"]:
            b.box((x, y, 2.2), (4.5, 4.5, 4.4), bevel=0.05)
            b.cylinder((x, y, 4.9), 1.6, 1.0, 24, radius2=1.8)
    single("Cooling towers", "Tank white", coll, towers)

    def pipes(b):
        for y in (-20.0, -8.0):
            b.cylinder(((-70 - 93) / 2, y + 0.8, 2.6), 0.22, 93 - 70, 16, "X")
            b.cylinder(((-70 - 93) / 2, y - 0.8, 2.6), 0.22, 93 - 70, 16, "X")
        for x in (-90, -84, -78, -72):
            b.box((x, -14, 1.3), (0.2, 16, 0.2))
            b.box((x, -14 + 7.9, 1.3), (0.2, 0.2, 2.6))
    single("Chilled water pipes", "Stainless", coll, pipes)
    wx, wy = u["water_tower"]

    def water_tower(b):
        for a in range(6):
            ang = 2 * math.pi * a / 6
            b.cylinder((wx + 4.6 * math.cos(ang), wy + 4.6 * math.sin(ang), 11), 0.3, 22, 10)
        b.cylinder((wx, wy, 11), 0.6, 22, 12)
        b.torus((wx, wy, 14), 4.6, 0.12, 32, 6)
    single("Water tower legs", "Structural steel", coll, water_tower)
    single("Water tower tank", "Tank white", coll, lambda b: (b.sphere((wx, wy, 25.5), 6.0, 3, 0, 0.72),
                                                              b.cylinder((wx, wy, 23.5), 6.0, 3, 32)), smooth=True)


def parking(lab):
    p = lab["layout"]["parking"]
    (cx, cy), (w, d) = p["center"], p["size"]
    coll = "Energy"

    def canopies(b):
        for row in range(p["canopy_rows"]):
            y = cy - d / 2 + 5 + row * 10
            for i in range(11):
                b.box((cx - w / 2 + 3 + i * 5.9, y - 1.8, 1.7), (0.25, 0.25, 3.4))
            b.box((cx, y - 1.8, 3.35), (w - 2, 0.35, 0.3))
    single("PV canopy frames", "Structural steel", coll, canopies)

    def panels(b):
        for row in range(p["canopy_rows"]):
            y = cy - d / 2 + 5 + row * 10
            for i in range(20):
                x = cx - w / 2 + 2.5 + i * 3.0
                m = Matrix.Translation((x, y, 3.8)) @ Matrix.Rotation(math.radians(10), 4, "X")
                v = [m @ Vector(c) for c in ((-1.45, -3.0, 0), (1.45, -3.0, 0), (1.45, 3.0, 0), (-1.45, 3.0, 0))]
                b.quad(*v)
    single("PV canopy modules", "PV module", coll, panels)
    body = Builder().box((0, 0, 0.75), (4.4, 1.8, 0.8), bevel=0.25).box((-0.2, 0, 1.35), (2.4, 1.6, 0.6), bevel=0.25)
    body = body.mesh("Car body")
    body.materials.append(MATS["Car paint"])
    glass = Builder().box((-0.2, 0, 1.38), (2.3, 1.65, 0.45), bevel=0.15).mesh("Car glass")
    glass.materials.append(MATS["Curtain glass"])
    palette = ((0.8, 0.8, 0.82), (0.05, 0.05, 0.06), (0.35, 0.37, 0.4), (0.55, 0.05, 0.04), (0.05, 0.15, 0.4), (0.9, 0.9, 0.9))
    n = 0
    for row in range(3):
        y = cy - d / 2 + 5 + row * 10
        for i in range(23):
            if RNG.random() < 0.3:
                continue
            n += 1
            car = obj(f"Car {n:02d}", body, None, "Campus / roads & parking",
                      (cx - w / 2 + 4.3 + i * 2.6, y + RNG.choice((-0.2, 0.2)), 0))
            car.rotation_euler.z = math.pi / 2 + RNG.choice((0, math.pi))
            car.color = (*RNG.choice(palette), 1)
            obj(f"Car {n:02d} / glass", glass, None, "Campus / roads & parking", (0, 0, 0), car)
    pedestal = Builder().box((0, 0, 0.8), (0.5, 0.35, 1.6), bevel=0.05).mesh("Charger pedestal")
    pedestal.materials.append(MATS["Machine white"])
    ring = Builder().torus((0, 0, 0), 0.22, 0.04, 24, 6).mesh("Charger ring")
    ring.materials.append(MATS["Status light"])
    for i, (x, y) in enumerate(p["chargers"]):
        ped = obj(f"EV charger {i + 1}", pedestal, None, coll, (x, y, 0))
        r = obj(f"EV charger {i + 1} / ring", ring, None, coll, (x, y - 0.19, 1.2))
        r.rotation_euler.x = math.pi / 2
        ped["rr_id"] = ped.name


# ----------------------------------------------------------------------------- production line
def stack_light(name, x, y, h, coll="Production line"):
    single(name + " / column", "Machine grey", coll, lambda b: (
        b.cylinder((x, y, h + 0.35), 0.035, 0.7, 10), b.cylinder((x, y, h + 0.78), 0.09, 0.18, 16)))
    return single(name + " / beacon", "Status light", coll, lambda b: b.cylinder((0, 0, 0), 0.09, 0.32, 16),
                  location=(x, y, h + 1.03))


def twin_ring(sid, x, y, z):
    return single(f"Twin {sid} / ring", "Twin ring", "Digital twin overlay",
                  lambda b: b.torus((0, 0, 0), 1.25, 0.05, 64, 8), location=(x, y, z))


def cnc(station):
    sid, (x, y), (sx, sy, sz) = station["id"], station["position"], station["size"]
    coll = "Production line"
    face = -1 if y > 0 else 1  # the door faces the line centreline
    single(f"Station {sid} / enclosure", "Machine white", coll, lambda b: (
        b.box((x, y - face * 0.3, sz / 2 + 0.15), (sx - 0.6, sy - 0.6, sz - 0.3), bevel=0.12),
        b.box((x + sx / 2 - 0.2, y, sz * 0.62), (0.4, sy - 0.4, sz * 0.9), bevel=0.05)))
    single(f"Station {sid} / base", "Machine grey", coll, lambda b: (
        b.box((x, y, 0.2), (sx, sy, 0.4), bevel=0.04), b.box((x - sx / 2 - 0.5, y, 0.45), (1.0, sy - 1.2, 0.7), bevel=0.04)))
    single(f"Station {sid} / accent", "Accent teal", coll, lambda b: b.box(
        (x, y + face * (sy / 2 - 0.29), sz - 0.2), (sx - 0.7, 0.04, 0.35)))
    single(f"Station {sid} / door window", "Glass", coll, lambda b: b.box(
        (x - 0.4, y + face * (sy / 2 - 0.3), sz * 0.52), (2.2, 0.05, 1.3)))
    light = single(f"Station {sid} / chamber light", "Chamber light", coll, lambda b: b.box(
        (0, 0, 0), (2.0, 0.05, 0.08)), location=(x - 0.4, y + face * 0.2, sz * 0.8))
    light["rr_id"] = light.name
    single(f"Station {sid} / spindle head", "Stainless", coll, lambda b: b.box((x - 0.4, y, sz * 0.78), (0.6, 0.6, 0.5)))
    single(f"Station {sid} / spindle", "Stainless", coll, lambda b: (
        b.cylinder((0, 0, 0), 0.12, 0.7, 16), b.box((0.1, 0, -0.2), (0.08, 0.05, 0.3))),
        location=(x - 0.4, y, sz * 0.55))
    single(f"Station {sid} / panel", "Machine grey", coll, lambda b: b.box(
        (x + sx / 2 + 0.3, y + face * (sy / 2 - 0.2), 1.2), (0.5, 0.35, 1.4), bevel=0.03))
    single(f"Station {sid} / panel screen", "Screen", coll, lambda b: b.box(
        (x + sx / 2 + 0.3, y + face * (sy / 2 - 0.01), 1.55), (0.4, 0.02, 0.3)))
    stack_light(f"Station {sid}", x + sx / 2 - 0.3, y - face * (sy / 2 - 0.4), sz)
    twin_ring(sid, x, y, sz + 2.2)


def robot(name, base, yaw, coll, parent_coll="Production line"):
    """Six-joint stylized industrial arm with a correct parent hierarchy."""
    j = []
    j1 = single(f"{name} / J1", "Robot orange", coll, lambda b: (
        b.cylinder((0, 0, 0.35), 0.42, 0.7, 24), b.box((0, 0, 0.8), (0.7, 0.6, 0.4), bevel=0.08)), location=base)
    j1.rotation_euler.z = yaw
    j.append(j1)
    single(f"{name} / base plate", "Machine grey", coll, lambda b: b.cylinder((base[0], base[1], 0.05), 0.55, 0.1, 24))
    j2 = single(f"{name} / J2", "Robot orange", coll, lambda b: (
        b.box((0, 0, 0.6), (0.34, 0.36, 1.3), bevel=0.08), b.cylinder((0, 0, 0), 0.22, 0.5, 20, "Y")),
        location=(0, 0, 0.95), parent=j1)
    j3 = single(f"{name} / J3", "Robot orange", coll, lambda b: (
        b.box((0.55, 0, 0), (1.2, 0.3, 0.3), bevel=0.07), b.cylinder((0, 0, 0), 0.2, 0.45, 20, "Y")),
        location=(0, 0, 1.25), parent=j2)
    j4 = single(f"{name} / J4", "Machine grey", coll, lambda b: b.cylinder((0.12, 0, 0), 0.13, 0.25, 16, "X"),
                location=(1.15, 0, 0), parent=j3)
    j5 = single(f"{name} / J5", "Robot orange", coll, lambda b: b.box((0.12, 0, 0), (0.24, 0.2, 0.2), bevel=0.04),
                location=(0.25, 0, 0), parent=j4)
    j6 = single(f"{name} / J6", "Stainless", coll, lambda b: (
        b.cylinder((0.1, 0, 0), 0.07, 0.2, 12, "X"), b.cylinder((0.3, 0, -0.08), 0.03, 0.35, 8, "X")),
        location=(0.24, 0, 0), parent=j5)
    j += [j2, j3, j4, j5, j6]
    for k, joint in enumerate(j):
        angles = weld_joints(0.0, "AB".index(name[-1]))
        joint.rotation_euler[2 if k in (0, 5) else 1] = angles[k] + (yaw if k == 0 else 0)
    return j


def weld_cell(station):
    x, y = station["position"]
    sx, sy, sz = station["size"]
    coll = "Production line"

    def fence(b):
        for i in range(10):
            px = x - sx / 2 + i * sx / 9
            for s in (-1, 1):
                b.box((px, y + s * sy / 2, 1.1), (0.08, 0.08, 2.2))
        for s in (-1, 1):
            for py in (y - sy / 2, y - sy / 4, y + sy / 4, y + sy / 2):
                b.box((x + s * sx / 2, py, 1.1), (0.08, 0.08, 2.2))
        for z in (0.15, 2.15):
            for s in (-1, 1):
                b.box((x, y + s * sy / 2, z), (sx, 0.06, 0.06))
    single("Station weld / fence posts", "Safety yellow", coll, fence)
    single("Station weld / fence mesh", "Fence mesh", coll, lambda b: (
        [b.box((x, y + s * sy / 2, 1.15), (sx, 0.02, 1.9)) for s in (-1, 1)],
        [b.box((x + s * sx / 2, y + (sy / 4 + sy / 2) / 2 * t, 1.15), (0.02, sy / 4, 1.9)) for s in (-1, 1) for t in (-1, 1)]))
    single("Station weld / positioner", "Machine grey", coll, lambda b: (
        b.box((x, y, 0.45), (2.4, 1.4, 0.9), bevel=0.05), b.cylinder((x, y, 1.0), 0.8, 0.2, 32)))
    single("Station weld / fixture", "Stainless", coll, lambda b: (
        b.box((x, y, 1.25), (1.2, 0.8, 0.3)), b.box((x, y, 1.5), (0.3, 0.9, 0.25))))
    single("Station weld / arc", "Arc", coll, lambda b: b.sphere((0, 0, 0), 0.09, 1), location=(x, y, 1.72))
    robot("Weld robot A", (x - 0.3, y + 2.3, 0.1), WELD_ROBOT_YAW[0], coll)
    robot("Weld robot B", (x + 0.3, y - 2.3, 0.1), WELD_ROBOT_YAW[1], coll)
    single("Station weld / fume hood", "Machine grey", coll, lambda b: (
        b.box((x, y, 4.4), (3.0, 2.0, 0.6), bevel=0.1), b.cylinder((x, y, 7.8), 0.3, 6.4, 16)))
    stack_light("Station weld", x + sx / 2 - 0.3, y + sy / 2 - 0.3, 2.3)
    twin_ring("weld", x, y, 6.0)


def kitting(station):
    x, y = station["position"]
    coll = "Production line"

    def racks(b):
        for s in (-1, 1):
            for dx in (-2.4, -0.8, 0.8, 2.4):
                b.box((x + dx, y + s * 1.6, 1.3), (0.08, 0.9, 2.6))
            for z in (0.4, 1.1, 1.8, 2.5):
                b.box((x, y + s * 1.6, z), (4.9, 0.95, 0.06))
    single("Station kitting / racks", "Rack blue", coll, racks)
    single("Station kitting / bins", "Tote blue", coll, lambda b: [
        b.box((x - 2.0 + i * 0.8, y + s * 1.6, z + 0.17), (0.6, 0.8, 0.28), bevel=0.02)
        for s in (-1, 1) for i in range(6) for z in (0.4, 1.1, 1.8)])
    single("Station kitting / pick table", "Stainless", coll, lambda b: (
        b.box((x, y, 0.9), (2.8, 1.0, 0.06)), [b.box((x + dx, y + dy, 0.45), (0.06, 0.06, 0.9))
                                              for dx in (-1.3, 1.3) for dy in (-0.4, 0.4)]))
    single("Station kitting / put-to-light", "Screen", coll, lambda b: b.box((x, y, 2.9), (4.8, 0.05, 0.12)))
    stack_light("Station kitting", x + 2.8, y + 0.6, 1.9)
    twin_ring("kitting", x, y, 4.2)


def worker(name, x, y, yaw, coll):
    w = single(name, "Hi-vis", coll, lambda b: (
        b.cylinder((0, 0, 1.15), 0.2, 0.7, 12), b.cylinder((0.0, 0, 0.45), 0.14, 0.9, 10)), location=(x, y, 0.2))
    w.rotation_euler.z = yaw
    single(name + " / head", "Skin", coll, lambda b: b.sphere((0, 0, 1.68), 0.13, 2), parent=w)
    single(name + " / helmet", "Machine white", coll, lambda b: b.sphere((0, 0, 1.75), 0.14, 2, 0, 0.6), parent=w)
    return w


def assembly(station):
    x, y = station["position"]
    sx, sy, sz = station["size"]
    coll = "Production line"
    single("Station assembly / benches", "Stainless", coll, lambda b: (
        b.box((x, y, 0.95), (sx, 1.4, 0.08)),
        [b.box((x + dx, y + dy, 0.47), (0.08, 0.08, 0.95)) for dx in (-3.8, 0, 3.8) for dy in (-0.6, 0.6)]))
    single("Station assembly / tool rail", "Machine grey", coll, lambda b: (
        b.box((x, y + 0.9, 2.3), (sx, 0.12, 0.12)), [b.box((x + dx, y + 0.9, 1.6), (0.1, 0.1, 1.4)) for dx in (-3.8, 3.8)]))
    single("Station assembly / fixtures", "Accent teal", coll, lambda b: [
        b.box((x + dx, y, 1.1), (0.9, 0.7, 0.22), bevel=0.03) for dx in (-2.5, 0, 2.5)])
    for i, dx in enumerate((-1.3, 1.3)):
        base = (x + dx, y + 0.35, 0.99)
        single(f"Station assembly / cobot {i + 1}", "Machine white", coll, lambda b, base=base: (
            b.cylinder(base, 0.14, 0.2, 16), b.cylinder((base[0], base[1], base[2] + 0.4), 0.08, 0.6, 12),
            b.box((base[0] + 0.25, base[1] - 0.1, base[2] + 0.72), (0.55, 0.12, 0.12), bevel=0.04)))
    for i, dx in enumerate((-2.5, 0, 2.5)):
        worker(f"Operator assembly {i + 1}", x + dx, y - 1.4, math.pi / 2, coll)
    stack_light("Station assembly", x + sx / 2 + 0.2, y + 0.8, 1.0)
    twin_ring("assembly", x, y, 3.6)


def inspection(station):
    x, y = station["position"]
    sx, sy, sz = station["size"]
    coll = "Production line"
    single("Station inspect / portal", "Machine white", coll, lambda b: (
        [b.box((x, y + s * 1.4, sz / 2), (1.6, 0.3, sz), bevel=0.05) for s in (-1, 1)],
        b.box((x, y, sz), (1.8, 3.1, 0.35), bevel=0.05)))
    single("Station inspect / light bar", "High-bay light", coll, lambda b: b.box((x, y, sz - 0.25), (1.2, 2.4, 0.06)))
    single("Station inspect / camera", "Machine grey", coll, lambda b: [
        b.cylinder((x + dx, y, sz - 0.35), 0.08, 0.25, 12) for dx in (-0.4, 0.4)])
    single("Station inspect / reject bin", "Reject red", coll, lambda b: b.box((x + 1.8, y + 1.9, 0.5), (1.0, 1.0, 1.0), bevel=0.05))
    single("Station inspect / console", "Machine grey", coll, lambda b: b.box((x - 2.2, y - 1.8, 0.7), (0.9, 0.6, 1.4), bevel=0.04))
    single("Station inspect / console screen", "Screen", coll, lambda b: b.box((x - 2.2, y - 1.49, 1.15), (0.8, 0.02, 0.45)))
    worker("Operator inspection", x - 2.2, y - 2.5, math.pi / 2, coll)
    stack_light("Station inspect", x + sx / 2, y - 1.6, 1.4)
    twin_ring("inspect", x, y, sz + 2.0)


def hall_props():
    """Static context (not simulated): storage, workshop, break area, andon boards."""
    coll = "Hall context (static)"

    def racking(b):
        for i in range(9):
            x = -64 + i * 9.5
            for dx in (0.0, 8.8):
                for dy in (0.0, 1.1):
                    b.box((x + dx, 18.2 + dy, 3.0), (0.1, 0.1, 6.0))
            for z in (0.15, 2.0, 4.0):
                for dy in (0.0, 1.1):
                    b.box((x + 4.4, 18.2 + dy, z), (8.9, 0.1, 0.14))
    single("Pallet racking", "Rack blue", coll, racking)
    single("Racking beams", "Hi-vis", coll, lambda b: [
        b.box((-64 + i * 9.5 + 4.4, 18.15, z), (8.9, 0.06, 0.12)) for i in range(9) for z in (2.0, 4.0)])
    single("Racked stock", "Cardboard", coll, lambda b: [
        b.box((-64 + i * 9.5 + 1.2 + j * 2.2, 18.75, z + 0.62), (1.8, 1.0, 1.1), bevel=0.02)
        for i in range(9) for j in range(4) for z in (0.25, 2.1, 4.1) if (i * 7 + j * 3 + int(z)) % 4])
    single("Racked pallets", "Pallet wood", coll, lambda b: [
        b.box((-64 + i * 9.5 + 1.2 + j * 2.2, 18.75, z + 0.03), (1.8, 1.1, 0.14))
        for i in range(9) for j in range(4) for z in (0.25, 2.1, 4.1) if (i * 7 + j * 3 + int(z)) % 4])
    single("Raw material", "Stainless", coll, lambda b: [
        b.cylinder((-67.5 + (i % 2) * 1.2, -7 + (i // 2) * 1.5, 0.45 + 0.5 * (i % 3)), 0.25, 1.1, 16, "X")
        for i in range(12)])
    single("Raw material pallets", "Pallet wood", coll, lambda b: [
        b.box((-67.0, -7 + k * 3.0 + 0.8, 0.28), (2.6, 2.4, 0.14)) for k in range(4)])
    single("Maintenance workshop", "Machine grey", coll, lambda b: (
        b.box((-64, -19.5, 0.5), (6, 1.0, 1.0), bevel=0.03), b.box((-58.5, -19.8, 1.0), (1.2, 0.6, 2.0), bevel=0.03),
        b.box((-57.0, -19.8, 1.0), (1.2, 0.6, 2.0), bevel=0.03), b.box((-61, -17, 0.35), (2.0, 1.4, 0.7), bevel=0.05)))
    single("Workshop cabinets", "Reject red", coll, lambda b: [
        b.box((-67.5 + i * 1.1, -21.2, 0.8), (1.0, 0.6, 1.6), bevel=0.03) for i in range(3)])
    single("Workshop cage", "Fence mesh", coll, lambda b: (
        b.box((-62, -13.5, 1.2), (16, 0.03, 2.4)), b.box((-54, -17.8, 1.2), (0.03, 8.6, 2.4))))
    px, py = 25.5, 17.8  # break area in the north-east corner
    single("Break area pod", "Machine white", coll, lambda b: (
        b.box((px, py + 2.1, 1.6), (7, 0.2, 3.2)), b.box((px - 3.5, py, 1.6), (0.2, 4.4, 3.2)),
        b.box((px + 3.5, py, 1.6), (0.2, 4.4, 3.2)), b.box((px, py, 3.2), (7.2, 4.6, 0.15))))
    single("Break area glazing", "Glass", coll, lambda b: b.box((px, py - 2.2, 1.6), (6.8, 0.06, 2.8)))
    single("Break area tables", "Pallet wood", coll, lambda b: [
        b.box((px - 1.8 + i * 3.6, py, 0.75), (1.6, 0.9, 0.06)) for i in range(2)])
    single("Andon boards", "Screen", coll, lambda b: [
        b.box((x, 15.75, 6.2), (3.2, 0.1, 1.6)) for x in (-50, -30, -10, 10)])
    single("Andon board frames", "Machine grey", coll, lambda b: [
        b.box((x, 15.82, 6.2), (3.4, 0.08, 1.8)) for x in (-50, -30, -10, 10)])
    single("Forklift", "Hi-vis", coll, lambda b: (
        b.box((-20, 14.0, 0.8), (2.2, 1.2, 1.0), bevel=0.1), b.box((-20.4, 14.0, 1.9), (1.2, 1.1, 0.08)),
        b.box((-18.8, 14.0, 1.6), (0.12, 1.0, 2.8))))
    single("Forklift detail", "Rubber", coll, lambda b: (
        [b.cylinder((-20 + dx, 14 + dy, 0.35), 0.35, 0.3, 16, "Y") for dx in (-0.7, 0.7) for dy in (-0.62, 0.62)],
        [b.box((-18.2, 14 + dy, 0.35), (1.2, 0.12, 0.06)) for dy in (-0.3, 0.3)]))
    single("Electrical cabinets", "Machine grey", coll, lambda b: [
        b.box((x, -15.4, 1.1), (1.6, 0.6, 2.2), bevel=0.03) for x in (-50, -30, -10, 10)])


def conveyors():
    coll = "Production line"
    runs = ((-57.0, -47.3), (-41.0, -31.0), (-21.5, -12.0), (-4.0, 5.0), (11.0, 13.0))
    single("Conveyor frames", "Machine grey", coll, lambda b: [
        (b.box(((a + c) / 2, s * 0.55, 0.85), (c - a, 0.08, 0.16)),
         [b.box((px, s * 0.55, 0.42), (0.08, 0.08, 0.84)) for px in (a + 0.2, (a + c) / 2, c - 0.2)])
        for a, c in runs for s in (-1, 1)])

    def rollers(b):
        for a, c in runs:
            n = int((c - a) / 0.3)
            for i in range(n):
                b.cylinder((a + 0.15 + i * 0.3, 0, 0.88), 0.045, 1.02, 10, "Y")
    single("Conveyor rollers", "Stainless", coll, rollers)
    # CNC feed spurs to both machines.
    single("CNC feed spurs", "Machine grey", coll, lambda b: [b.box((-44, s * 3.0, 0.85), (1.0, 2.2, 0.16)) for s in (-1, 1)])


def buffers(lab):
    lay = lab["layout"]
    coll = "Production line"
    tote = Builder().box((0, 0, 0.22), (0.9, 0.6, 0.38), bevel=0.03).mesh("Tote")
    tote.materials.append(MATS["Tote blue"])
    boxes = Builder().box((0, 0, 0.62), (1.05, 1.05, 0.9), bevel=0.02).mesh("Finished goods")
    boxes.materials.append(MATS["Cardboard"])
    pallet = Builder()
    for name, buffer in lay["buffers"].items():
        for i in range(lab["config"]["buffers"][name]):
            px, py = slot_position(buffer, i)
            pallet.box((px, py, 0.29), (1.15, 1.0, 0.12))
            for dy in (-0.4, 0, 0.4):
                pallet.box((px, py + dy, 0.18), (1.15, 0.12, 0.12))
            crate = obj(f"Buffer {name} / slot {i + 1:02d}", boxes if name == "outbound" else tote, None, coll,
                        (px, py, 0.35 - (0.0 if name == "outbound" else 0.0)))
            crate["rr_id"] = crate.name
    obj("Buffer pallets", pallet.mesh("Buffer pallets"), "Pallet wood", coll)


def amrs(lab):
    lay = lab["layout"]
    coll, twin = "Logistics", "Digital twin overlay"
    body = Builder().box((0, 0, 0.22), (1.4, 0.9, 0.34), bevel=0.08).box((0, 0, 0.42), (1.2, 0.8, 0.06), bevel=0.02)
    body = body.mesh("AMR body")
    body.materials.append(MATS["Machine grey"])
    for i in range(len(lay["amr"]["homes"])):
        x, y = lay["amr"]["homes"][i]
        a = obj(f"AMR {i + 1}", body, None, coll, (x, y, 0.2))
        single(f"AMR {i + 1} / deck", "Machine white", coll, lambda b: b.box((0, 0, 0.46), (1.1, 0.72, 0.03)), parent=a)
        single(f"AMR {i + 1} / lidar", "Rubber", coll, lambda b: b.cylinder((0.55, 0, 0.5), 0.07, 0.1, 16), parent=a)
        single(f"AMR {i + 1} / wheels", "Rubber", coll, lambda b: [
            b.cylinder((dx, s * 0.46, 0.1), 0.1, 0.06, 16, "Y") for dx in (-0.45, 0.45) for s in (-1, 1)], parent=a)
        single(f"AMR {i + 1} / status", "Status light", coll, lambda b: (
            b.box((0.71, 0, 0.26), (0.02, 0.8, 0.05)), b.box((-0.71, 0, 0.26), (0.02, 0.8, 0.05))), parent=a)
        single(f"AMR {i + 1} / payload", "Cardboard", coll, lambda b: (
            b.box((-0.25, 0, 0.72), (0.55, 0.7, 0.5), bevel=0.01), b.box((0.3, 0, 0.72), (0.5, 0.7, 0.5), bevel=0.01),
            b.box((0.0, 0, 1.15), (0.6, 0.6, 0.35), bevel=0.01)), parent=a)
        g = single(f"Twin ghost AMR {i + 1}", "Hologram cyan", twin, lambda b: b.box((0, 0, 0.35), (1.5, 1.0, 0.7)),
                   location=(x, y, 0.2))
        g.display_type = "WIRE"
    route = [lay["amr"]["homes"][0], *lay["amr"]["corridor"]]
    single("AMR route marking", "Safety yellow", coll, lambda b: [
        b.box(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, 0.215 if max(p[0], q[0]) <= 30 else 0.09),
              (abs(q[0] - p[0]) + 0.12, abs(q[1] - p[1]) + 0.12, 0.012))
        for p, q in zip(route[1:], route[2:])])
    single("AMR chargers", "Machine grey", coll, lambda b: [
        b.box((h[0] + 0.95, h[1], 0.45), (0.2, 0.7, 0.9), bevel=0.03) for h in lay["amr"]["homes"]])


def twin_overlay(lab):
    coll = "Digital twin overlay"
    gx, gy = GAUGE_POSITION
    H = GAUGE_HEIGHT_M
    twin = empty("Digital twin", coll, (0, 0, 0), kind="SPHERE", size=2.0)
    for key in ("sim_time_s", "good_units", "wear_truth", "wear_estimate", "grid_import_kw"):
        twin[key] = 0.0
    single("Twin overlay / gauge frame", "Hologram cyan", coll, lambda b: (
        b.box((gx, gy, GAUGE_BASE_Z - 0.05), (2.2, 0.8, 0.1)),
        [b.box((gx + dx, gy, GAUGE_BASE_Z + H / 2), (0.04, 0.04, H)) for dx in (-1.1, 1.1)],
        [b.box((gx, gy, GAUGE_BASE_Z + H * f), (2.2, 0.03, 0.03)) for f in (0.25, 0.5, 0.75)]))
    single("Twin overlay / failure threshold", "Hologram red", coll, lambda b: b.box((gx, gy, GAUGE_BASE_Z + H), (2.6, 0.12, 0.06)))
    for name, mat, dx in (("wear truth", "Hologram amber", -0.45), ("wear estimate", "Hologram solid", 0.45)):
        single(f"Twin overlay / {name}", mat, coll, lambda b: b.box((0, 0, H / 2), (0.55, 0.45, H)),
               location=(gx + dx, gy, GAUGE_BASE_Z))
    single("Twin overlay / wear band", "Hologram band", coll, lambda b: b.box((0, 0, H / 2), (0.85, 0.7, H)),
           location=(gx + 0.45, gy, GAUGE_BASE_Z))
    single("Twin overlay / service request", "Hologram solid", coll, lambda b: (
        b.torus((0, 0, 0.35), 0.35, 0.08, 32, 8), b.box((0, 0, -0.35), (0.16, 0.16, 1.0))),
        location=(-44.0, -7.0, 7.2))
    # Campus energy column next to the energy center.
    ex, ey = -84.0, 54.0
    single("Twin overlay / grid import", "Hologram status", coll, lambda b: b.cylinder((0, 0, 0.5), 1.1, 1.0, 32),
           location=(ex, ey, 0.1))
    limit = lab["config"]["demand_limit_kw"] * IMPORT_SCALE_M_PER_KW
    single("Twin overlay / demand limit", "Hologram red", coll, lambda b: b.torus((ex, ey, limit + 0.1), 2.0, 0.08, 48, 8))
    single("Twin overlay / energy base", "Hologram cyan", coll, lambda b: b.cylinder((ex, ey, 0.05), 2.4, 0.1, 48))
    # Static data links: every station ring to the operations center on the office's top floor.
    hub = (-4.0, 48.5, 14.0)
    curve = bpy.data.curves.new("Twin data links", "CURVE")
    curve.dimensions, curve.bevel_depth, curve.bevel_resolution = "3D", 0.05, 2
    for station in lab["layout"]["stations"]:
        x, y = station["position"]
        z = {"weld": 6.0, "kitting": 4.2, "assembly": 3.6}.get(station["id"], station["size"][2] + 2.1)
        spline = curve.splines.new("BEZIER")
        spline.bezier_points.add(1)
        a, b = spline.bezier_points
        a.co, b.co = (x, y, z), hub
        a.handle_left = a.handle_right = (x, y, z + 12)
        b.handle_left = b.handle_right = (hub[0], hub[1] - 14, hub[2] + 8)
    curve.materials.append(MATS["Hologram cyan"])
    links = bpy.data.objects.new("Twin data links", curve)
    collection(coll).objects.link(links)
    links["rr_id"] = links.name
    # Rooftop air handlers (status shows the twin's setpoint command as applied by the plant).
    for i, x in enumerate((-55, -35, -15, 5)):
        single(f"Rooftop unit {i + 1}", "Machine white", "Buildings / hall cutaway", lambda b, x=x: (
            b.box((x, 10, HALL["h"] + 1.2), (4.0, 2.4, 1.6), bevel=0.08),
            b.cylinder((x - 1, 10, HALL["h"] + 2.05), 0.7, 0.1, 24), b.cylinder((x + 1, 10, HALL["h"] + 2.05), 0.7, 0.1, 24)))
        single(f"Rooftop unit {i + 1} / status", "Status light", "Buildings / hall cutaway",
               lambda b: b.box((0, 0, 0), (0.08, 1.8, 0.12)), location=(x + 2.05, 10, HALL["h"] + 1.6))


def lighting():
    world = bpy.data.worlds.new("Campus sky")
    bpy.context.scene.world = world
    nt = world.node_tree
    bg = nt.nodes["Background"]
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(58)
    sky.sun_rotation = math.radians(200)
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.16
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = SUN_STRENGTH
    sun_data.angle = math.radians(0.8)
    sun_data.color = (1.0, 0.96, 0.9)
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(32), 0.0, math.radians(-25))  # early-afternoon sun from the south-west
    collection("Cameras & lights").objects.link(sun)
    sun["rr_id"] = "Sun"
    for i, (x, y) in enumerate(((-55, 0), (-30, 0), (-5, 0), (15, -6))):
        data = bpy.data.lights.new(f"Hall fill {i + 1}", "AREA")
        data.shape, data.size, data.size_y, data.energy = "RECTANGLE", 16, 30, 2600
        data.color = (1.0, 0.95, 0.88)
        light = bpy.data.objects.new(f"Hall fill {i + 1}", data)
        light.location = (x, y, HALL["h"] - 1.0)
        collection("Cameras & lights").objects.link(light)


CAMERAS = {
    "Campus aerial": ((168.0, -178.0, 118.0), (-8.0, 2.0, 0.0), 34),
    "Hall cutaway": ((24.0, -58.0, 38.0), (-22.0, -1.0, 0.0), 30),
    "CNC twin close-up": ((-35.5, -27.0, 8.5), (-45.0, -5.0, 2.6), 30),
    "Energy & parking": ((150.0, -118.0, 36.0), (58.0, -40.0, 2.0), 30),
    "Line level": ((-72.0, -12.5, 3.6), (-10.0, 0.5, 1.8), 22),
}


def cameras():
    for name, (location, target, lens) in CAMERAS.items():
        data = bpy.data.cameras.new(name)
        data.lens, data.clip_start, data.clip_end = lens, 0.1, 2500
        cam = bpy.data.objects.new(f"Camera / {name}", data)
        cam.location = location
        direction = Vector(target) - Vector(location)
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        collection("Cameras & lights").objects.link(cam)
    bpy.context.scene.camera = bpy.data.objects["Camera / Campus aerial"]


# ----------------------------------------------------------------------------- animation
def animate(lab, mode):
    spec = channels(lab, mode)
    grouped = {}
    for (owner, path, index), values in spec.items():
        grouped.setdefault(owner, []).append((path, index, values))
    for owner, curves in grouped.items():
        if owner.startswith("light:"):
            target, id_type = bpy.data.lights[owner[6:]], "LIGHT"
        else:
            target, id_type = bpy.data.objects[owner], "OBJECT"
        action = bpy.data.actions.new(f"{owner} / recorded")
        slot = action.slots.new(id_type=id_type, name=target.name)
        strip = action.layers.new("Recorded samples").strips.new(type="KEYFRAME")
        bag = strip.channelbags.new(slot)
        for path, index, values in curves:
            fc = bag.fcurves.new(path, index=index)
            keys = [(1, values[0])]
            for k in range(1, len(values)):
                if values[k] != values[k - 1]:
                    keys.append((k + 1, values[k]))
            fc.keyframe_points.add(len(keys))
            fc.keyframe_points.foreach_set("co", [c for key in keys for c in key])
            fc.keyframe_points.foreach_set("interpolation", [0] * len(keys))  # CONSTANT
            fc.update()
        target.animation_data_create()
        target.animation_data.action = action
        target.animation_data.action_slot = slot
    return sum(len(v) for v in spec.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", type=Path, required=True)
    parser.add_argument("--mode", choices=("closed", "shadow"), default="closed")
    parser.add_argument("--output", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    raw = args.lab.read_bytes()
    lab = json.loads(raw)
    scene = reset()
    n = lab["config"]["samples"]
    scene.frame_start, scene.frame_end = 1, n
    scene.render.fps, scene.render.fps_base = FPS, 1
    materials()
    terrain(lab)
    trees(lab)
    hall()
    warehouse(lab)
    office(lab)
    energy_center(lab)
    parking(lab)
    stations = {s["id"]: s for s in lab["layout"]["stations"]}
    kitting(stations["kitting"])
    cnc(stations["cnc1"])
    cnc(stations["cnc2"])
    weld_cell(stations["weld"])
    assembly(stations["assembly"])
    inspection(stations["inspect"])
    conveyors()
    hall_props()
    for sid, station in stations.items():
        empty(f"Station {sid}", "Production line", (*station["position"], 0.0), kind="CUBE", size=0.3)
    buffers(lab)
    amrs(lab)
    twin_overlay(lab)
    lighting()
    cameras()
    keys = animate(lab, args.mode)
    scene["robot_reel_schema"] = lab["schema"]
    scene["robot_reel_mode"] = args.mode
    scene["robot_reel_seed"] = lab["runs"][args.mode]["seed"]
    scene["lab_json_sha256"] = hashlib.sha256(raw).hexdigest()
    scene["frame_mapping"] = "Frame k+1 holds sample k (5 s plant time); constant interpolation; no physics."
    scene.frame_set(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), compress=True)
    stats = {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes), "materials": len(bpy.data.materials),
             "animated_values": keys, "frames": n, "mode": args.mode, "output": str(args.output)}
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
