"""MCP server for Blacknode workflows.

Provides tool functions in ``blacknode.mcp.tools`` that are pure-Python and
unit-testable without the MCP runtime. ``blacknode.mcp.server`` wraps those
functions as FastMCP tools and is what gets launched by ``blacknode mcp``.
"""
from __future__ import annotations


def main() -> None:
    from .server import main as _main

    _main()


__all__ = ["main"]
