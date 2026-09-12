"""OpenUSD presentation export for recorded Newton box poses; no physics schemas."""
import math
from pathlib import Path

from .newton import point, validate_trace


def export_usd(trace, path):
    from pxr import Gf, Sdf, Usd, UsdGeom, Vt

    validate_trace(trace)
    stage = Usd.Stage.CreateNew(str(path))
    stage.SetStartTimeCode(1)
    stage.SetEndTimeCode(len(trace["frames"]))
    stage.SetFramesPerSecond(trace["fps"])
    stage.SetTimeCodesPerSecond(trace["fps"])
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    stage.GetRootLayer().customLayerData = {
        "source": "Robot Reel / Newton 1.6.0 / SolverXPBD / CPU",
        "sampling": "Frame 1 = simulation 0 s. Recorded poses at 30 Hz; no resimulation.",
    }
    for index, body in enumerate(trace["bodies"]):
        cube = UsdGeom.Cube.Define(stage, f"/World/{body['name']}")
        cube.CreateSizeAttr(1.)
        color = body["color"].lstrip("#")
        cube.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*(int(color[i:i+2], 16)/255 for i in (0, 2, 4)))]))
        cube.GetPrim().CreateAttribute("reel:bodyIndex", Sdf.ValueTypeNames.Int, custom=True).Set(index)
        matrix = cube.AddTransformOp(UsdGeom.XformOp.PrecisionDouble)
        for frame in trace["frames"]:
            pose = frame["poses"][index]
            transform = Gf.Matrix4d(1.)
            transform.SetRotate(Gf.Quatd(pose[6], Gf.Vec3d(*pose[3:6])))
            transform.SetTranslateOnly(Gf.Vec3d(*pose[:3]))
            scale = Gf.Matrix4d(1.).SetScale(Gf.Vec3d(*body["size"]))
            # Row-vector convention: scale the unit cube, rotate, then translate.
            matrix.Set(scale * transform, frame["frame"]+1)
    stage.GetRootLayer().Save()
    # Keep generated ASCII scenes clean in a source checkout.
    path = Path(path)
    path.write_text(path.read_text().rstrip() + "\n")


def check_usd(trace, path):
    from pxr import Gf, Sdf, Usd, UsdGeom

    validate_trace(trace)
    layer = Sdf.Layer.FindOrOpen(str(path))
    if layer is None or layer.GetExternalReferences():
        raise ValueError("Expected a self-contained USD layer")
    stage = Usd.Stage.Open(layer)
    if (
        stage.GetStartTimeCode() != 1 or stage.GetEndTimeCode() != len(trace["frames"])
        or stage.GetTimeCodesPerSecond() != trace["fps"] or stage.GetFramesPerSecond() != trace["fps"]
        or UsdGeom.GetStageUpAxis(stage) != "Z" or UsdGeom.GetStageMetersPerUnit(stage) != 1
    ):
        raise ValueError("USD time base, axis or length unit mismatch")
    max_error = 0.
    count = 0
    for index, body in enumerate(trace["bodies"]):
        cube = UsdGeom.Cube.Get(stage, f"/World/{body['name']}")
        if not cube or cube.GetSizeAttr().Get() != 1:
            raise ValueError("Missing or resized USD box")
        ops = cube.GetOrderedXformOps()
        expected_times = list(range(1, len(trace["frames"])+1))
        if len(ops) != 1 or ops[0].GetTimeSamples() != expected_times:
            raise ValueError("USD must contain every recorded sample exactly once")
        for frame in trace["frames"]:
            cache = UsdGeom.XformCache(frame["frame"]+1)
            transform = cache.GetLocalToWorldTransform(cube.GetPrim())
            # Four affine-independent points catch translation, rotation and scale errors.
            for local in ([0, 0, 0], [.5, 0, 0], [0, .5, 0], [0, 0, .5]):
                actual = list(transform.Transform(Gf.Vec3d(*local)))
                expected = point(frame["poses"][index], [v*s for v, s in zip(local, body["size"])])
                error = math.dist(actual, expected)
                if not math.isfinite(error) or error > 1e-5:
                    raise ValueError(f"USD transform differs from source: {body['name']}, frame {frame['frame']}")
                max_error = max(max_error, error)
            count += 1
    return {"body_samples": count, "max_transform_error_m": max_error}
