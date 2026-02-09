"""Simple MCP server exposing a terminal tool to run shell commands."""

import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Terminal Server")


@mcp.resource("file://desktop/testRigor-README")
def testrigor_readme() -> str:
    """Read the content of testRigor-README.md from the user's Desktop folder."""
    path = Path.home() / "Desktop" / "testRigor-README.md"
    if not path.exists():
        return f"File not found: {path}"
    return path.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
def run_terminal_command(command: str, args: str = "") -> str:
    """Run a terminal command with optional arguments. E.g. command='mkdir', args='/test' runs mkdir /test."""
    try:
        cmd_list = [command] + (args.split() if args.strip() else [])
        result = subprocess.run(
            cmd_list,
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout or ""
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 60 seconds"
    except Exception as e:
        return f"Error: {e}"


def main():
    # Initialize and run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

