#!/usr/bin/env python3
"""No-op PreToolUse hook stub.

The global Claude Code config (~/.claude/settings.json) runs this script
before every Bash tool call, but no project-specific logic exists for
py-MD-viewer yet. This stub just exits cleanly so Bash isn't blocked.
"""
import sys

sys.stdin.read()
sys.exit(0)
