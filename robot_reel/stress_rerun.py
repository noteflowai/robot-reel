"""Export one paired Stress Lab seed to a checked, portable Rerun recording."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile

from .stress import CONDITIONS, canonical_hash, file_hash
from .stress_site import load_collection, verify_site

SDK_VERSION = "0.37.2"
SCHEMA = "robot-reel-stress-rerun-1"
COLORS = {"reference": (121, 223, 195), "dim": (193, 177, 255), "camera": (255, 202, 133)}


def selection(directory, seed):
    """Select complete paired trials while retaining the full experiment's scope."""
    document, attempts, traces = load_collection(directory)
    if type(seed) is not int or seed not in document["seeds"]:
        raise ValueError("Choose a seed in the recorded experiment")
    selected = [trace for trace in traces if trace["seed"] == seed]
    if [trace["stress"]["condition"] for trace in selected] != [c["id"] for c in CONDITIONS]:
        raise ValueError("The selected seed must have all three completed conditions")
    paths = {attempt["trial_id"]: Path(directory)/attempt["directory"] for attempt in attempts
             if attempt["status"] == "completed"}
    return document, selected, paths


def provenance(document, traces):
    return {
        "schema": SCHEMA, "rerun_version": SDK_VERSION, "seed": traces[0]["seed"],
        "selected_trials": len(traces), "experiment_trials": len(document["seeds"])*len(CONDITIONS),
        "plan_sha256": canonical_hash(document), "traces_sha256": canonical_hash(traces),
        "clock": "episode-relative nanoseconds; sample N is observation N at 20 Hz",
        "position": "measured end-effector xyz in simulator world coordinates, metres, Z up",
        "controls": "normalized applied controls [-1,1]; terminal observations have no action",
        "display": "complete recorded paths; camera holds final image; markers clear after termination",
        "trials": [{"id": t["stress"]["trial_id"], "condition": t["stress"]["condition"],
                    "outcome": t["result"]["outcome"], "actions": t["result"]["actions"],
                    "observations": len(t["frames"]), "inference_calls": len(t["inference_calls"]),
                    "end_seconds": t["frames"][-1]["episode_time"]} for t in traces],
    }


def blueprint(traces):
    import rerun.blueprint as rrb
    keys = [c["id"] for c in CONDITIONS]
    positions = [frame["state"][:3] for trace in traces for frame in trace["frames"]]
    low = [min(p[i] for p in positions) for i in range(3)]
    high = [max(p[i] for p in positions) for i in range(3)]
    center = [(a+b)/2 for a, b in zip(low, high)]
    span = max(b-a for a, b in zip(low, high)) or .1
    cameras = []
    for camera in ("main", "wrist"):
        views = []
        for trace, condition in zip(traces, CONDITIONS):
            label = f'{condition["label"]} · {trace["result"]["outcome"]} · ends {trace["frames"][-1]["episode_time"]:.2f}s'
            views.append(rrb.Spatial2DView(name=label, origin=f'/cameras/{condition["id"]}/{camera}'))
        cameras.append(rrb.Horizontal(*views, name="Scene cameras" if camera == "main" else "Wrist cameras"))
    plots = rrb.Tabs(
        rrb.TimeSeriesView(name="Applied gripper · normalized [-1,1]", contents=[f"/controls/{key}/gripper" for key in keys],
                           axis_y=rrb.ScalarAxis(range=(-1, 1))),
        rrb.TimeSeriesView(name="Policy calls · measured seconds", contents=[f"/inference/{key}/policy_seconds" for key in keys]),
        rrb.TimeSeriesView(name="Applied XYZ controls · normalized",
                           contents=[f"/controls/{key}/{channel}" for key in keys for channel in ("delta_x", "delta_y", "delta_z")]),
        active_tab=0,
    )
    return rrb.Blueprint(
        rrb.Tabs(
            rrb.Vertical(
                rrb.Tabs(*cameras, active_tab=0),
                rrb.Horizontal(
                    rrb.Spatial3DView(name="Measured EEF · full paths · metres", origin="/world",
                                      background=(9, 18, 27), line_grid=True,
                                      eye_controls=rrb.EyeControls3D(
                                          position=[c+s*span for c, s in zip(center, (.8, -1, .7))],
                                          look_target=center, eye_up=(0, 0, 1))),
                    plots, column_shares=[.55, .45],
                ), row_shares=[.55, .45], name=f"Seed {traces[0]['seed']:02d} · paired replay",
            ),
            rrb.TextDocumentView(name="Read the experiment", origin="/about"),
            rrb.Tabs(*(rrb.TextDocumentView(name=c["label"], origin=f'/evidence/{c["id"]}/observation')
                       for c in CONDITIONS), name="Exact observation JSON"),
            active_tab=0,
        ),
        rrb.TimePanel(state="expanded", timeline="episode", play_state="paused", playback_speed=1),
        rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"),
        auto_views=False, auto_layout=False,
    )


def _sdk():
    import rerun as rr
    if rr.__version__ != SDK_VERSION:
        raise ValueError(f"Use rerun-sdk=={SDK_VERSION} for this exporter and its reader")
    return rr


def _write(directory, path, seed):
    rr = _sdk()
    document, traces, paths = selection(directory, seed)
    meta = provenance(document, traces)
    recording = rr.RecordingStream("robot-reel-stress", recording_id=f"seed-{seed:02d}-{meta['traces_sha256']}")
    recording.save(path, default_blueprint=blueprint(traces))

    def log(entity, value, static=False):
        recording.log(entity, value, static=static, strict=True)

    def clock(sample):
        recording.set_time("episode", duration=sample/20)
        recording.set_time("sample", sequence=sample)

    try:
        log("provenance", rr.TextDocument(json.dumps(meta, sort_keys=True)), True)
        lines = [
            f"# Robot Reel · Seed {seed:02d}",
            f"Three paired trials selected from the {meta['experiment_trials']}-trial experiment.",
            "One LIBERO task, one SmolVLA policy, reference / 25% light / camera +12 cm.",
            "This selected example is not a benchmark or an estimate of general robustness.",
            "## Read the clocks and geometry",
            "Use the **episode** timeline: all trials start at observation zero, at 20 Hz.",
            "The 3D lines contain complete recorded end-effector paths, in world metres (Z up).",
            "They are measured positions, not reconstructed robot meshes or predicted futures.",
            "Moving markers disappear one sample after their final observation.",
            "Camera views hold their final image; each title states its recorded end time and outcome.",
            "Controls end before the terminal observation. Latency points occur only at real policy calls.",
            "The SDK's log_time, if shown, is export time, not simulation or collection time.",
            "## Data that travels with this recording",
            "Six original MP4s, lossless observation/inference JSON, applied controls and measured poses.",
            "Spatial display components use float32 (checked within 1e-6 m); source JSON stays exact.",
            "Videos are embedded; this file needs no remote video server. Open with Rerun 0.37.2.",
            "Apache-2.0 recorder code. The included media notice documents upstream asset terms.",
            "## Trial outcomes",
            *[f"- {t['id']}: {t['outcome']}, {t['actions']} actions, ends {t['end_seconds']:.2f}s."
              for t in meta["trials"]],
        ]
        log("about", rr.TextDocument("\n\n".join(lines), media_type="text/markdown"), True)
        for name in ("NOTICE.txt", "LICENSE"):
            log(f"notices/{name}", rr.TextDocument((Path(directory)/name).read_text()), True)
        log("world", rr.ViewCoordinates.RIGHT_HAND_Z_UP, True)
        for trace, condition in zip(traces, CONDITIONS):
            key, color = condition["id"], COLORS[condition["id"]]
            source = paths[trace["stress"]["trial_id"]]
            log(f"evidence/{key}/trace", rr.TextDocument(json.dumps(trace, sort_keys=True)), True)
            log(f"world/{key}/path", rr.LineStrips3D(
                [[frame["state"][:3] for frame in trace["frames"]]], colors=[color], radii=.0012), True)
            for channel in trace["channels"]:
                log(f"controls/{key}/{channel}", rr.SeriesLines(
                    colors=[color], names=[condition["label"]], interpolation_mode="StepAfter"), True)
            for timing in ("policy_seconds", "env_step_seconds"):
                log(f"inference/{key}/{timing}", rr.SeriesPoints(colors=[color], names=[condition["label"]]), True)
            for camera in ("main", "wrist"):
                video = rr.AssetVideo(path=source/f"{camera}.mp4")
                timestamps = video.read_frame_timestamps_nanos().tolist()
                if timestamps != [frame["frame"]*50_000_000 for frame in trace["frames"]]:
                    raise ValueError("Video presentation timestamps differ from the source samples")
                log(f"cameras/{key}/{camera}", video, True)
            for frame in trace["frames"]:
                clock(frame["frame"])
                log(f"world/{key}/tip", rr.Points3D([frame["state"][:3]], colors=[color], radii=.004))
                log(f"evidence/{key}/observation", rr.TextDocument(json.dumps(frame, sort_keys=True)))
                for camera in ("main", "wrist"):
                    log(f"cameras/{key}/{camera}", rr.VideoFrameReference(nanoseconds=frame["frame"]*50_000_000))
                if frame["action"] is None:
                    log(f"controls/{key}", rr.Clear(recursive=True))
                else:
                    for channel, value in zip(trace["channels"], frame["action"]):
                        log(f"controls/{key}/{channel}", rr.Scalars(value))
            clock(len(trace["frames"]))
            log(f"world/{key}/tip", rr.Clear(recursive=False))
            for call in trace["inference_calls"]:
                clock(call["frame"])
                log(f"evidence/{key}/inference", rr.TextDocument(json.dumps(call, sort_keys=True)))
                for timing in ("policy_seconds", "env_step_seconds"):
                    log(f"inference/{key}/{timing}", rr.Scalars(call[timing]))
        recording.flush()
    finally:
        recording.disconnect()
    return meta


def read_components(path):
    """Read native Arrow components back without applying latest-at interpolation."""
    rr = _sdk()
    reader = rr.experimental.RrdReader(path)
    if len(reader.recordings()) != 1 or len(reader.blueprints()) != 1:
        raise ValueError("Expected one recording and one saved viewer blueprint")
    values = {}
    for chunk in reader.stream().to_chunks():
        batch = chunk.to_record_batch()
        if chunk.is_static:
            samples = [None]*batch.num_rows
        else:
            if "sample" not in batch.schema.names or "episode" not in batch.schema.names:
                raise ValueError("Missing source sample or episode clock")
            samples = batch.column("sample").to_pylist()
            nanos = batch.column("episode").cast("int64").to_pylist()
            if nanos != [sample*50_000_000 for sample in samples]:
                raise ValueError("Rerun episode clock differs from the source samples")
        for field, column in zip(batch.schema, batch.columns):
            if (field.metadata or {}).get(b"rerun:kind") != b"data":
                continue
            key = (chunk.entity_path, field.name)
            rows = values.setdefault(key, {})
            for sample, value in zip(samples, column.to_pylist()):
                if value is not None:
                    if sample in rows:
                        raise ValueError(f"Duplicate Rerun component at {key}/{sample}")
                    rows[sample] = value
    return values


def verify(directory, path, seed=0):
    document, traces, paths = selection(directory, seed)
    actual = read_components(path)

    def require(entity, component, expected, tolerance=None):
        rows = actual.get((entity, component), {})
        if tolerance is None:
            equal = rows == expected
        else:
            def close(a, b):
                if isinstance(b, list):
                    return isinstance(a, list) and len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
                return isinstance(a, (int, float)) and math.isclose(a, b, rel_tol=0, abs_tol=tolerance)
            equal = rows.keys() == expected.keys() and all(close(rows[k], value) for k, value in expected.items())
        if not equal:
            raise ValueError(f"Rerun component differs from source: {entity}/{component}")

    require("/provenance", "TextDocument:text", {None: [json.dumps(provenance(document, traces), sort_keys=True)]})
    for name in ("NOTICE.txt", "LICENSE"):
        require(f"/notices/{name}", "TextDocument:text", {None: [(Path(directory)/name).read_text()]})
    for trace in traces:
        key = trace["stress"]["condition"]
        frames = trace["frames"]
        require(f"/evidence/{key}/trace", "TextDocument:text", {None: [json.dumps(trace, sort_keys=True)]})
        require(f"/evidence/{key}/observation", "TextDocument:text",
                {f["frame"]: [json.dumps(f, sort_keys=True)] for f in frames})
        require(f"/evidence/{key}/inference", "TextDocument:text",
                {c["frame"]: [json.dumps(c, sort_keys=True)] for c in trace["inference_calls"]})
        require(f"/world/{key}/path", "LineStrips3D:strips", {None: [[f["state"][:3] for f in frames]]}, 1e-6)
        require(f"/world/{key}/tip", "Points3D:positions", {f["frame"]: [f["state"][:3]] for f in frames}, 1e-6)
        require(f"/world/{key}/tip", "Clear:is_recursive", {len(frames): [False]})
        require(f"/controls/{key}", "Clear:is_recursive", {frames[-1]["frame"]: [True]})
        for i, channel in enumerate(trace["channels"]):
            require(f"/controls/{key}/{channel}", "Scalars:scalars",
                    {f["frame"]: [f["action"][i]] for f in frames if f["action"] is not None})
            require(f"/controls/{key}/{channel}", "SeriesLines:interpolation_mode", {None: [2]})
        for timing in ("policy_seconds", "env_step_seconds"):
            require(f"/inference/{key}/{timing}", "Scalars:scalars",
                    {c["frame"]: [c[timing]] for c in trace["inference_calls"]})
        for camera in ("main", "wrist"):
            entity = f"/cameras/{key}/{camera}"
            blobs = actual.get((entity, "AssetVideo:blob"), {})
            source = paths[trace["stress"]["trial_id"]]/f"{camera}.mp4"
            if set(blobs) != {None} or len(blobs[None]) != 1 or hashlib.sha256(bytes(blobs[None][0])).hexdigest() != file_hash(source):
                raise ValueError(f"Rerun video differs from source: {entity}")
            require(entity, "VideoFrameReference:timestamp", {f["frame"]: [f["frame"]*50_000_000] for f in frames})
    return {
        **provenance(document, traces), "videos_checked": len(traces)*2,
        "observations_checked": sum(len(t["frames"]) for t in traces),
        "controls_checked": sum(t["result"]["actions"]*len(t["channels"]) for t in traces),
        "inference_calls_checked": sum(len(t["inference_calls"]) for t in traces),
        "rrd_sha256": file_hash(path), "rrd_bytes": Path(path).stat().st_size,
    }


def export(directory, output, seed=0):
    directory, output = Path(directory), Path(output)
    verify_site(directory)
    selection(directory, seed)
    if output.exists():
        raise ValueError("Choose a new .rrd output file")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".rrd", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        _write(directory, temporary, seed)
        result = verify(directory, temporary, seed)
        temporary.chmod(0o644)
        temporary.replace(output)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=0, help="Recorded paired seed (default: 0)")
    parser.add_argument("--verify", action="store_true", help="Read back and verify an existing export")
    args = parser.parse_args(argv)
    action = verify if args.verify else export
    print(json.dumps(action(args.directory, args.output, args.seed), indent=2))


if __name__ == "__main__":
    main()
