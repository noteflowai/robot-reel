"""Exercise the real stdio MCP server, including export and workspace boundaries."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile


async def main():
    from mcp import Client, StdioServerParameters
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from robot_reel.director import verify_director
    (root/"artifacts").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mcp-check-", dir=root/"artifacts") as temporary:
        relative = str(Path(temporary).relative_to(root)/"film")
        config = StdioServerParameters(
            command=sys.executable, args=["-m", "robot_reel.cli", "mcp", "--root", str(root)], cwd=root,
        )
        async with Client(config) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {"inspect_recording", "create_storyboard"}, names
            inspected = await client.call_tool("inspect_recording", {"source": "docs/compare/braking"})
            assert not inspected.is_error
            outside = await client.call_tool("inspect_recording", {"source": "../outside"})
            assert outside.is_error
            plan = json.loads((root/"examples/contact-storyboard.json").read_text())
            arguments = {k: v for k, v in plan.items() if k != "schema"}
            arguments.update(source="docs/compare/braking", output=relative)
            created = await client.call_tool("create_storyboard", arguments)
            assert not created.is_error, created
            assert verify_director(root/relative)["frames"] == 210
            duplicate = await client.call_tool("create_storyboard", arguments)
            assert duplicate.is_error
            arguments["output"] = str(Path(temporary).relative_to(root)/"invalid")
            arguments["shots"][0]["end"] -= 1
            rejected = await client.call_tool("create_storyboard", arguments)
            assert rejected.is_error
    print("MCP stdio: inspection, export, overwrite protection, invalid plans and workspace boundaries passed")


if __name__ == "__main__":
    asyncio.run(main())
