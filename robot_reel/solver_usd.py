"""Export and independently read all sampled translations and velocities."""
from pathlib import Path

from .solver_lab import FPS, IDS, SAMPLES, decode, make_lab, read


def write(root):
    from pxr import Gf, Sdf, Usd, UsdGeom

    root = Path(root)
    lab = make_lab([decode(read(root, f"{name}.json")) for name in IDS])
    stage = Usd.Stage.CreateNew(str(root / "scene.usda"))
    stage.SetStartTimeCode(1)
    stage.SetEndTimeCode(SAMPLES)
    stage.SetFramesPerSecond(FPS)
    stage.SetTimeCodesPerSecond(FPS)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    stage.GetRootLayer().customLayerData = {
        "source": "Robot Reel / recorded Genesis and Newton CUDA ballistic flight",
        "sampling": "Frame 1 is t=0; 30 fps. Recorded animation, no USD physics.",
        "layout": "Each run is offset along Y by its zero-based run index; local positions unchanged.",
    }
    for j, run in enumerate(lab["runs"]):
        root_path = "/World/" + run["id"].replace("-", "_")
        parent = UsdGeom.Xform.Define(stage, root_path)
        parent.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0, j, 0))
        sphere = UsdGeom.Sphere.Define(stage, root_path + "/projectile")
        sphere.CreateRadiusAttr(.1)
        op = sphere.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
        vel = sphere.GetPrim().CreateAttribute("reel:velocity", Sdf.ValueTypeNames.Double3, custom=True)
        for f in run["frames"]:
            op.Set(Gf.Vec3d(*f["position_m"]), f["sample"] + 1)
            vel.Set(Gf.Vec3d(*f["velocity_m_s"]), f["sample"] + 1)
    stage.GetRootLayer().Save()
    path = root / "scene.usda"
    path.write_text(path.read_text().rstrip() + "\n")
    return check(root)


def check(root):
    from pxr import Sdf, Usd, UsdGeom

    root = Path(root)
    lab = make_lab([decode(read(root, f"{name}.json")) for name in IDS])
    layer = Sdf.Layer.FindOrOpen(str(root / "scene.usda"))
    if layer is None or layer.GetExternalReferences():
        raise ValueError("Expected a self-contained USD file")
    stage = Usd.Stage.Open(layer)
    if (stage.GetStartTimeCode() != 1 or stage.GetEndTimeCode() != SAMPLES
            or stage.GetFramesPerSecond() != FPS or stage.GetTimeCodesPerSecond() != FPS
            or UsdGeom.GetStageMetersPerUnit(stage) != 1 or UsdGeom.GetStageUpAxis(stage) != "Z"):
        raise ValueError("USD time base or units differ")
    count = 0
    for j, run in enumerate(lab["runs"]):
        path = "/World/" + run["id"].replace("-", "_")
        parent = UsdGeom.Xform.Get(stage, path).GetOrderedXformOps()
        sphere = UsdGeom.Sphere.Get(stage, path + "/projectile")
        if len(parent) != 1 or list(parent[0].Get()) != [0, j, 0] or sphere.GetRadiusAttr().Get() != .1:
            raise ValueError("USD layout or sphere size differs")
        ops = sphere.GetOrderedXformOps()
        vel = sphere.GetPrim().GetAttribute("reel:velocity")
        times = list(range(1, SAMPLES + 1))
        if len(ops) != 1 or ops[0].GetTimeSamples() != times or vel.GetTimeSamples() != times:
            raise ValueError("USD is missing recorded samples")
        for f in run["frames"]:
            if (list(ops[0].Get(f["sample"] + 1)) != f["position_m"]
                    or list(vel.Get(f["sample"] + 1)) != f["velocity_m_s"]):
                raise ValueError("USD position or velocity differs")
            count += 1
    return count
