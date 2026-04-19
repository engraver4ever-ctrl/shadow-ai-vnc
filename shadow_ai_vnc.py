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
    error: Optional[str] = None


@dataclass
class ActionResult:
    """Action execution result."""
    success: bool
    action: str
    error: Optional[str] = None


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
            
            # Wait for connection to establish
            self._client.connect(timeout=self.conn.timeout)
            
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
    
    def screenshot(self, output_path: str) -> ScreenshotResult:
        """Capture screen and save to file."""
        if not self._client:
            return ScreenshotResult(success=False, error="Not connected")
        
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            self._client.captureScreen(str(path))
            
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


def cmd_connect(args) -> None:
    """Connect to VNC server."""
    conn = VNCConnection(
        host=args.host,
        port=args.port or 5900,
        password=args.password or os.environ.get('VNC_PASSWORD')
    )
    
    ssh_config = None
    if args.ssh:
        ssh_config = SSHConfig(
            ssh_host=args.ssh,
            ssh_user=args.ssh_user or 'root',
            ssh_key_file=args.ssh_key,
            ssh_password=args.ssh_password
        )
    
    controller = VNCController(conn, ssh_config)
    result = controller.connect()
    
    if result.success and args.session:
        session = VNCSession(
            session_id=args.session,
            host=conn.host,
            port=conn.port,
            vnc_password=conn.password,
            ssh_config=ssh_config
        )
        _save_session(session)
        output_json({"action": "connect", "success": True, "session_id": args.session})
    else:
        output_json({"action": "connect", "success": result.success, "error": result.error})


def cmd_session(args) -> None:
    """Execute command in existing session."""
    session = _load_session(args.session)
    if not session:
        output_json({"error": f"Session {args.session} not found"})
        return
    
    conn = VNCConnection(
        host=session.host,
        port=session.port,
        password=session.vnc_password
    )
    
    ssh_config = session.ssh_config
    controller = VNCController(conn, ssh_config)
    
    if args.command == 'screenshot':
        result = controller.screenshot(args.output)
        output_json({"action": "screenshot", "success": result.success, 
                    "path": result.path, "width": result.width, "height": result.height,
                    "error": result.error})
    elif args.command == 'key':
        result = controller.send_key(args.key)
        output_json({"action": f"key:{args.key}", "success": result.success, "error": result.error})
    elif args.command == 'type':
        result = controller.send_text(args.text)
        output_json({"action": "type", "success": result.success, "error": result.error})
    elif args.command == 'click':
        result = controller.mouse_click(args.x, args.y)
        output_json({"action": "mouse_click", "success": result.success, "error": result.error})
    elif args.command == 'move':
        result = controller.mouse_move(args.x, args.y)
        output_json({"action": "mouse_move", "success": result.success, "error": result.error})
    
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
    path = _get_session_path(args.session)
    if path.exists():
        path.unlink()
        output_json({"action": "delete", "success": True, "session": args.session})
    else:
        output_json({"action": "delete", "success": False, "error": "Session not found"})


def main():
    parser = argparse.ArgumentParser(description="shadow-ai-vnc: Headless VNC client for AI agents")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # connect command
    connect_parser = subparsers.add_parser('connect', help='Connect to VNC server')
    connect_parser.add_argument('-s', '--host', required=True, help='VNC server host')
    connect_parser.add_argument('-p', '--port', type=int, help='VNC port (default: 5900)')
    connect_parser.add_argument('-P', '--password', help='VNC password')
    connect_parser.add_argument('--ssh', help='SSH tunnel host')
    connect_parser.add_argument('--ssh-user', help='SSH user')
    connect_parser.add_argument('--ssh-key', help='SSH key file')
    connect_parser.add_argument('--ssh-password', help='SSH password')
    connect_parser.add_argument('--session', help='Save session with ID')
    connect_parser.set_defaults(func=cmd_connect)
    
    # session command
    session_parser = subparsers.add_parser('session', help='Run command in session')
    session_parser.add_argument('session', help='Session ID')
    session_parser.add_argument('command', choices=['screenshot', 'key', 'type', 'click', 'move'])
    session_parser.add_argument('--output', help='Screenshot output path')
    session_parser.add_argument('--key', help='Key to press')
    session_parser.add_argument('--text', help='Text to type')
    session_parser.add_argument('x', nargs='?', type=int, help='X coordinate')
    session_parser.add_argument('y', nargs='?', type=int, help='Y coordinate')
    session_parser.set_defaults(func=cmd_session)
    
    # list command
    list_parser = subparsers.add_parser('list', help='List sessions')
    list_parser.set_defaults(func=cmd_list)
    
    # delete command
    delete_parser = subparsers.add_parser('delete', help='Delete session')
    delete_parser.add_argument('session', help='Session ID')
    delete_parser.set_defaults(func=cmd_delete)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Set defaults from environment
    if hasattr(args, 'password') and not args.password:
        args.password = os.environ.get('VNC_PASSWORD')
    
    args.func(args)


if __name__ == '__main__':
    main()