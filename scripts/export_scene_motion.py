"""Export recorded robot geometry, poses, proxy and camera to USD and glTF."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robot_reel.scene_motion import checked_file, identity, validate_trace, write_json


def load(root):
    import mujoco
    root = Path(root)
    trace = json.loads((root / "trace.json").read_text())
    validate_trace(trace)
    for name, expected in trace["files"].items():
        checked_file(root, name, expected)
    model = mujoco.MjModel.from_xml_path(str(root / "model/captured-scene.xml"))
    return trace, model


def mesh_arrays(model, mesh):
    start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
    first, faces = model.mesh_faceadr[mesh], model.mesh_facenum[mesh]
    return model.mesh_vert[start:start+count], model.mesh_face[first:first+faces]


def rgba(model, geom):
    material = int(model.geom_matid[geom])
    return (model.mat_rgba[material] if material >= 0 else model.geom_rgba[geom]).tolist()


def body_local_vertices(model, geom):
    """Bake only a fixed visual attachment; preserve every recorded body pose."""
    import mujoco
    import numpy as np
    vertices, faces = mesh_arrays(model, int(model.geom_dataid[geom]))
    rotation = np.empty(9)
    mujoco.mju_quat2Mat(rotation, model.geom_quat[geom])
    exact = vertices.astype(np.float64) @ rotation.reshape(3, 3).T + model.geom_pos[geom]
    stored = exact.astype("<f4")
    return stored, faces, float(np.max(np.abs(stored.astype(np.float64) - exact)))


def export_glb(trace, model, path):
    import mujoco
    import numpy as np

    binary = bytearray()
    views, accessors, meshes, materials = [], [], [], []
    nodes = [{"name": "WorldToBrowser", "rotation": [-math.sqrt(.5), 0, 0, math.sqrt(.5)],
              "children": []}]
    mesh_buffers = {}

    def accessor(array, component, kind, target):
        while len(binary) % 4:
            binary.append(0)
        view = len(views)
        raw = array.tobytes()
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(raw), "target": target})
        binary.extend(raw)
        item = {"bufferView": view, "componentType": component,
                "count": len(array), "type": kind}
        if kind == "VEC3":
            item.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        accessors.append(item)
        return len(accessors)-1

    body_nodes = {}
    for i, (name, pose) in enumerate(zip(trace["bodies"], trace["frames"][0]["body_poses"]), 1):
        body_nodes[i] = len(nodes)
        nodes[0]["children"].append(len(nodes))
        nodes.append({"name": name, "translation": pose[:3],
                      "rotation": [*pose[4:], pose[3]], "children": []})
    for geom in range(model.ngeom):
        if model.geom_group[geom] != 2:
            continue
        if model.geom_type[geom] != mujoco.mjtGeom.mjGEOM_MESH:
            raise ValueError("unexpected robot visual primitive")
        mesh = int(model.geom_dataid[geom])
        if mesh not in mesh_buffers:
            points, faces = mesh_arrays(model, mesh)
            mesh_buffers[mesh] = (
                accessor(points.astype("<f4"), 5126, "VEC3", 34962),
                accessor(faces.astype("<u4").ravel(), 5125, "SCALAR", 34963),
            )
        positions, indices = mesh_buffers[mesh]
        material = len(materials)
        materials.append({"name": f"material_{geom}", "doubleSided": True,
                          "pbrMetallicRoughness": {"baseColorFactor": rgba(model, geom),
                                                   "metallicFactor": 0, "roughnessFactor": .55}})
        mesh_index = len(meshes)
        meshes.append({"name": f"mesh_{geom}", "primitives": [
            {"attributes": {"POSITION": positions}, "indices": indices, "material": material}]})
        nodes[body_nodes[int(model.geom_bodyid[geom])]]["children"].append(len(nodes))
        q = model.geom_quat[geom].tolist()
        nodes.append({"name": f"geom_{geom:03}", "mesh": mesh_index,
                      "translation": model.geom_pos[geom].tolist(), "rotation": [*q[1:], q[0]]})
    record = {"asset": {"version": "2.0", "generator": "Robot Reel recorded MuJoCo geometry",
                        "copyright": "Pollen Robotics; model-derived geometry retains BY-SA-NC terms"},
              "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes, "meshes": meshes,
              "materials": materials, "accessors": accessors, "bufferViews": views,
              "buffers": [{"byteLength": len(binary)}],
              "extras": {"trace_sha256": trace["_trace_sha256"], "unit": "metre",
                         "motion": "Initial recorded pose; body nodes accept subsequent trace poses in Z-up."}}
    encoded = json.dumps(record, separators=(",", ":"), allow_nan=False).encode()
    encoded += b" " * ((-len(encoded)) % 4)
    binary.extend(b"\0" * ((-len(binary)) % 4))
    size = 12 + 8 + len(encoded) + 8 + len(binary)
    Path(path).write_bytes(struct.pack("<4sII", b"glTF", 2, size)
                          + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                          + struct.pack("<II", len(binary), 0x004E4942) + binary)
    return {"visual_geometries": len(meshes), "unique_meshes": len(mesh_buffers),
            "body_nodes": len(body_nodes), "file": identity(path)}


def export_usd(trace, model, root, path):
    import mujoco
    import numpy as np
    from pxr import Gf, Usd, UsdGeom, UsdShade, Sdf, Vt

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    stage.SetStartTimeCode(1)
    stage.SetEndTimeCode(len(trace["frames"]))
    stage.SetFramesPerSecond(trace["plan"]["sample_hz"])
    stage.SetTimeCodesPerSecond(trace["plan"]["sample_hz"])
    stage.SetMetadata("customLayerData", {
        "robot_reel_trace_sha256": trace["_trace_sha256"],
        "frame_mapping": "USD time code = source frame + 1; source sim_time_s remains in trace.json",
        "model_geometry_terms": "Creative Commons BY-SA-NC; version unspecified upstream",
    })
    for i, name in enumerate(trace["bodies"]):
        body = UsdGeom.Xform.Define(stage, f"/World/Robot/{name}")
        move = body.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
        rotate = body.AddOrientOp(UsdGeom.XformOp.PrecisionDouble)
        for frame in trace["frames"]:
            pose = frame["body_poses"][i]
            move.Set(Gf.Vec3d(*pose[:3]), frame["frame"] + 1)
            rotate.Set(Gf.Quatd(pose[3], Gf.Vec3d(*pose[4:])), frame["frame"] + 1)
    for geom in range(model.ngeom):
        if model.geom_group[geom] != 2:
            continue
        if model.geom_type[geom] != mujoco.mjtGeom.mjGEOM_MESH:
            raise ValueError("unexpected visual geometry")
        body_name = model.body(int(model.geom_bodyid[geom])).name
        mesh = UsdGeom.Mesh.Define(stage, f"/World/Robot/{body_name}/geom_{geom:03}")
        vertices, faces, _ = body_local_vertices(model, geom)
        mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(vertices.astype(np.float32)))
        mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(faces), 3, dtype=np.int32)))
        mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(faces.ravel().astype(np.int32)))
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateExtentAttr([Gf.Vec3f(*vertices.min(axis=0).tolist()),
                              Gf.Vec3f(*vertices.max(axis=0).tolist())])
        # Static attachments are already in body coordinates. This avoids
        # importer-specific Euler decomposition near singular orientations.
        color = rgba(model, geom)
        material = UsdShade.Material.Define(stage, f"/World/Materials/material_{geom}")
        shader = UsdShade.Shader.Define(stage, f"/World/Materials/material_{geom}/surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color[:3]))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(.55)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
        mesh.CreateDisplayColorAttr([Gf.Vec3f(*color[:3])])
    hfield = json.loads((Path(root) / "collision-heightfield.json").read_text())
    n, (low, high) = hfield["resolution"], hfield["bounds"]
    vertices = [[low[0]+(high[0]-low[0])*c/(n-1), low[1]+(high[1]-low[1])*r/(n-1),
                 hfield["heights_m"][r*n+c]] for r in range(n) for c in range(n)]
    faces = []
    for r in range(n - 1):
        for c in range(n - 1):
            i = r*n+c
            faces.extend([[i, i+1, i+n], [i+1, i+n+1, i+n]])
    proxy = UsdGeom.Mesh.Define(stage, "/World/MotionCollisionProxy")
    proxy.CreatePointsAttr(vertices)
    proxy.CreateFaceVertexCountsAttr([3]*len(faces))
    proxy.CreateFaceVertexIndicesAttr([v for face in faces for v in face])
    proxy.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    proxy.CreateDisplayColorAttr([(.2, .6, .5)])
    camera = UsdGeom.Camera.Define(stage, "/World/RecordedCamera")
    record = trace["camera"]
    camera.CreateProjectionAttr(UsdGeom.Tokens.perspective)
    # USD lens/filmback values use tenths of the stage unit. On this metre
    # stage, 0.5 means a 50 mm virtual lens; aperture is derived from the FOV.
    focal = .5
    vertical = 2 * focal * math.tan(math.radians(record["vertical_fov_degrees"]) / 2)
    camera.CreateFocalLengthAttr(focal)
    camera.CreateVerticalApertureAttr(vertical)
    camera.CreateHorizontalApertureAttr(vertical * record["width"] / record["height"])
    camera.CreateClippingRangeAttr(Gf.Vec2f(.01, 500))
    # Gf matrices act on row vectors; each row is one world-space camera axis.
    matrix = Gf.Matrix4d(1)
    for i, axis in enumerate(record["axes_world"]):
        matrix.SetRow(i, Gf.Vec4d(*axis, 0))
    matrix.SetRow(3, Gf.Vec4d(*record["position_m"], 1))
    camera.AddTransformOp(UsdGeom.XformOp.PrecisionDouble).Set(matrix)
    camera.GetPrim().SetCustomData({"image_width": record["width"], "image_height": record["height"]})
    stage.GetRootLayer().Save()


def verify_usd(trace, model, path):
    import numpy as np
    from pxr import Gf, Usd, UsdGeom
    stage = Usd.Stage.Open(str(path))
    if (UsdGeom.GetStageMetersPerUnit(stage) != 1 or UsdGeom.GetStageUpAxis(stage) != "Z"
            or stage.GetStartTimeCode() != 1 or stage.GetEndTimeCode() != len(trace["frames"])):
        raise ValueError("USD units or source frame range differ")
    maximum = 0.
    for frame in trace["frames"]:
        cache = UsdGeom.XformCache(frame["frame"] + 1)
        for name, pose in zip(trace["bodies"], frame["body_poses"]):
            prim = stage.GetPrimAtPath(f"/World/Robot/{name}")
            matrix = np.asarray(cache.GetLocalToWorldTransform(prim))
            expected = Gf.Matrix4d().SetRotate(Gf.Quatd(pose[3], Gf.Vec3d(*pose[4:])))
            expected.SetTranslateOnly(Gf.Vec3d(*pose[:3]))
            maximum = max(maximum, float(np.max(np.abs(matrix - np.asarray(expected)))))
    if maximum > 1e-11:
        raise ValueError(f"USD body poses differ: {maximum}")
    geometry_count = vertices_count = 0
    local_error = 0.
    for geom in range(model.ngeom):
        if model.geom_group[geom] != 2:
            continue
        body_name = model.body(int(model.geom_bodyid[geom])).name
        mesh = UsdGeom.Mesh.Get(stage, f"/World/Robot/{body_name}/geom_{geom:03}")
        vertices, faces, _ = body_local_vertices(model, geom)
        if not np.array_equal(np.asarray(mesh.GetPointsAttr().Get()), vertices) or not np.array_equal(
            np.asarray(mesh.GetFaceVertexIndicesAttr().Get()), faces.ravel()
        ):
            raise ValueError("USD mesh data differs from the compiled source")
        expected = Gf.Matrix4d(1)
        local_error = max(local_error, float(np.max(np.abs(
            np.asarray(mesh.GetLocalTransformation()) - np.asarray(expected)))))
        geometry_count += 1
        vertices_count += len(vertices)
    if local_error > 1e-11:
        raise ValueError("USD local geometry transforms differ")
    camera = UsdGeom.Camera.Get(stage, "/World/RecordedCamera")
    matrix = np.asarray(camera.ComputeLocalToWorldTransform(0))
    expected = np.eye(4)
    expected[:3, :3] = trace["camera"]["axes_world"]
    expected[3, :3] = trace["camera"]["position_m"]
    if np.max(np.abs(matrix - expected)) > 1e-11:
        raise ValueError("USD camera pose differs")
    focal = camera.GetFocalLengthAttr().Get()
    vertical = camera.GetVerticalApertureAttr().Get()
    horizontal = camera.GetHorizontalApertureAttr().Get()
    fy = trace["camera"]["height"] * focal / vertical
    fx = trace["camera"]["width"] * focal / horizontal
    camera_error = max(abs(fx - trace["camera"]["focal_px"][0]),
                       abs(fy - trace["camera"]["focal_px"][1]))
    if camera_error > .0001:
        raise ValueError("USD camera projection differs")
    return {"frames": len(trace["frames"]), "body_transforms": len(trace["frames"])*15,
            "max_body_transform_error": maximum, "visual_geometries": geometry_count,
            "max_local_geometry_transform_error": local_error,
            "max_camera_focal_error_px": camera_error,
            "checked_local_vertices": vertices_count, "usd": identity(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    exporter_identity = identity(Path(__file__))
    trace, model = load(args.recording)
    trace["_trace_sha256"] = identity(args.recording / "trace.json")["sha256"]
    args.output.mkdir(parents=True, exist_ok=False)
    geometry = []
    for geom in range(model.ngeom):
        if model.geom_group[geom] != 2:
            continue
        vertices, faces, rounding_error = body_local_vertices(model, geom)
        geometry.append({
            "name": f"geom_{geom:03}", "body": model.body(int(model.geom_bodyid[geom])).name,
            "point_space": "body-local; static visual attachment baked into vertices",
            "position_m": [0, 0, 0], "quaternion_wxyz": [1, 0, 0, 0],
            "original_geom_position_m": model.geom_pos[geom].tolist(),
            "original_geom_quaternion_wxyz": model.geom_quat[geom].tolist(),
            "max_vertex_rounding_error_m": rounding_error,
            "vertices": len(vertices), "triangles": len(faces),
            "points_f32_le_sha256": hashlib.sha256(vertices.astype("<f4").tobytes()).hexdigest(),
            "faces_i32_le_sha256": hashlib.sha256(faces.astype("<i4").tobytes()).hexdigest(),
        })
    write_json(args.output / "geometry.json", {
        "schema": "robot-reel.scene-motion-geometry.v1",
        "source_trace": identity(args.recording / "trace.json"), "geometries": geometry,
    })
    export_usd(trace, model, args.recording, args.output / "motion.usdc")
    glb = export_glb(trace, model, args.output / "robot.glb")
    check = verify_usd(trace, model, args.output / "motion.usdc")
    result = {"schema": "robot-reel.scene-motion-export.v1",
              "source_trace": identity(args.recording / "trace.json"), "usd_check": check, "glb": glb,
              "geometry": identity(args.output / "geometry.json"),
              "exporter": exporter_identity,
              "usd_core": importlib.metadata.version("usd-core")}
    if identity(Path(__file__)) != exporter_identity:
        raise ValueError("exporter source changed during the export")
    write_json(args.output / "export-check.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
