"""Typed MCP tools for agents directing recorded motion. Transport: local stdio."""
import argparse
from pathlib import Path

from .director import export_director, inspect_source, verify_director


def inside_root(root, name):
    if not isinstance(name, str) or not name:
        raise ValueError("Provide a path relative to the configured workspace")
    candidate = (root/name).resolve()
    if Path(name).is_absolute() or candidate == root or root not in candidate.parents:
        raise ValueError("Path must stay inside the configured workspace")
    return candidate


def create_server(root):
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations
    from pydantic import BaseModel, ConfigDict
    from typing import Literal

    class Shot(BaseModel):
        model_config = ConfigDict(extra="forbid")
        start: int
        end: int
        camera: Literal["overview", "tracking", "impact", "top"]
        rate: Literal[.5, 1]
        caption: str

    server = MCPServer(
        "Robot Reel Director",
        instructions=(
            "Turn a user's natural-language film brief into a storyboard over a recorded run. "
            "First inspect_recording; use actual event frames and outcomes. Then create_storyboard. "
            "Cover every source frame in order using exclusive end indices. Slow motion repeats "
            "samples. Tools export validated data and trusted builder scripts; they do not execute "
            "Blender, shell commands, model calls or arbitrary Python. Captions are editorial text, "
            "not independently verified facts. Preserve the simulation-only scope."
        ),
    )

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def inspect_recording(source: str) -> dict:
        """Inspect a capture/comparison path relative to the configured workspace.

        Returns recorded contact/braking events, outcome summaries and supported cameras.
        """
        try:
            return inspect_source(inside_root(root, source))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False))
    def create_storyboard(source: str, output: str, brief: str, title: str,
                          shots: list[Shot], theme: Literal["midnight", "daylight"] = "midnight") -> dict:
        """Export a validated storyboard into a new relative output directory.

        Use the user's brief to choose cuts and captions. Input trajectories remain unchanged.
        """
        try:
            destination = inside_root(root, output)
            plan = {
                "schema": "robot-reel-director-1", "brief": brief, "title": title, "theme": theme,
                "shots": [shot.model_dump() for shot in shots],
            }
            export_director(inside_root(root, source), destination, plan)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise ToolError(str(exc)) from exc
        return {
            **verify_director(destination), "output": str(destination.relative_to(root)),
            "builder": str((destination/"build_directed_scene.py").relative_to(root)),
            "next_step": "Run the trusted Blender builder documented in docs/director.md.",
        }

    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Explicit workspace boundary for all tool paths")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("--root must be an existing directory")
    try:
        create_server(root).run(transport="stdio")
    except ImportError as exc:
        parser.exit(1, f"Missing MCP dependency: {exc}. Install: pip install -e '.[director]'\n")


if __name__ == "__main__":
    main()
