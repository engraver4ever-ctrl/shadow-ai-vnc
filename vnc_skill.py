#!/usr/bin/env python3
"""
Skill wrapper for VNC operations using shadow-ai-vnc or direct vncdotool.

Configuration via environment variables:
- VNC_SERVER: VNC server IP (default: localhost)
- VNC_PORT: VNC port (default: 5900)
- VNC_PASSWORD: VNC password (required)
- VNC_TIMEOUT: Connection timeout in seconds (default: 30)
"""

import subprocess
import json
import os
from pathlib import Path

VNC_SERVER = os.environ.get("VNC_SERVER", "localhost")
VNC_PORT = int(os.environ.get("VNC_PORT", "5900"))
VNC_PASSWORD = os.environ.get("VNC_PASSWORD")
VNC_TIMEOUT = int(os.environ.get("VNC_TIMEOUT", "30"))

def run_vncdotool(*args):
    """Run vncdotool CLI directly."""
    if not VNC_PASSWORD:
        return {
            "success": False,
            "error": "VNC_PASSWORD environment variable not set"
        }
    
    cmd = ["vncdotool", "-s", f"{VNC_SERVER}::{VNC_PORT}", "-p", VNC_PASSWORD, "-t", str(VNC_TIMEOUT)]
    cmd.extend(args)
    
    result = subprocess.run(cmd, capture_output=True, timeout=VNC_TIMEOUT + 10)
    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stderr": result.stderr.decode() if result.stderr else None
    }

def vnc_screenshot(output_path: str) -> dict:
    """Capture screenshot and return metadata."""
    result = run_vncdotool("capture", output_path)
    
    if result["success"] and os.path.exists(output_path):
        try:
            from PIL import Image
            with Image.open(output_path) as img:
                width, height = img.size
            return {
                "success": True,
                "path": str(Path(output_path).absolute()),
                "width": width,
                "height": height
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    return {"success": False, "error": result.get("stderr", "Screenshot failed")}

def vnc_key(key: str) -> dict:
    """Send key press."""
    result = run_vncdotool("key", key)
    return {"success": result["success"], "action": f"key:{key}"}

def vnc_type(text: str) -> dict:
    """Type text."""
    result = run_vncdotool("type", text)
    return {"success": result["success"], "action": "type"}

def vnc_click(x: int, y: int, button: int = 1) -> dict:
    """Click at coordinates."""
    # Move first
    run_vncdotool("move", str(x), str(y))
    # Then click
    button_map = {1: "left", 2: "mid", 3: "right"}
    btn = button_map.get(button, "left")
    result = run_vncdotool("click", btn)
    return {"success": result["success"], "action": "click", "x": x, "y": y}

def vnc_move(x: int, y: int) -> dict:
    """Move mouse."""
    result = run_vncdotool("move", str(x), str(y))
    return {"success": result["success"], "action": "move", "x": x, "y": y}

# Example usage if run directly
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: vnc_skill.py <command> [args...]")
        print("Commands: screenshot <path>, key <key>, type <text>, click <x> <y>, move <x> <y>")
        print()
        print("Environment variables:")
        print("  VNC_SERVER    - VNC server IP (default: localhost)")
        print("  VNC_PORT      - VNC port (default: 5900)")
        print("  VNC_PASSWORD  - VNC password (required)")
        print("  VNC_TIMEOUT   - Connection timeout (default: 30)")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "screenshot":
        result = vnc_screenshot(sys.argv[2] if len(sys.argv) > 2 else "/tmp/vnc_screenshot.png")
    elif cmd == "key":
        result = vnc_key(sys.argv[2] if len(sys.argv) > 2 else "Return")
    elif cmd == "type":
        result = vnc_type(sys.argv[2] if len(sys.argv) > 2 else "Hello")
    elif cmd == "click":
        x = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        y = int(sys.argv[3]) if len(sys.argv) > 3 else 100
        result = vnc_click(x, y)
    elif cmd == "move":
        x = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        y = int(sys.argv[3]) if len(sys.argv) > 3 else 100
        result = vnc_move(x, y)
    else:
        result = {"success": False, "error": f"Unknown command: {cmd}"}
    
    print(json.dumps(result, indent=2))
