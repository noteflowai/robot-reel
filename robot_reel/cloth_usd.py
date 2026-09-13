"""Time-sampled deforming meshes, with native point/velocity readback."""
import hashlib
import math

from .cloth import CASES, VERTICES, digest, floats, validate, vertex


def offset(case):
    """Presentation only; local points remain in the original simulation frame."""
    return [(case-1)*1.35, 0, 0]


def export_usd(trace, positions, velocities, path):
    from pxr import Gf, Usd, UsdGeom, Vt

    validate(trace, positions, velocities)
    q, v = floats(positions, len(positions)//4), floats(velocities, len(velocities)//4)
    stage = Usd.Stage.CreateNew(str(path))
    stage.SetStartTimeCode(1)
    stage.SetEndTimeCode(trace["frame_count"])
    stage.SetFramesPerSecond(trace["fps"])
    stage.SetTimeCodesPerSecond(trace["fps"])
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    stage.GetRootLayer().customLayerData = {
        "source": f"Newton 1.6.0 / SolverVBD / {trace['source']['device_name']}",
        "sampling": "Frame 1 = source sample 0. Recorded points and velocities; no resimulation.",
        "presentation": "Case translations along X separate independent simulations; local points are unchanged.",
    }
    for c, case in enumerate(CASES):
        mesh = UsdGeom.Mesh.Define(stage, f"/World/{case['id']}")
        mesh.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*offset(c)))
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
        mesh.CreateDoubleSidedAttr(True)
        mesh.CreateFaceVertexCountsAttr([3]*len(trace["triangles"]))
        mesh.CreateFaceVertexIndicesAttr([i for face in trace["triangles"] for i in face])
        rgb = [int(case["color"][i:i+2], 16)/255 for i in (1, 3, 5)]
        mesh.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*rgb)]))
        points, speeds = mesh.CreatePointsAttr(), mesh.CreateVelocitiesAttr()
        for f in range(trace["frame_count"]):
            points.Set(Vt.Vec3fArray([Gf.Vec3f(*vertex(q, f, c, i)) for i in range(VERTICES)]), f+1)
            speeds.Set(Vt.Vec3fArray([Gf.Vec3f(*vertex(v, f, c, i)) for i in range(VERTICES)]), f+1)
    stage.GetRootLayer().Save()


def check_usd(trace, positions, velocities, path):
    from pxr import Gf, Sdf, Usd, UsdGeom

    validate(trace, positions, velocities)
    q, v = floats(positions, len(positions)//4), floats(velocities, len(velocities)//4)
    layer = Sdf.Layer.FindOrOpen(str(path))
    if layer is None:
        raise ValueError("Missing cloth USD layer")
    layer.Reload(force=True)
    if layer.GetExternalReferences():
        raise ValueError("Cloth USD must be self-contained")
    stage = Usd.Stage.Open(layer)
    if (stage.GetStartTimeCode() != 1 or stage.GetEndTimeCode() != trace["frame_count"]
            or stage.GetTimeCodesPerSecond() != trace["fps"] or stage.GetFramesPerSecond() != trace["fps"]
            or UsdGeom.GetStageUpAxis(stage) != "Z" or UsdGeom.GetStageMetersPerUnit(stage) != 1):
        raise ValueError("Cloth USD clock or units mismatch")
    if {str(p.GetPath()) for p in stage.Traverse()} != {"/World", *(f"/World/{c['id']}" for c in CASES)}:
        raise ValueError("Unexpected cloth USD primitives")
    max_position = max_velocity = 0.
    for c, case in enumerate(CASES):
        mesh = UsdGeom.Mesh.Get(stage, f"/World/{case['id']}")
        if (not mesh or list(mesh.GetFaceVertexCountsAttr().Get()) != [3]*len(trace["triangles"])
                or list(mesh.GetFaceVertexIndicesAttr().Get()) != [i for face in trace["triangles"] for i in face]
                or mesh.GetSubdivisionSchemeAttr().Get() != "none"
                or mesh.GetOrientationAttr().Get() != "rightHanded" or not mesh.GetDoubleSidedAttr().Get()):
            raise ValueError("Cloth USD mesh topology or appearance mismatch")
        colors = mesh.GetDisplayColorAttr().Get()
        rgb = [int(case["color"][i:i+2], 16)/255 for i in (1, 3, 5)]
        if colors is None or len(colors) != 1 or math.dist(colors[0], rgb) > 1e-7:
            raise ValueError("Cloth USD case color mismatch")
        expected_times = list(range(1, trace["frame_count"]+1))
        if any(attr.GetTimeSamples() != expected_times for attr in (mesh.GetPointsAttr(), mesh.GetVelocitiesAttr())):
            raise ValueError("Cloth USD must retain every source sample")
        for f in range(trace["frame_count"]):
            points, speeds = mesh.GetPointsAttr().Get(f+1), mesh.GetVelocitiesAttr().Get(f+1)
            if len(points) != VERTICES or len(speeds) != VERTICES:
                raise ValueError("Cloth USD vertex count mismatch")
            transform = UsdGeom.XformCache(f+1).GetLocalToWorldTransform(mesh.GetPrim())
            # Check the full affine transform, including components a flat mesh cannot reveal.
            for p in ([0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]):
                error = math.dist(transform.Transform(Gf.Vec3d(*p)), [a+b for a, b in zip(p, offset(c))])
                if not math.isfinite(error) or error > 1e-7:
                    raise ValueError("Cloth USD presentation transform mismatch")
            for i in range(VERTICES):
                p_error = math.dist(points[i], vertex(q, f, c, i))
                v_error = math.dist(speeds[i], vertex(v, f, c, i))
                if not math.isfinite(p_error+v_error) or p_error > 1e-7 or v_error > 1e-7:
                    raise ValueError(f"Cloth USD differs from source: case {c}, sample {f}, vertex {i}")
                max_position, max_velocity = max(max_position, p_error), max(max_velocity, v_error)
    return {
        "checked_vertex_samples": trace["frame_count"]*len(CASES)*VERTICES,
        "maximum_position_error_m": max_position, "maximum_velocity_error_m_s": max_velocity,
        "positions_sha256": hashlib.sha256(positions).hexdigest(), "velocities_sha256": hashlib.sha256(velocities).hexdigest(),
        "usd_sha256": digest(path),
    }
