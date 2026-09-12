"""Install the reviewed launcher with an exact backup and atomic replacement."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile

REVIEWED_SHA256 = "5f6b46a62f486a71b80b1cb0ff40f9ab2526604353ccf139adf50acdc1863af0"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def install(source, target, expected_sha256=REVIEWED_SHA256):
    source, target = Path(source), Path(target)
    data = source.read_bytes()
    compile(data, str(source), "exec")
    if target.is_symlink():
        raise ValueError("Refusing to replace a launcher symlink")
    old = target.read_bytes() if target.exists() else None
    if old == data:
        return None
    if old is not None:
        if target.stat().st_uid != os.getuid():
            raise ValueError("Existing launcher belongs to another user")
        if digest(old) != expected_sha256:
            raise ValueError("Installed launcher changed since review; compare it with the candidate before replacing it")
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if old is not None:
        backup = target.with_name(target.name+".backup."+digest(old)[:12])
        if backup.is_symlink() or backup.exists() and backup.read_bytes() != old:
            raise ValueError("Existing backup does not match the installed launcher")
        if not backup.exists():
            with backup.open("xb") as stream:
                stream.write(old)
                stream.flush()
                os.fsync(stream.fileno())
            backup.chmod(target.stat().st_mode & 0o777)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".agents-install-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o755)
        if (target.read_bytes() if target.exists() else None) != old:
            raise ValueError("Launcher changed during installation; retained the newer file")
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path.home()/".local/bin/agents")
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error("Install as your normal login user, not root")
    try:
        backup = install(Path(__file__).with_name("agents.py"), args.target)
    except (OSError, ValueError, SyntaxError) as exc:
        parser.error(str(exc))
    print(f"Installed: {args.target}")
    if backup:
        print(f"Original backup: {backup}")
    print("Existing agent sessions are unchanged. Exit the active CLI and run agents again for new startup permissions.")


if __name__ == "__main__":
    main()
