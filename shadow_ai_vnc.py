#!/usr/bin/env python3
"""
shadow-ai-vnc - Headless VNC client for AI agents
A CLI tool to connect to VNC servers, capture screens, and send inputs.
Designed for OpenClaw and other AI agent systems.
Supports SSH tunneling and persistent sessions.

Uses vncdotool Python API (not CLI) for better compatibility.
"""

import argparse
import json
import os
import pickle
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Tuple

import paramiko
from vncdotool import api


SESSION_DIR = Path(tempfile.gettempdir()) / "shadow-ai-vnc"
SESSION_FILE = "session.pkl"


@dataclass
class VNCConnection:
    """Connection configuration."""
    host: str
    port: int = 5900
    password: Optional[str] = None
    timeout: float = 30.0


@dataclass
class SSHConfig:
    """SSH tunnel configuration."""
    ssh_host: str
    ssh_port: int = 22
    ssh_user: str = "root"
    ssh_key_file: Optional[str] = None
    ssh_password: Optional[str] = None
    local_port: int = 0  # 0 = auto-select


@dataclass
class VNCSession:
    """Persistent VNC session."""
    session_id: str
    host: str
    port: int
    vnc_password: Optional[str] = None
    ssh_config: Optional[SSHConfig] = None
    ssh_tunnel: Optional[dict] = None  # {"local_port": int, "pid": int}
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


@dataclass
class ScreenshotResult:
    """Screenshot capture result."""
    success: bool
    path: Optional[str] = None
    width: int = 0
    height: int = 0
    original_width: Optional[int] = None
    original_height: Optional[int] = None
    scale: float = 1.0
    error: Optional[str] = None


@dataclass
class ActionResult:
    """Action execution result."""
    success: bool
    action: str
    error: Optional[str] = None


class SSHClient:
    """SSH client for tunneling and remote commands."""
    
    def __init__(self, config: SSHConfig):
        self.config = config
        self._client: Optional[paramiko.SSHClient] = None
    
    def connect(self) -> Tuple[bool, str]:
        """Connect to SSH server."""
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                'hostname': self.config.ssh_host,
                'port': self.config.ssh_port,
                'username': self.config.ssh_user,
                'timeout': 30,
            }
            
            if self.config.ssh_key_file:
                connect_kwargs['key_filename'] = self.config.ssh_key_file
            elif self.config.ssh_password:
                connect_kwargs['password'] = self.config.ssh_password
            
            self._client.connect(**connect_kwargs)
            return True, f"SSH connected to {self.config.ssh_host}"
        except Exception as e:
            return False, f"SSH connection failed: {str(e)}"
    
    def execute(self, command: str) -> Tuple[bool, str, str]:
        """Execute command on remote host. Returns (success, stdout, stderr)."""
        if not self._client:
            return False, "", "Not connected"
        try:
            stdin, stdout, stderr = self._client.exec_command(command, timeout=30)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            exit_code = stdout.channel.recv_exit_status()
            return exit_code == 0, out, err
        except Exception as e:
            return False, "", str(e)
    
    def disconnect(self) -> None:
        """Disconnect SSH."""
        if self._client:
            self._client.close()
            self._client = None


class SSHTunnel:
    """Manages SSH tunnels for VNC connections."""
    
    def __init__(self, config: SSHConfig):
        self.config = config
        self.local_port: Optional[int] = None
        self.pid: Optional[int] = None
        self._client: Optional[paramiko.SSHClient] = None
    
    def start(self) -> Tuple[bool, str]:
        """Start SSH tunnel and return (success, message)."""
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                'hostname': self.config.ssh_host,
                'port': self.config.ssh_port,
                'username': self.config.ssh_user,
                'timeout': 30,
            }
            
            if self.config.ssh_key_file:
                connect_kwargs['key_filename'] = self.config.ssh_key_file
            elif self.config.ssh_password:
                connect_kwargs['password'] = self.config.ssh_password
            
            self._client.connect(**connect_kwargs)
            
            if self.config.local_port == 0:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', 0))
                    self.local_port = s.getsockname()[1]
            else:
                self.local_port = self.config.local_port
            
            transport = self._client.get_transport()
            transport.request_port_forward('', self.local_port)
            
            self.pid = os.getpid()
            
            return True, f"SSH tunnel established on local port {self.local_port}"
            
        except Exception as e:
            return False, f"SSH tunnel failed: {str(e)}"
    
    def stop(self) -> None:
        """Stop SSH tunnel."""
        if self._client:
            try:
                transport = self._client.get_transport()
                if transport:
                    transport.cancel_port_forward('', self.local_port)
                self._client.close()
            except Exception:
                pass
            self._client = None


class VNCController:
    """Headless VNC controller for AI agents - uses vncdotool Python API."""
    
    def __init__(self, conn: VNCConnection, ssh_config: Optional[SSHConfig] = None):
        self.conn = conn
        self.ssh_config = ssh_config
        self._ssh_tunnel: Optional[SSHTunnel] = None
        self._client = None
    
    def connect(self) -> ActionResult:
        """Establish VNC connection using Python API."""
        try:
            if self.ssh_config:
                self._ssh_tunnel = SSHTunnel(self.ssh_config)
                success, msg = self._ssh_tunnel.start()
                if not success:
                    return ActionResult(success=False, action="ssh_tunnel", error=msg)
            
            # Use Python API instead of CLI
            server = f"{self.conn.host}::{self.conn.port}"
            self._client = api.connect(server, password=self.conn.password)
            
            # api.connect() already establishes the connection
            # No need to call proxy.connect() again
            pass
            
            return ActionResult(success=True, action="connect")
            
        except Exception as e:
            return ActionResult(success=False, action="connect", error=str(e))
    
    def disconnect(self) -> ActionResult:
        """Close VNC connection."""
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
        
        if self._ssh_tunnel:
            self._ssh_tunnel.stop()
            self._ssh_tunnel = None
        
        return ActionResult(success=True, action="disconnect")
    
    def screenshot(self, output_path: str, scale: float = 1.0, format: str = None) -> ScreenshotResult:
        """Capture screen and save to file.
        
        Args:
            output_path: Where to save the screenshot
            scale: Scale factor for upscaling (1.0 = no scaling, 2.0 = 2x)
            format: Output format (png, jpeg, etc). None = auto from extension
        """
        if not self._client:
            return ScreenshotResult(success=False, error="Not connected")
        
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            self._client.captureScreen(str(path))
            
            from PIL import Image
            with Image.open(path) as img:
                orig_width, orig_height = img.size
                
                # Apply scaling if requested
                if scale != 1.0:
                    new_size = (int(orig_width * scale), int(orig_height * scale))
                    # Use LANCZOS for best quality, or NEAREST for pixel-perfect (text)
                    if scale >= 2.0:
                        # For large upscaling, NEAREST keeps text sharp
                        img = img.resize(new_size, Image.NEAREST)
                    else:
                        img = img.resize(new_size, Image.LANCZOS)
                    img.save(str(path), format=format)
                    width, height = new_size
                else:
                    width, height = orig_width, orig_height
            
            return ScreenshotResult(
                success=True,
                path=str(path.absolute()),
                width=width,
                height=height,
                original_width=orig_width if scale != 1.0 else None,
                original_height=orig_height if scale != 1.0 else None
            )
            
        except Exception as e:
            return ScreenshotResult(success=False, error=str(e))
    
    def send_key(self, key: str) -> ActionResult:
        """Send a key press."""
        if not self._client:
            return ActionResult(success=False, action=f"key:{key}", error="Not connected")
        
        try:
            self._client.keyPress(key)
            return ActionResult(success=True, action=f"key:{key}")
        except Exception as e:
            return ActionResult(success=False, action=f"key:{key}", error=str(e))
    
    def send_text(self, text: str) -> ActionResult:
        """Type text string."""
        if not self._client:
            return ActionResult(success=False, action="type", error="Not connected")
        
        try:
            self._client.typeText(text)
            return ActionResult(success=True, action="type")
        except Exception as e:
            return ActionResult(success=False, action="type", error=str(e))
    
    def mouse_click(self, x: int, y: int, button: int = 1) -> ActionResult:
        """Click at coordinates (1=left, 2=middle, 3=right)."""
        if not self._client:
            return ActionResult(success=False, action="mouse_click", error="Not connected")
        
        try:
            self._client.mouseMove(x, y)
            # Map button: 1=left, 2=middle, 3=right
            self._client.mousePress(button)
            return ActionResult(success=True, action="mouse_click")
        except Exception as e:
            return ActionResult(success=False, action="mouse_click", error=str(e))
    
    def set_resolution(self, width: int, height: int, depth: int = 24) -> ActionResult:
        """Set VNC server resolution via SSH (Linux/X11 only).
        
        This uses xrandr to change the X11 display resolution.
        Requires SSH access to the VNC server host.
        
        Args:
            width: Screen width
            height: Screen height  
            depth: Color depth (default 24)
        
        Returns:
            ActionResult with success/error info
        """
        if not self._client:
            return ActionResult(success=False, action="set_resolution", 
                              error="VNC not connected. Connect first.")
        
        try:
            # Get screen info first
            screen_info = self._client.screen.size if hasattr(self._client, 'screen') and self._client.screen else (0, 0)
            current_w, current_h = screen_info
            
            result = {
                "action": "set_resolution",
                "requested": {"width": width, "height": height, "depth": depth},
                "previous": {"width": current_w, "height": current_h},
                "success": False,
                "message": ""
            }
            
            # If we have SSH config, try to use xrandr
            if self.ssh_config:
                ssh = SSHClient(self.ssh_config)
                success, msg = ssh.connect()
                if not success:
                    result["message"] = f"SSH connection failed: {msg}"
                    return ActionResult(success=False, action="set_resolution", 
                                      error=result["message"])
                
                # Try xrandr first
                success, out, err = ssh.execute("which xrandr")
                if success:
                    # Find the display
                    success, out, err = ssh.execute("echo $DISPLAY")
                    display = out.strip() or ":1"
                    
                    # Try to set resolution with xrandr
                    cmd = f"DISPLAY={display} xrandr --output $(DISPLAY={display} xrandr | grep ' connected' | head -1 | awk '{{print $1}}') --mode {width}x{height}"
                    success, out, err = ssh.execute(cmd)
                    
                    if success:
                        result["success"] = True
                        result["message"] = f"Resolution set to {width}x{height} via xrandr"
                    else:
                        # Try adding mode if it doesn't exist
                        cmd = f"DISPLAY={display} xrandr --newmode \"{width}x{height}\" $(DISPLAY={display} cvt {width} {height} | grep Modeline | sed 's/.*Modeline \"[^\"]*\" //')"
                        ssh.execute(cmd)
                        
                        output_name = f"$(DISPLAY={display} xrandr | grep ' connected' | head -1 | awk '{{print $1}}')"
                        cmd = f"DISPLAY={display} xrandr --addmode {output_name} \"{width}x{height}\""
                        success, out, err = ssh.execute(cmd)
                        
                        cmd = f"DISPLAY={display} xrandr --output {output_name} --mode \"{width}x{height}\""
                        success, out, err = ssh.execute(cmd)
                        
                        if success:
                            result["success"] = True
                            result["message"] = f"Resolution set to {width}x{height} via xrandr (new mode)"
                        else:
                            result["message"] = f"xrandr failed: {err}. Trying Xvfb restart..."
                
                # Fallback: Try to restart Xvfb with new resolution
                if not result["success"]:
                    # Find and kill Xvfb
                    ssh.execute("pkill -f 'Xvfb.*:1'")
                    time.sleep(1)
                    
                    # Start Xvfb with new resolution
                    cmd = f"Xvfb :1 -screen 0 {width}x{height}x{depth} -nolisten tcp &"
                    success, out, err = ssh.execute(cmd)
                    
                    if success:
                        result["success"] = True
                        result["message"] = f"Xvfb restarted with {width}x{height}x{depth}"
                        result["method"] = "xvfb_restart"
                    else:
                        result["message"] = f"Failed to set resolution: {err}"
                
                ssh.disconnect()
            else:
                # No SSH config - try to use x11vnc scale option if available
                result["message"] = "No SSH config available. Cannot change server resolution. Use --scale option for screenshot upscaling."
            
            return ActionResult(
                success=result["success"], 
                action="set_resolution",
                error=None if result["success"] else result["message"]
            )
            
        except Exception as e:
            return ActionResult(success=False, action="set_resolution", error=str(e))

    def mouse_move(self, x: int, y: int) -> ActionResult:
        """Move mouse to coordinates."""
        if not self._client:
            return ActionResult(success=False, action="mouse_move", error="Not connected")
        
        try:
            self._client.mouseMove(x, y)
            return ActionResult(success=True, action="mouse_move")
        except Exception as e:
            return ActionResult(success=False, action="mouse_move", error=str(e))


def output_json(data: dict) -> None:
    """Output JSON result."""
    print(json.dumps(data, indent=2))


def _ensure_session_dir() -> Path:
    """Ensure session directory exists."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR


def _get_session_path(session_id: str) -> Path:
    """Get path for session file."""
    return _ensure_session_dir() / f"{session_id}.pkl"


def _load_session(session_id: str) -> Optional[VNCSession]:
    """Load session from disk."""
    path = _get_session_path(session_id)
    if not path.exists():
        return None
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except Exception:
        return None


def _save_session(session: VNCSession) -> None:
    """Save session to disk."""
    path = _get_session_path(session.session_id)
    with open(path, 'wb') as f:
        pickle.dump(session, f)


# ── Connection helpers ──────────────────────────────────────────────────

def _build_connection(args) -> Tuple[VNCConnection, Optional[SSHConfig]]:
    """Build VNCConnection and optional SSHConfig from parsed args."""
    password = args.password or os.environ.get('VNC_PASSWORD')
    conn = VNCConnection(
        host=args.host,
        port=args.port or 5900,
        password=password
    )
    
    ssh_config = None
    if getattr(args, 'ssh_host', None):
        ssh_config = SSHConfig(
            ssh_host=args.ssh_host,
            ssh_port=getattr(args, 'ssh_port', 22) or 22,
            ssh_user=getattr(args, 'ssh_user', 'root') or 'root',
            ssh_key_file=getattr(args, 'ssh_key', None),
            ssh_password=getattr(args, 'ssh_password', None)
        )
    
    return conn, ssh_config


def _connect_and_execute(args, action_fn):
    """Connect to VNC, execute action, disconnect, return result dict."""
    conn, ssh_config = _build_connection(args)
    controller = VNCController(conn, ssh_config)
    connect_result = controller.connect()
    
    if not connect_result.success:
        return {"success": False, "error": f"Connection failed: {connect_result.error}"}
    
    try:
        result = action_fn(controller)
    except Exception as e:
        return {"success": False, "error": f"Action failed: {str(e)}"}
    finally:
        controller.disconnect()
    
    return result


# ── Command handlers ────────────────────────────────────────────────────

def cmd_screenshot(args) -> None:
    """Take a screenshot."""
    def action(ctrl):
        result = ctrl.screenshot(args.output, scale=getattr(args, 'scale', 1.0) or 1.0,
                                 format=getattr(args, 'format', None))
        out = {"success": result.success, "path": result.path,
               "width": result.width, "height": result.height}
        if result.original_width:
            out["original_size"] = f"{result.original_width}x{result.original_height}"
            out["scaled_size"] = f"{result.width}x{result.height}"
            out["scale"] = getattr(args, 'scale', 1.0) or 1.0
        if result.error:
            out["error"] = result.error
        return out
    
    output_json(_connect_and_execute(args, action))


def cmd_key(args) -> None:
    """Send a key press."""
    def action(ctrl):
        result = ctrl.send_key(args.key)
        return {"success": result.success, "action": f"key:{args.key}",
                "error": result.error}
    output_json(_connect_and_execute(args, action))


def cmd_type(args) -> None:
    """Type text."""
    def action(ctrl):
        result = ctrl.send_text(args.text)
        return {"success": result.success, "action": "type", "error": result.error}
    output_json(_connect_and_execute(args, action))


def cmd_click(args) -> None:
    """Click at coordinates."""
    def action(ctrl):
        result = ctrl.mouse_click(args.x, args.y, button=args.button)
        return {"success": result.success, "action": "click",
                "x": args.x, "y": args.y, "button": args.button,
                "error": result.error}
    output_json(_connect_and_execute(args, action))


def cmd_move(args) -> None:
    """Move mouse to coordinates."""
    def action(ctrl):
        result = ctrl.mouse_move(args.x, args.y)
        return {"success": result.success, "action": "move",
                "x": args.x, "y": args.y, "error": result.error}
    output_json(_connect_and_execute(args, action))


def cmd_set_resolution(args) -> None:
    """Set VNC server resolution (requires SSH)."""
    def action(ctrl):
        result = ctrl.set_resolution(args.width, args.height, getattr(args, 'depth', 24) or 24)
        return {"success": result.success, "action": "set_resolution",
                "width": args.width, "height": args.height,
                "error": result.error}
    output_json(_connect_and_execute(args, action))


def cmd_connect(args) -> None:
    """Connect to VNC server and save session."""
    conn, ssh_config = _build_connection(args)
    controller = VNCController(conn, ssh_config)
    result = controller.connect()
    
    session_id = getattr(args, 'session', None) or os.environ.get('VNC_SESSION', None)
    
    if result.success and session_id:
        session = VNCSession(
            session_id=session_id,
            host=conn.host,
            port=conn.port,
            vnc_password=conn.password,
            ssh_config=ssh_config
        )
        _save_session(session)
        output_json({"action": "connect", "success": True, "session_id": session_id})
    elif result.success:
        output_json({"action": "connect", "success": True})
    else:
        output_json({"action": "connect", "success": False, "error": result.error})
    
    # Keep connection alive for sessions
    if result.success and session_id:
        return  # Don't disconnect — session is persistent
    controller.disconnect()


def cmd_session(args) -> None:
    """Execute command in existing session."""
    session = _load_session(args.session_id)
    if not session:
        output_json({"error": f"Session {args.session_id} not found"})
        return
    
    conn = VNCConnection(host=session.host, port=session.port, password=session.vnc_password)
    controller = VNCController(conn, session.ssh_config)
    
    subcmd = args.session_command
    if subcmd == 'screenshot':
        result = controller.screenshot(args.output, scale=getattr(args, 'scale', 1.0) or 1.0)
        out = {"success": result.success, "path": result.path,
               "width": result.width, "height": result.height}
        if result.original_width:
            out["original_size"] = f"{result.original_width}x{result.original_height}"
            out["scaled_size"] = f"{result.width}x{result.height}"
        if result.error:
            out["error"] = result.error
        output_json(out)
    elif subcmd == 'key':
        result = controller.send_key(args.key)
        output_json({"success": result.success, "action": f"key:{args.key}", "error": result.error})
    elif subcmd == 'type':
        result = controller.send_text(args.text)
        output_json({"success": result.success, "action": "type", "error": result.error})
    elif subcmd == 'click':
        result = controller.mouse_click(args.x, args.y)
        output_json({"success": result.success, "action": "click", "x": args.x, "y": args.y})
    elif subcmd == 'move':
        result = controller.mouse_move(args.x, args.y)
        output_json({"success": result.success, "action": "move", "x": args.x, "y": args.y})
    elif subcmd == 'set-resolution':
        result = controller.set_resolution(args.width, args.height)
        output_json({"success": result.success, "action": "set_resolution",
                    "width": args.width, "height": args.height, "error": result.error})
    else:
        output_json({"error": f"Unknown session command: {subcmd}"})
    
    controller.disconnect()


def cmd_list(args) -> None:
    """List active sessions."""
    _ensure_session_dir()
    sessions = []
    for path in SESSION_DIR.glob("*.pkl"):
        session = _load_session(path.stem)
        if session:
            sessions.append({
                "session_id": session.session_id,
                "host": session.host,
                "port": session.port,
                "created_at": session.created_at,
                "last_used": session.last_used
            })
    output_json({"sessions": sessions})


def cmd_delete(args) -> None:
    """Delete a session."""
    path = _get_session_path(args.session_id)
    if path.exists():
        path.unlink()
        output_json({"action": "delete", "success": True, "session": args.session_id})
    else:
        output_json({"action": "delete", "success": False, "error": "Session not found"})


# ── CLI argument definitions ────────────────────────────────────────────

def _add_connection_args(p):
    """Add common connection args to a subparser."""
    p.add_argument('-s', '--host', default=os.environ.get('VNC_SERVER', 'localhost'),
                   help='VNC server host (env: VNC_SERVER)')
    p.add_argument('-p', '--port', type=int, default=int(os.environ.get('VNC_PORT', '5900')),
                   help='VNC port (default: 5900, env: VNC_PORT)')
    p.add_argument('-P', '--password', default=os.environ.get('VNC_PASSWORD'),
                   help='VNC password (env: VNC_PASSWORD)')
    p.add_argument('--ssh-host', help='SSH tunnel host')
    p.add_argument('--ssh-port', type=int, default=22, help='SSH port (default: 22)')
    p.add_argument('--ssh-user', default='root', help='SSH user (default: root)')
    p.add_argument('--ssh-key', help='SSH key file')
    p.add_argument('--ssh-password', help='SSH password')


def main():
    parser = argparse.ArgumentParser(
        description="shadow-ai-vnc: Headless VNC client for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Screenshot at native resolution
  shadow-ai-vnc screenshot -s 192.168.1.100 -o /tmp/screen.png

  # Screenshot with 2x upscale (good for OCR on low-res VNC)
  shadow-ai-vnc screenshot -s 192.168.1.100 -o /tmp/screen.png --scale 2

  # Send key
  shadow-ai-vnc key -s 192.168.1.100 Return

  # Type text
  shadow-ai-vnc type -s 192.168.1.100 "Hello, World!"

  # Click
  shadow-ai-vnc click -s 192.168.1.100 500 300

  # Right click
  shadow-ai-vnc click -s 192.168.1.100 500 300 --button 3

  # Set resolution via SSH
  shadow-ai-vnc set-resolution -s localhost --ssh-host 192.168.1.100 1920 1080

  # Session: connect, then reuse
  shadow-ai-vnc connect -s 192.168.1.100 --session mysession
  shadow-ai-vnc session mysession screenshot -o /tmp/screen.png
"""
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # ── screenshot ──
    p = subparsers.add_parser('screenshot', help='Capture screenshot')
    _add_connection_args(p)
    p.add_argument('-o', '--output', required=True, help='Output file path')
    p.add_argument('--scale', type=float, default=1.0,
                   help='Scale factor for upscaling (1.0=native, 2.0=2x). '
                        'Use 2+ for better OCR on low-res VNC servers.')
    p.add_argument('--format', choices=['png', 'jpeg', 'bmp', 'tiff'],
                   help='Output image format (default: auto from extension)')
    p.set_defaults(func=cmd_screenshot)
    
    # ── key ──
    p = subparsers.add_parser('key', help='Send key press')
    _add_connection_args(p)
    p.add_argument('key', help='Key to press (e.g. Return, Escape, ctrl-c, alt-f4)')
    p.set_defaults(func=cmd_key)
    
    # ── type ──
    p = subparsers.add_parser('type', help='Type text string')
    _add_connection_args(p)
    p.add_argument('text', help='Text to type')
    p.set_defaults(func=cmd_type)
    
    # ── click ──
    p = subparsers.add_parser('click', help='Click at coordinates')
    _add_connection_args(p)
    p.add_argument('x', type=int, help='X coordinate')
    p.add_argument('y', type=int, help='Y coordinate')
    p.add_argument('--button', type=int, default=1, help='Mouse button (1=left, 2=mid, 3=right)')
    p.set_defaults(func=cmd_click)
    
    # ── move ──
    p = subparsers.add_parser('move', help='Move mouse to coordinates')
    _add_connection_args(p)
    p.add_argument('x', type=int, help='X coordinate')
    p.add_argument('y', type=int, help='Y coordinate')
    p.set_defaults(func=cmd_move)
    
    # ── set-resolution ──
    p = subparsers.add_parser('set-resolution', help='Set VNC server resolution (requires SSH)')
    _add_connection_args(p)
    p.add_argument('width', type=int, help='Screen width')
    p.add_argument('height', type=int, help='Screen height')
    p.add_argument('--depth', type=int, default=24, help='Color depth (default: 24)')
    p.set_defaults(func=cmd_set_resolution)
    
    # ── connect ──
    p = subparsers.add_parser('connect', help='Connect and save session')
    _add_connection_args(p)
    p.add_argument('--session', help='Session ID to save')
    p.set_defaults(func=cmd_connect)
    
    # ── session ──
    p = subparsers.add_parser('session', help='Run command in saved session')
    p.add_argument('session_id', help='Session ID')
    p.add_argument('session_command',
                   choices=['screenshot', 'key', 'type', 'click', 'move', 'set-resolution'],
                   help='Command to run')
    p.add_argument('-o', '--output', help='Screenshot output path')
    p.add_argument('--key', help='Key to press')
    p.add_argument('--text', help='Text to type')
    p.add_argument('--x', type=int, help='X coordinate')
    p.add_argument('--y', type=int, help='Y coordinate')
    p.add_argument('--scale', type=float, default=1.0, help='Screenshot scale factor')
    p.add_argument('--width', type=int, help='Resolution width (for set-resolution)')
    p.add_argument('--height', type=int, help='Resolution height (for set-resolution)')
    p.set_defaults(func=cmd_session)
    
    # ── list ──
    p = subparsers.add_parser('list', help='List saved sessions')
    p.set_defaults(func=cmd_list)
    
    # ── delete ──
    p = subparsers.add_parser('delete', help='Delete saved session')
    p.add_argument('session_id', help='Session ID')
    p.set_defaults(func=cmd_delete)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()