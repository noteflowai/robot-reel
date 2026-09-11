"""Small, explicitly labeled physical-AI demo packs. No hardware or driving model."""
import json
from pathlib import Path

import imageio_ffmpeg
import mujoco

from .capture import FPS, HEIGHT, WIDTH


VEHICLE_CONFIG = {
    "initial_speed_mps": 8.0, "mass_kg": 500.0, "max_deceleration_mps2": 6.0,
    "obstacle_x_m": 30.0, "obstacle_half_length_m": .4, "car_half_length_m": 1.1,
    "early_trigger_gap_m": 14.0, "late_trigger_gap_m": 2.0, "duration_s": 6.0,
}


def vehicle_xml():
    markings = "".join(f'<geom type="box" pos="{x} 0 .015" size=".8 .035 .01" rgba=".8 .9 .95 1" contype="0" conaffinity="0"/>'
                       for x in range(-10, 61, 4))
    wheels = "".join(f'<geom type="cylinder" pos="{x} {y} -.12" size=".25 .12" euler="1.5708 0 0" rgba=".035 .045 .06 1" mass="0" contype="0" conaffinity="0"/>'
                     for x in (-.65, .65) for y in (-.65, .65))
    return f"""<mujoco model="Robot Reel longitudinal braking">
      <option timestep="0.002" gravity="0 0 -9.81"/>
      <visual><global offwidth="{WIDTH}" offheight="{HEIGHT}"/><headlight ambient=".4 .4 .45"/></visual>
      <worldbody>
        <light pos="10 -8 12" dir="0 0 -1" diffuse=".9 .95 1"/>
        <geom name="ground" type="plane" size="100 10 .1" rgba=".065 .085 .12 1"/>
        <geom type="box" pos="20 -2 .04" size="40 .06 .03" rgba=".3 .95 .8 1" contype="0" conaffinity="0"/>
        <geom type="box" pos="20 2 .04" size="40 .06 .03" rgba=".3 .95 .8 1" contype="0" conaffinity="0"/>
        {markings}
        <geom name="obstacle" type="box" pos="30 0 .8" size=".4 1 .8" rgba=".96 .25 .2 1"/>
        <body name="vehicle" pos="0 0 .45">
          <joint name="position" type="slide" axis="1 0 0" damping="0"/>
          <geom name="chassis" type="box" size="1.1 .6 .22" mass="500" rgba=".16 .55 .96 1"/>
          <geom name="cabin" type="box" pos="-.1 0 .37" size=".55 .5 .18" mass="0" rgba=".16 .22 .31 1" contype="0" conaffinity="0"/>
          <geom type="box" pos="1.105 0 .06" size=".01 .45 .06" mass="0" rgba=".7 1 1 1" contype="0" conaffinity="0"/>
          {wheels}
        </body>
      </worldbody><actuator><motor name="brake" joint="position" gear="1" ctrllimited="true" ctrlrange="-3000 3000"/></actuator>
    </mujoco>"""


def brake_trial(output, early):
    config = VEHICLE_CONFIG
    name = "braking_early" if early else "braking_late"
    model = mujoco.MjModel.from_xml_string(vehicle_xml())
    data = mujoco.MjData(model)
    data.qvel[0] = config["initial_speed_mps"]
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)
    camera = mujoco.MjvCamera()
    camera.distance, camera.azimuth, camera.elevation = 19, 145, -35
    writer = imageio_ffmpeg.write_frames(str(output/f"{name}-raw.mp4"), (WIDTH, HEIGHT),
        fps=FPS, codec="libx264", pix_fmt_out="yuv420p", quality=8,
        macro_block_size=2, ffmpeg_log_level="error")
    writer.send(None)
    trigger = config["early_trigger_gap_m"] if early else config["late_trigger_gap_m"]
    contact_x = config["obstacle_x_m"] - config["obstacle_half_length_m"] - config["car_half_length_m"]
    nominal_gap = config["early_trigger_gap_m"] - config["initial_speed_mps"]**2/(2*config["max_deceleration_mps2"])
    reference = [0., nominal_gap, contact_x-nominal_gap]
    obstacle = model.geom("obstacle").id
    chassis = model.geom("chassis").id
    frames, actions = [], []
    braking, collision = False, False
    first_contact_time = None
    try:
        for i in range(round(config["duration_s"]*FPS)):
            steps = round((i+1)/FPS/model.opt.timestep)-round(i/FPS/model.opt.timestep)
            for _ in range(steps):
                gap = contact_x-float(data.qpos[0])
                braking = braking or gap <= trigger
                if braking:
                    # A bounded force on a one-dimensional rigid-body surrogate.
                    data.ctrl[0] = -config["mass_kg"]*config["max_deceleration_mps2"] if data.qvel[0] > .05 else -config["mass_kg"]*20*data.qvel[0]
                else:
                    data.ctrl[0] = 0.
                mujoco.mj_step(model, data)
                for c in data.contact:
                    if {c.geom1, c.geom2} == {obstacle, chassis} and c.dist <= 0:
                        collision = True
                        if first_contact_time is None:
                            first_contact_time = float(data.time)
            gap = contact_x-float(data.qpos[0])
            label = "Impact detected." if collision else ("Brake before the hazard." if braking else "Same road. Same speed.")
            state = [float(data.qvel[0]), gap, float(data.qpos[0])]
            frames.append({"frame": i, "sim_time": float(data.time), "label": label,
                           "mode": "physics", "source": "scripted", "qpos": state,
                           "target": reference, "collision": collision,
                           "brake_force_n": float(data.ctrl[0])})
            camera.lookat[:] = [float(data.qpos[0])+4, 0, .35]
            renderer.update_scene(data, camera=camera)
            writer.send(renderer.render())
    finally:
        writer.close()
        renderer.close()
    outcome = {"collision": collision, "first_contact_time_s": first_contact_time,
               "minimum_gap_m": min(f["qpos"][1] for f in frames),
               "final_gap_m": frames[-1]["qpos"][1], "final_speed_mps": frames[-1]["qpos"][0]}
    trace = {
        "robot": name, "kind": "braking", "fps": FPS, "timestep": model.opt.timestep,
        "display_name": "EARLY BRAKE" if early else "LATE BRAKE", "eyebrow": "AUTOMOTIVE / CONTROL TEST",
        "description": "Scripted longitudinal controller", "disclaimer": "1D surrogate / no driving AI",
        "joints": ["speed", "gap", "position"], "display_joints": ["speed", "gap", "position"],
        "units": ["m/s", "m", "m"], "limits": [[0, 8], [-1, 29], [0, 31]],
        "home": [8, contact_x, 0], "frames": frames, "actions": actions,
        "config": {**config, "trigger_gap_m": trigger}, "outcome": outcome,
        "reference_note": "References show nominal early-braking standstill values; they are not a learned trajectory.",
    }
    (output/f"{name}-trace.json").write_text(json.dumps(trace, indent=2))
    return trace


def run_pack(output: Path, pack: str, speed=.5):
    from .capture import manifest
    from .film import render
    from .viewer import export_viewer
    output.mkdir(parents=True, exist_ok=True)
    if any(output.glob("*-trace.json")):
        raise ValueError("Output already contains a capture; choose a fresh directory")
    if pack == "braking":
        (output/"vehicle.xml").write_text(vehicle_xml())
        late, early = brake_trial(output, False), brake_trial(output, True)
        if not late["outcome"]["collision"] or early["outcome"]["collision"]:
            raise RuntimeError("Braking comparison did not produce the expected contact contrast")
        names = [late["robot"], early["robot"]]
    else:
        from .microduck import record_microduck
        names = record_microduck(output, speed=speed)
    render(output, names=names)
    manifest(output, "scripted", None, None, scene_names=names, pack=pack)
    export_viewer(output)
    manifest(output, "scripted", None, None, scene_names=names, pack=pack)
    print(f"Done: {output.resolve()} (open index.html)", flush=True)
