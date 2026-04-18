#!/usr/bin/env python3
"""
vncctl - Headless VNC client for AI agents
A CLI tool to connect to VNC servers, capture screens, and send inputs.
Designed for OpenClaw and other AI agent systems.
"""

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from vncdotool import api, client


@dataclass
class VNCConnection:
    """Connection configuration."""
    host: str
    port: int = 5900
    password: Optional[str] = None
    timeout: float = 30.0


@dataclass
class ScreenshotResult:
    """Screenshot capture result."""
    success: bool
    path: Optional[str] = None
    width: int = 0
    height: int = 0
    error: Optional[str] = None


@dataclass
class ActionResult:
    """Action execution result."""
    success: bool
    action: str
    error: Optional[str] = None


class VNCController:
    """Headless VNC controller for AI agents."""
    
    def __init__(self, conn: VNCConnection):
        self.conn = conn
        self._client: Optional[client.VNCDoToolClient] = None
    
    def connect(self) -> ActionResult:
        """Establish VNC connection."""
        try:
            self._client = api.connect(
                self.conn.host,
                self.conn.port,
                password=self.conn.password,
                timeout=self.conn.timeout
            )
            return ActionResult(success=True, action="connect")
        except Exception as e:
            return ActionResult(success=False, action="connect", error=str(e))
    
    def disconnect(self) -> ActionResult:
        """Close VNC connection."""
        if self._client:
            try:
                self._client.disconnect()
                self._client = None
                return ActionResult(success=True, action="disconnect")
            except Exception as e:
                return ActionResult(success=False, action="disconnect", error=str(e))
        return ActionResult(success=True, action="disconnect")
    
    def screenshot(self, output_path: str) -> ScreenshotResult:
        """Capture screen and save to file."""
        if not self._client:
            return ScreenshotResult(
                success=False,
                error="Not connected to VNC server"
            )
        
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            self._client.captureScreen(str(path))
            
            # Get dimensions from the saved image
            from PIL import Image
            with Image.open(path) as img:
                width, height = img.size
            
            return ScreenshotResult(
                success=True,
                path=str(path.absolute()),
                width=width,
                height=height
            )
        except Exception as e:
            return ScreenshotResult(success=False, error=str(e))
    
    def send_key(self, key: str) -> ActionResult:
        """Send a key press."""
        if not self._client:
            return ActionResult(success=False, action=f"key:{key}", 
                              error="Not connected")
        
        try:
            self._client.keyPress(key)
            return ActionResult(success=True, action=f"key:{key}")
        except Exception as e:
            return ActionResult(success=False, action=f"key:{key}", error=str(e))
    
    def send_text(self, text: str) -> ActionResult:
        """Type text string."""
        if not self._client:
            return ActionResult(success=False, action="type", 
                              error="Not connected")
        
        try:
            self._client.type(text)
            return ActionResult(success=True, action="type")
        except Exception as e:
            return ActionResult(success=False, action="type", error=str(e))
    
    def mouse_click(self, x: int, y: int, button: int = 1) -> ActionResult:
        """Click at coordinates (1=left, 2=middle, 3=right)."""
        if not self._client:
            return ActionResult(success=False, action="mouse_click", 
                              error="Not connected")
        
        try:
            self._client.mouseMove(x, y)
            self._client.mouseDown(button)
            time.sleep(0.05)
            self._client.mouseUp(button)
            return ActionResult(success=True, action="mouse_click")
        except Exception as e:
            return ActionResult(success=False, action="mouse_click", error=str(e))
    
    def mouse_move(self, x: int, y: int) -> ActionResult:
        """Move mouse to coordinates."""
        if not self._client:
            return ActionResult(success=False, action="mouse_move", 
                              error="Not connected")
        
        try:
            self._client.mouseMove(x, y)
            return ActionResult(success=True, action="mouse_move")
        except Exception as e:
            return ActionResult(success=False, action="mouse_move", error=str(e))


def output_json(data: dict) -> None:
    """Output JSON result."""
    print(json.dumps(data, indent=2))


def cmd_connect(args) -> int:
    """Connect to VNC server."""
    conn = VNCConnection(
        host=args.host,
        port=args.port,
        password=args.password
    )
    
    ctl = VNCController(conn)
    result = ctl.connect()
    
    if result.success:
        # Keep connection alive for subsequent commands
        # In practice, you'd use a session file or daemon
        output_json({
            "success": True,
            "host": args.host,
            "port": args.port,
            "message": "Connected successfully"
        })
        return 0
    else:
        output_json({
            "success": False,
            "error": result.error
        })
        return 1


def cmd_screenshot(args) -> int:
    """Capture screenshot."""
    conn = VNCConnection(
        host=args.host,
        port=args.port,
        password=args.password
    )
    
    ctl = VNCController(conn)
    
    connect_result = ctl.connect()
    if not connect_result.success:
        output_json({
            "success": False,
            "error": connect_result.error
        })
        return 1
    
    try:
        result = ctl.screenshot(args.output)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def cmd_key(args) -> int:
    """Send key press."""
    conn = VNCConnection(
        host=args.host,
        port=args.port,
        password=args.password
    )
    
    ctl = VNCController(conn)
    
    connect_result = ctl.connect()
    if not connect_result.success:
        output_json({
            "success": False,
            "error": connect_result.error
        })
        return 1
    
    try:
        result = ctl.send_key(args.key)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def cmd_type(args) -> int:
    """Type text."""
    conn = VNCConnection(
        host=args.host,
        port=args.port,
        password=args.password
    )
    
    ctl = VNCController(conn)
    
    connect_result = ctl.connect()
    if not connect_result.success:
        output_json({
            "success": False,
            "error": connect_result.error
        })
        return 1
    
    try:
        result = ctl.send_text(args.text)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def cmd_click(args) -> int:
    """Mouse click."""
    conn = VNCConnection(
        host=args.host,
        port=args.port,
        password=args.password
    )
    
    ctl = VNCController(conn)
    
    connect_result = ctl.connect()
    if not connect_result.success:
        output_json({
            "success": False,
            "error": connect_result.error
        })
        return 1
    
    try:
        result = ctl.mouse_click(args.x, args.y, args.button)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description="vncctl - Headless VNC client for AI agents"
    )
    parser.add_argument(
        "--host", required=True,
        help="VNC server hostname or IP"
    )
    parser.add_argument(
        "--port", type=int, default=5900,
        help="VNC server port (default: 5900)"
    )
    parser.add_argument(
        "--password", default=None,
        help="VNC password"
    )
    parser.add_argument(
        "--password-file",
        help="File containing VNC password"
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # screenshot command
    screenshot_parser = subparsers.add_parser(
        "screenshot",
        help="Capture screen and save to file"
    )
    screenshot_parser.add_argument(
        "--output", "-o", required=True,
        help="Output file path (PNG)"
    )
    screenshot_parser.set_defaults(func=cmd_screenshot)
    
    # key command
    key_parser = subparsers.add_parser(
        "key",
        help="Send key press"
    )
    key_parser.add_argument(
        "key",
        help="Key to press (e.g., 'ctrl', 'alt', 'f1', 'Return')"
    )
    key_parser.set_defaults(func=cmd_key)
    
    # type command
    type_parser = subparsers.add_parser(
        "type",
        help="Type text string"
    )
    type_parser.add_argument(
        "text",
        help="Text to type"
    )
    type_parser.set_defaults(func=cmd_type)
    
    # click command
    click_parser = subparsers.add_parser(
        "click",
        help="Mouse click at coordinates"
    )
    click_parser.add_argument("x", type=int, help="X coordinate")
    click_parser.add_argument("y", type=int, help="Y coordinate")
    click_parser.add_argument(
        "--button", "-b", type=int, default=1,
        choices=[1, 2, 3],
        help="Mouse button: 1=left, 2=middle, 3=right"
    )
    click_parser.set_defaults(func=cmd_click)
    
    args = parser.parse_args()
    
    # Load password from file if specified
    if args.password_file:
        args.password = Path(args.password_file).read_text().strip()
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
