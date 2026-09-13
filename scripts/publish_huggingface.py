"""Publish only the files in a verified Space bundle using an authenticated Hub account."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_huggingface import MANIFEST, SOURCE, verify


def publish(directory, repo_id):
    directory = Path(directory).resolve()
    record = verify(directory)
    if record["source_dirty"]:
        raise ValueError("Preview bundle has uncommitted source; build from a clean commit")
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.utils import validate_repo_id

    validate_repo_id(repo_id)
    if len(repo_id.split("/")) != 2:
        raise ValueError("Supply an explicit account/space ID")
    api = HfApi()
    api.whoami()  # Resolve auth before creating anything. Never print or persist the token here.
    receipt = directory.parent/(".hf-"+repo_id.replace("/", "--")+".json")
    if not api.repo_exists(repo_id, repo_type="space"):
        api.create_repo(repo_id, repo_type="space", space_sdk="static", private=False)
        parent = api.space_info(repo_id).sha
        # Recover an interrupted first upload only when this process created the
        # still-unchanged empty Space. Never infer ownership from an empty repo.
        receipt.write_text(json.dumps({"repo_id": repo_id, "initial_head": parent,
                                       "source_repository": SOURCE})+"\n")
        previous = set()
    else:
        info = api.space_info(repo_id)
        if info.sdk != "static" or info.private:
            raise ValueError("Refusing to change an existing Space's SDK or visibility")
        parent = info.sha
        try:
            old_path = hf_hub_download(repo_id, MANIFEST, repo_type="space", revision=info.sha)
        except Exception as exc:
            created = json.loads(receipt.read_text()) if receipt.exists() else {}
            if created != {"repo_id": repo_id, "initial_head": parent, "source_repository": SOURCE}:
                raise ValueError("Existing Space has no Robot Reel manifest; refusing to overwrite it") from exc
            previous = set()
        else:
            old = json.loads(Path(old_path).read_text())
            if old.get("source_repository") != SOURCE:
                raise ValueError("Existing Space belongs to a different source project")
            previous = set(old["files"])
    allowed = sorted(set(record["files"]) | {MANIFEST})
    commit = api.upload_folder(
        repo_id=repo_id, repo_type="space", folder_path=directory,
        allow_patterns=allowed, delete_patterns=sorted(previous-set(allowed)) or None,
        parent_commit=parent, commit_message="Sync verified Robot Reel "+record["source_commit"][:12],
    )
    return {"repo_id": repo_id, "source_commit": record["source_commit"], "hub_commit": commit.oid,
            "space_url": f"https://huggingface.co/spaces/{repo_id}", "files": len(allowed)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repo-id", default="glayguo/robot-reel")
    args = parser.parse_args()
    print(json.dumps(publish(args.bundle, args.repo_id), indent=2))
