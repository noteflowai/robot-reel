"""Check the actual gated Cosmos dependencies without downloading or accepting terms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = "nvidia/Cosmos-Predict2-2B-Video2World"
REVISION = "f50c09f5d8ab133a90cac3f4886a6471e9ba3f18"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new access-report path")
    from huggingface_hub import get_hf_file_metadata, get_token, hf_hub_url
    from huggingface_hub.errors import HfHubHTTPError

    rows = []
    for name in ("model-480p-16fps.pt", "tokenizer/tokenizer.pth"):
        try:
            metadata = get_hf_file_metadata(
                hf_hub_url(REPO, name, revision=REVISION), token=get_token()
            )
            rows.append({
                "file": name, "accessible": True, "bytes": metadata.size,
                "etag": metadata.etag, "http_status": 200,
            })
        except HfHubHTTPError as error:
            rows.append({
                "file": name, "accessible": False,
                "http_status": error.response.status_code,
                "error_type": type(error).__name__,
            })
    report = {
        "schema": "robot-reel.cosmos-access.v1", "repository": REPO,
        "revision": REVISION, "dependencies": rows,
        "ready": all(row["accessible"] for row in rows),
        "scope": (
            "Authenticated file-metadata access only. No terms were accepted, access request "
            "submitted, gated model downloaded, or inference performed by this check."
        ),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    if not report["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
