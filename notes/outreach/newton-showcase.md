Maintainer disclosure: this is a self-submission from Robot Reel, an independent
project using Newton. Thanks to the Newton and Warp contributors for the public
simulation APIs.

The [Cloth Lab](https://noteflowai.github.io/robot-reel/cloth/) records three
separate Newton 1.6.0 / SolverVBD runs on an NVIDIA L40S, then makes the saved
deformation inspectable in a browser and Blender. No installation is needed
to replay it.

![Three recorded cloth cases](https://raw.githubusercontent.com/noteflowai/robot-reel/858886243c100f866be773d2c32eb13c2e2da917/docs/cloth/poster.png)

Only `edge_ke` changes: 0.01, 1.0 and 100.0. The mesh, two-column clamp, initial
state and integration settings stay the same. The recording contains 121
samples × 3 cases × 117 vertices = **42,471 vertex samples**, with positions
and velocities preserved as float32.

The export keeps deformation as time-sampled USD mesh points and velocities.
Native USD readback checks the samples, topology, clock and presentation
transforms. The Blender 5.2.1 import check evaluates every vertex at every
recorded frame against the source, with a 1e-5 m positional tolerance.
The [method, source layout and reproduction commands](https://github.com/noteflowai/robot-reel/blob/858886243c100f866be773d2c32eb13c2e2da917/docs/cloth.md)
include the exact solver settings.

One practical Blender detail: set the scene to **30 fps** before playback.
Frame 1 corresponds to source sample 0; Blender does not automatically adopt
the USD frame rate. Mesh cache modifiers replay the saved deformation.

Try switching from side-by-side to overlay, selecting a sample, and exporting
its Figure PNG and Sample JSON. The JSON can restore that selection and camera
in another copy of the same recording. The Python verifier recomputes the
measurements from the original vertices.

From the current source checkout, with Python 3.12+:

```bash
python3 -S -m robot_reel.cli cloth --output docs/cloth --verify
```

This verifies the included recording using the standard library. Recording a
new run requires the documented Newton/Warp runtime and chosen device.

For a rigid-body example, the [Butterfly Lab](https://noteflowai.github.io/robot-reel/chaos/)
records 12 isolated CPU Newton worlds, 0.05° apart in release angle.
Its browser time sculpture uses depth for time; the USD contains the physical
link animation. Both native import checks cover all 14,424 recorded body poses.

Scope: these are small, finite-step simulation examples. The cloth has no
collision or self-contact, and its bending coefficients are not calibrated
fabric properties. The rigid-body example uses CPU. Neither experiment is
a new solver, a performance benchmark or a real-robot result.

Code, procedural geometry and these two recordings are Apache-2.0:
[Robot Reel](https://github.com/noteflowai/robot-reel).
Feedback on the recording contract, USD interoperability and missing
inspection channels would be useful.
