"""Editable recorded box animation; worlds separated only for presentation."""
import math

from .chaos import WORLD_COUNT, digest, validate_trace
from .newton import point


def offset(world):
    return [0, (world-(WORLD_COUNT-1)/2)*.6, 0]


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
    root = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(root.GetPrim())
    stage.GetRootLayer().customLayerData = {
        "source": "Robot Reel / Newton 1.6.0 / XPBD / 12 isolated CPU worlds",
        "sampling": "Frame 1 = 0 s. 30 Hz recorded poses. No USD physics.",
        "layout": "World parents offset 0.6 m along Y for presentation. Local poses unchanged.",
    }
    for world in trace["worlds"]:
        i = world["id"]
        parent = UsdGeom.Xform.Define(stage, f"/World/world_{i:02}")
        parent.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*offset(i)))
        parent.GetPrim().CreateAttribute("reel:releaseOffsetDegrees", Sdf.ValueTypeNames.Double, custom=True).Set(world["angle_offset_deg"])
        color = world["color"].lstrip("#")
        for link, name in enumerate(("upper", "lower")):
            cube = UsdGeom.Cube.Define(stage, f"/World/world_{i:02}/w{i:02}_{name}")
            cube.CreateSizeAttr(1.)
            cube.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*(int(color[j:j+2], 16)/255 for j in (0, 2, 4)))]))
            matrix = cube.AddTransformOp(UsdGeom.XformOp.PrecisionDouble)
            for frame in trace["frames"]:
                pose = frame["poses"][2*i+link]
                transform = Gf.Matrix4d(1.)
                transform.SetRotate(Gf.Quatd(pose[6], Gf.Vec3d(*pose[3:6])))
                transform.SetTranslateOnly(Gf.Vec3d(*pose[:3]))
                matrix.Set(Gf.Matrix4d(1.).SetScale(Gf.Vec3d(*trace["link_size_m"])) * transform, frame["frame"]+1)
    stage.GetRootLayer().Save()


def check_usd(trace, path):
    from pxr import Gf, Sdf, Usd, UsdGeom

    validate_trace(trace)
    layer = Sdf.Layer.FindOrOpen(str(path))
    if layer is None or layer.GetExternalReferences():
        raise ValueError("Expected a self-contained chaos USD")
    stage = Usd.Stage.Open(layer)
    if (
        stage.GetStartTimeCode() != 1 or stage.GetEndTimeCode() != len(trace["frames"])
        or stage.GetTimeCodesPerSecond() != trace["fps"] or stage.GetFramesPerSecond() != trace["fps"]
        or UsdGeom.GetStageUpAxis(stage) != "Z" or UsdGeom.GetStageMetersPerUnit(stage) != 1
    ):
        raise ValueError("Chaos USD clock, axis or units mismatch")
    maximum = 0.
    count = 0
    cubes = []
    for world in trace["worlds"]:
        i = world["id"]
        for link, name in enumerate(("upper", "lower")):
            cube = UsdGeom.Cube.Get(stage, f"/World/world_{i:02}/w{i:02}_{name}")
            if not cube or cube.GetSizeAttr().Get() != 1:
                raise ValueError("Missing or resized chaos USD box")
            ops = cube.GetOrderedXformOps()
            if len(ops) != 1 or ops[0].GetTimeSamples() != list(range(1, len(trace["frames"])+1)):
                raise ValueError("Chaos USD does not retain every sample")
            cubes.append((i, link, cube))
    for frame in trace["frames"]:
        cache = UsdGeom.XformCache(frame["frame"]+1)
        for i, link, cube in cubes:
            transform = cache.GetLocalToWorldTransform(cube.GetPrim())
            for local in ([0, 0, 0], [.5, 0, 0], [0, .5, 0], [0, 0, .5]):
                actual = list(transform.Transform(Gf.Vec3d(*local)))
                expected = point(frame["poses"][2*i+link], [v*s for v, s in zip(local, trace["link_size_m"])])
                expected = [v+shift for v, shift in zip(expected, offset(i))]
                error = math.dist(actual, expected)
                if not math.isfinite(error) or error > 1e-5:
                    raise ValueError(f"Chaos USD pose differs: world {i}, sample {frame['frame']}")
                maximum = max(maximum, error)
            count += 1
    return {"checked_body_samples": count, "maximum_transform_error_m": maximum, "usd_sha256": digest(path)}
