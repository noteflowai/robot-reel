"""Fetch two pinned npm packages and copy the exact Scene Lab browser dependencies."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

PACKAGES = {
    "@sparkjsdev/spark": ("2.2.0", {
        "dist/spark.module.min.js": "spark.module.min.js", "LICENSE": "SPARK-LICENSE",
    }),
    "three": ("0.180.0", {
        "build/three.module.min.js": "three.module.min.js",
        "build/three.core.min.js": "three.core.min.js",
        "examples/jsm/controls/OrbitControls.js": "addons/controls/OrbitControls.js",
        "examples/jsm/loaders/GLTFLoader.js": "addons/loaders/GLTFLoader.js",
        "examples/jsm/utils/BufferGeometryUtils.js": "addons/utils/BufferGeometryUtils.js",
        "examples/jsm/postprocessing/Pass.js": "addons/postprocessing/Pass.js",
        "LICENSE": "THREE-LICENSE",
    }),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    for name, (version, members) in PACKAGES.items():
        url = f"https://registry.npmjs.org/{name}/{version}"
        with urllib.request.urlopen(url, timeout=30) as response:
            metadata = json.loads(response.read(2_000_000))
        tarball = metadata["dist"]["tarball"]
        if not tarball.startswith("https://registry.npmjs.org/"):
            raise ValueError("unexpected npm tarball origin")
        with urllib.request.urlopen(tarball, timeout=60) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise ValueError("npm archive exceeds the supported size")
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
        if integrity != metadata["dist"]["integrity"]:
            raise ValueError("npm package integrity differs")
        files = {}
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member, target in members.items():
                entry = archive.getmember("package/" + member)
                if not entry.isfile() or entry.size > 8 * 1024 * 1024:
                    raise ValueError("unexpected browser dependency file")
                content = archive.extractfile(entry).read()
                destination = args.output / target
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                files[target] = {
                    "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
                }
        records.append({
            "name": name, "version": version, "license": metadata["license"],
            "registry_metadata": url, "integrity": integrity, "files": files,
        })
    (args.output / "vendor.json").write_text(json.dumps({
        "schema": "robot-reel.scene-vendor.v1", "packages": records,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
