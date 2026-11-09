"""CLO3D MCP Server — Control CLO3D via the Model Context Protocol."""

import hashlib
from pathlib import Path

__version__ = "0.1.1"


def _build_stamp():
    """Content hash of this package's sources: detects stale embedded imports."""
    try:
        digest = hashlib.sha256()
        for path in sorted(Path(__file__).resolve().parent.rglob("*.py")):
            digest.update(path.relative_to(Path(__file__).resolve().parent).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()[:12]
    except OSError:
        return "unknown"


BUILD = _build_stamp()


def main():
    """Entry point for the MCP server (used by uvx/pip scripts)."""
    from clo3d_mcp.server import mcp
    mcp.run()
