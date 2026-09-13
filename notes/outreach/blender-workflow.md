# Draft: Replay recorded GPU cloth in Blender through OpenUSD

Not posted. Intended for Blender Artists → Resources → Released Add-ons and
Extensions, tagged `free`. This is a Python recording/export workflow, not an
installable Blender extension.

---

I'm sharing a free workflow from Robot Reel, a project I maintain, for bringing
recorded cloth deformation into Blender. The simulation runs in Newton; Blender
reads the saved mesh animation so you can change cameras, lights and materials.

![Recorded cloth comparison](https://raw.githubusercontent.com/noteflowai/robot-reel/858886243c100f866be773d2c32eb13c2e2da917/docs/cloth/poster.png)

Try the [browser replay](https://noteflowai.github.io/robot-reel/cloth/) and
download its **USD** or **Offline experiment**. The scene contains three versions
of the same procedural sheet, recorded with different bending coefficients.

In Blender 5.2.1:

1. Set the scene to **30 fps**.
2. Import `scene.usdc` using **File → Import → Universal Scene Description**.
3. Play frames **1–121**. Frame 1 is the untouched initial state at time zero.
   The mesh cache modifiers contain the recorded deformation.
4. Add your own camera, lights and materials. Keep the mesh cache to preserve
   the recorded motion.

The three cases have 117 vertices each. The included Blender import check
compares every vertex in every frame to the original positions, allowing
1e-5 m of positional roundoff. The USD also retains recorded velocities.
Side-by-side spacing is a presentation transform; measurement comparisons use
the original coordinates.

These sheets have no collision or self-contact, and the bending coefficients
are not measured properties of real fabrics. Colors identify the three cases.
The Newton recording used an L40S; replaying or importing it does not require
running that simulation again.

[Source, reproduction commands and import checker](https://github.com/noteflowai/robot-reel/blob/858886243c100f866be773d2c32eb13c2e2da917/docs/cloth.md).
Code, this procedural geometry and its recording are Apache-2.0.

I'd appreciate feedback on USD import behavior in other Blender versions and
what metadata would make recorded simulation scenes easier to reuse.
