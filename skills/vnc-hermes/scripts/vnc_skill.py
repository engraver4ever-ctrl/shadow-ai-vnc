#!/usr/bin/env python3
"""
Skill wrapper for VNC operations using shadow-ai-vnc (asyncio-native RFB client).

Configuration via environment variables:
- VNC_SERVER: VNC server IP (default: localhost)
- VNC_PORT: VNC port (default: 5900)
- VNC_PASSWORD: VNC password (required)
- VNC_TIMEOUT: Connection timeout in seconds (default: 30)
- VNC_RESOLUTION: Default resolution WxH (default: 1920x1080)
"""

import subprocess
import json
import os
import asyncio
import sys
from pathlib import Path

VNC_SERVER = os.environ.get("VNC_SERVER", "localhost")
VNC_PORT = int(os.environ.get("VNC_PORT", "5900"))
VNC_PASSWORD = os.environ.get("VNC_PASSWORD")
VNC_TIMEOUT = int(os.environ.get("VNC_TIMEOUT", "30"))
VNC_RESOLUTION = os.environ.get("VNC_RESOLUTION", "1920x1080")

# Add shadow-ai-vnc to path
sys.path.insert(0, '/home/steve/.openclaw/workspace/projects/shadow-ai-vnc')

def run_shadow_vnc(*args, timeout=30):
    """Run shadow-ai-vnc CLI directly."""
    cmd = ["shadow-ai-vnc", "-s", f"{VNC_SERVER}:{VNC_PORT}", "-p", VNC_PASSWORD or "", "-t", str(timeout)]
    cmd.extend(args)
    
    # Pass env vars to subprocess so shadow-ai-vnc can use them
    env = os.environ.copy()
    env["VNC_SERVER"] = VNC_SERVER
    env["VNC_PORT"] = str(VNC_PORT)
    if VNC_PASSWORD:
        env["VNC_PASSWORD"] = VNC_PASSWORD
    env["VNC_TIMEOUT"] = str(VNC_TIMEOUT)
    env["VNC_RESOLUTION"] = VNC_RESOLUTION
    
    result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10, env=env)
    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.decode() if result.stdout else None,
        "stderr": result.stderr.decode() if result.stderr else None
    }

def set_resolution(width: int, height: int) -> dict:
    """Set VNC server resolution (requires x11vnc/Xvfb)."""
    # Update systemd service environment
    try:
        # Create/update systemd drop-in
        dropin_dir = "/etc/systemd/system/vncserver.service.d"
        subprocess.run(["sudo", "mkdir", "-p", dropin_dir], capture_output=True, check=True)
        
        conf_content = f"""[Service]
Environment="VNC_RESOLUTION={width}x{height}"
"""
        subprocess.run(
            ["sudo", "tee", f"{dropin_dir}/resolution.conf"],
            input=conf_content.encode(),
            capture_output=True, check=True
        )
        
        # Reload and restart
        subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True, check=True)
        subprocess.run(["sudo", "systemctl", "restart", "vncserver.service"], capture_output=True, check=True)
        
        return {
            "success": True,
            "resolution": f"{width}x{height}",
            "message": f"VNC server restarted with {width}x{height}"
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to set resolution: {e}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def get_resolution() -> dict:
    """Get current VNC server resolution."""
    try:
        result = subprocess.run(
            ["xdpyinfo", "-display", ":1"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'dimensions:' in line:
                    parts = line.strip().split()
                    res = parts[1]  # e.g., "1920x1080"
                    return {"success": True, "resolution": res}
        return {"success": False, "error": "Could not detect resolution"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def vnc_screenshot(output_path: str, scale: float = 1.0) -> dict:
    """Capture screenshot using shadow-ai-vnc and return metadata.
    
    Args:
        output_path: Where to save the screenshot
        scale: Scale factor for upscaling (1.0=native, 2.0=2x)
               Useful for OCR on low-res VNC servers.
    """
    result = run_shadow_vnc("screenshot", output_path)
    
    if result["success"] and os.path.exists(output_path):
        try:
            from PIL import Image
            with Image.open(output_path) as img:
                orig_width, orig_height = img.size
                
                # Apply scaling if requested
                if scale != 1.0:
                    new_size = (int(orig_width * scale), int(orig_height * scale))
                    # NEAREST keeps text sharp when upscaling
                    img = img.resize(new_size, Image.NEAREST if scale >= 2.0 else Image.LANCZOS)
                    img.save(output_path)
                    width, height = new_size
                else:
                    width, height = orig_width, orig_height
            
            out = {
                "success": True,
                "path": str(Path(output_path).absolute()),
                "width": width,
                "height": height
            }
            if scale != 1.0:
                out["original_size"] = f"{orig_width}x{orig_height}"
                out["scaled_size"] = f"{width}x{height}"
                out["scale"] = scale
            return out
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    return {"success": False, "error": result.get("stderr", "Screenshot failed")}

def vnc_key(key: str) -> dict:
    """Send key press."""
    result = run_shadow_vnc("key", key)
    return {"success": result["success"], "action": f"key:{key}"}

def vnc_type(text: str) -> dict:
    """Type text."""
    result = run_shadow_vnc("type", text)
    return {"success": result["success"], "action": "type"}

def vnc_click(x: int, y: int, button: int = 1) -> dict:
    """Click at coordinates."""
    result = run_shadow_vnc("click", str(x), str(y))
    return {"success": result["success"], "action": "click", "x": x, "y": y}

def vnc_move(x: int, y: int) -> dict:
    """Move mouse (uses click without pressing a button)."""
    # shadow-ai-vnc doesn't have a separate 'move' command
    # Use click at position to move cursor there
    result = run_shadow_vnc("click", str(x), str(y))
    return {"success": result["success"], "action": "move", "x": x, "y": y, "note": "uses click for positioning"}

# Example usage if run directly
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: vnc_skill.py <command> [args...]")
        print("Commands:")
        print("  screenshot <path> [scale]     - Capture screenshot")
        print("  resolution [WxH]              - Get/set resolution")
        print("  key <key>                     - Send key press")
        print("  type <text>                   - Type text")
        print("  click <x> <y>                 - Click at coordinates")
        print("  move <x> <y>                  - Move mouse")
        print()
        print("Environment variables:")
        print("  VNC_SERVER     - VNC server IP (default: localhost)")
        print("  VNC_PORT       - VNC port (default: 5900)")
        print("  VNC_PASSWORD   - VNC password (required)")
        print("  VNC_TIMEOUT    - Connection timeout (default: 30)")
        print("  VNC_RESOLUTION - Default resolution (default: 1920x1080)")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "screenshot":
        scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
        result = vnc_screenshot(sys.argv[2] if len(sys.argv) > 2 else "/tmp/vnc_screenshot.png", scale=scale)
    elif cmd == "resolution":
        if len(sys.argv) > 2:
            parts = sys.argv[2].split('x')
            if len(parts) == 2:
                result = set_resolution(int(parts[0]), int(parts[1]))
            else:
                result = {"success": False, "error": "Invalid resolution format. Use WxH (e.g., 1920x1080)"}
        else:
            result = get_resolution()
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