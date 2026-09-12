"""Lossless JSON telemetry interchange; MCAP is an optional dependency."""
import argparse
import json
from pathlib import Path

from .stress import canonical_hash


def records(traces):
    for trace in traces:
        trial = trace["stress"]["trial_id"]
        for kind, rows in (("observation", trace["frames"]), ("inference", trace["inference_calls"])):
            for row in rows:
                yield f"/{trial}/{kind}", row["frame"], round(row["frame"]/trace["fps"]*1_000_000_000), {
                    "trial_id": trial, "kind": kind, "sample": row,
                }


def export_mcap(traces, path):
    from mcap.writer import Writer
    with Path(path).open("wb") as stream:
        writer = Writer(stream)
        writer.start(library="robot-reel")
        schema = writer.register_schema("robot-reel.telemetry", "jsonschema", json.dumps({
            "type": "object", "required": ["trial_id", "kind", "sample"],
            "properties": {"trial_id": {"type": "string"}, "kind": {"type": "string"}, "sample": {"type": "object"}},
        }).encode())
        writer.add_metadata("robot-reel", {
            "clock": "episode-relative nanoseconds; every trial starts at zero, not UTC",
            "traces_sha256": canonical_hash(traces),
            "action_units": "normalized controls [-1,1], not joint angles",
            "videos": "separate MP4 files; raw observation pixel hashes are in telemetry",
        })
        channels = {}
        for topic, sequence, stamp, row in records(traces):
            if topic not in channels:
                channels[topic] = writer.register_channel(topic, "json", schema)
            writer.add_message(channels[topic], stamp, json.dumps(row, separators=(",", ":"), allow_nan=False).encode(), stamp, sequence)
        writer.finish()
    return check_mcap(traces, path)


def check_mcap(traces, path):
    from mcap.reader import make_reader
    from itertools import zip_longest
    count = 0
    with Path(path).open("rb") as stream:
        reader = make_reader(stream, validate_crcs=True)
        metadata = list(reader.iter_metadata())
        if len(metadata) != 1 or metadata[0].name != "robot-reel" or metadata[0].metadata.get("traces_sha256") != canonical_hash(traces):
            raise ValueError("MCAP trace provenance mismatch")
        for expected, actual in zip_longest(records(traces), reader.iter_messages(log_time_order=False)):
            if expected is None or actual is None:
                raise ValueError("MCAP message count mismatch")
            topic, sequence, stamp, row = expected
            schema, channel, message = actual
            if (
                schema is None or schema.encoding != "jsonschema" or schema.name != "robot-reel.telemetry"
                or channel.topic != topic or channel.message_encoding != "json"
                or message.sequence != sequence or message.log_time != stamp or message.publish_time != stamp
                or json.loads(message.data) != row
            ):
                raise ValueError("MCAP telemetry differs from the source trace")
            count += 1
    return {"messages": count, "trials": len(traces)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    from .stress_site import load_collection, verify_site
    verify_site(args.directory)
    _, _, traces = load_collection(args.directory)
    print(json.dumps(check_mcap(traces, args.directory/"telemetry.mcap"), indent=2))


if __name__ == "__main__":
    main()
