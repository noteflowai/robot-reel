"""Build an offline review from original episodes and every frozen model output."""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.claim_review import review_claims


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(destination):
    if destination.exists():
        raise ValueError("Use a new output directory")
    source = ROOT/"examples/model-review"
    sources = json.loads((source/"sources.json").read_text())
    protocol = json.loads((source/"protocol.json").read_text())
    expected = {f"{case['id']}-{seed}.json" for case in protocol["cases"] for seed in protocol["seeds"]}
    found = {p.name for p in (source/"recorded").glob("*.json")} - {"identity.json", "protocol.json"}
    if found != expected:
        raise ValueError("Recorded output inventory differs from the frozen protocol")
    if (source/"recorded/protocol.json").read_bytes() != (source/"protocol.json").read_bytes():
        raise ValueError("The recording used a different protocol")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".model-review-", dir=destination.parent) as temporary:
        stage = Path(temporary)/"site"
        stage.mkdir()
        for name in ("protocol.json", "sources.json", "NOTICE.txt", "README.md", "record.py",
                     "runtime-environment.json", "runtime-failures.json", "model-files.json"):
            shutil.copyfile(source/name, stage/name)
        shutil.copytree(source/"recorded", stage/"recorded")
        episodes = []
        for item in sources:
            run = ROOT/item["source_directory"]
            for name, expected_hash in item["files"].items():
                if digest(run/name) != expected_hash:
                    raise ValueError(f"Original source changed: {run/name}")
            if digest(source/item["sheet"]) != item["sheet_sha256"]:
                raise ValueError("The model's contact sheet changed")
            shutil.copyfile(source/item["sheet"], stage/item["sheet"])
            media = stage/"media"/item["id"]
            media.mkdir(parents=True)
            for name in ("trace.json", "main.mp4", "wrist.mp4", "main-poster.png", "wrist-poster.png"):
                shutil.copyfile(run/name, media/name)
            trace = json.loads((run/"trace.json").read_text())
            reviews = {}
            for mode in ("images-only", "with-record"):
                record = json.loads((source/f"recorded/{item['id']}-{mode}-17.json").read_text())
                if record["protocol_sha256"] != digest(source/"protocol.json"):
                    raise ValueError("Generation is bound to another protocol")
                claims = None
                display_claims = None
                try:
                    claims = json.loads(record["text"])
                    report = review_claims(trace, claims)
                except (ValueError, TypeError) as error:
                    # Keep strict parsing failed. An exact JSON fence can be
                    # removed for reading the explanation only, never scoring.
                    text = record["text"].strip()
                    if text.startswith("```json\n") and text.endswith("\n```"):
                        try:
                            display_claims = json.loads(text[8:-4])
                            if not isinstance(display_claims, dict):
                                display_claims = None
                        except (ValueError, TypeError):
                            pass
                    report = {"schema": "robot-reel-claim-review-1", "facts_match": False,
                              "error": str(error), "explanation_status": "not_assessed"}
                reviews[mode] = {"claims": claims, "display_claims": display_claims,
                                 "review": report, "record": record}
            episodes.append({**item, "reviews": reviews})
        data = {"schema": "robot-reel-model-review-1", "episodes": episodes}
        (stage/"review.json").write_text(json.dumps(data, indent=2)+"\n")
        payload = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")
        page = (ROOT/"scripts/model_review.html").read_text().replace("__LAB_DATA__", payload)
        (stage/"index.html").write_text(page)
        files = {p.relative_to(stage).as_posix(): digest(p) for p in stage.rglob("*") if p.is_file()}
        (stage/"manifest.json").write_text(json.dumps({"schema": "robot-reel-model-review-files-1",
                                                       "files": files}, indent=2)+"\n")
        with zipfile.ZipFile(stage/"review.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file() and path.name != "review.zip":
                    info = zipfile.ZipInfo(path.relative_to(stage).as_posix(), (2020, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, path.read_bytes())
        verify(stage)
        stage.rename(destination)
    return data


def verify(folder):
    manifest = json.loads((folder/"manifest.json").read_text())
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"manifest.json", "review.zip"}:
        raise ValueError("Unexpected review files")
    for name, expected in manifest["files"].items():
        if digest(folder/name) != expected:
            raise ValueError(f"Review file changed: {name}")
    with zipfile.ZipFile(folder/"review.zip") as archive:
        expected = actual - {"review.zip"}
        if len(archive.namelist()) != len(expected) or set(archive.namelist()) != expected:
            raise ValueError("Offline archive inventory differs")
        for name in expected:
            if archive.read(name) != (folder/name).read_bytes():
                raise ValueError(f"Offline archive changed: {name}")
    for episode in json.loads((folder/"review.json").read_text())["episodes"]:
        trace = json.loads((folder/f"media/{episode['id']}/trace.json").read_text())
        for selected in episode["reviews"].values():
            if "error" not in selected["review"] and review_claims(trace, selected["claims"]) != selected["review"]:
                raise ValueError("Recomputed claim checks differ")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/model-review")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify(args.output)
    else:
        build(args.output)
    print("Model review and offline archive verified")
