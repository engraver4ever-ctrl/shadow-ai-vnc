#!/usr/bin/env python3
"""
shadow-ai-vnc - Headless VNC client for AI agents
A CLI tool to connect to VNC servers, capture screens, and send inputs.
Designed for OpenClaw and other AI agent systems.
Supports SSH tunneling and persistent sessions.
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
            
            # Connect via SSH
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
            
            # Find available local port
            if self.config.local_port == 0:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', 0))
                    self.local_port = s.getsockname()[1]
            else:
                self.local_port = self.config.local_port
            
            # Create reverse port forward: localhost:LOCAL_PORT -> remote:5900
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
    """Headless VNC controller for AI agents - uses vncdotool CLI."""
    
    def __init__(self, conn: VNCConnection, ssh_config: Optional[SSHConfig] = None):
        self.conn = conn
        self.ssh_config = ssh_config
        self._ssh_tunnel: Optional[SSHTunnel] = None
    
    def _build_vncdotool_args(self, *command) -> list:
        """Build vncdotool command args."""
        args = ["vncdotool", "-s", f"{self.conn.host}::{self.conn.port}"]
        
        if self.conn.password:
            args.extend(["-p", self.conn.password])
        
        for cmd in command:
            args.append(cmd)
        
        return args
    
    def connect(self) -> ActionResult:
        """Establish VNC connection (verify connectivity)."""
        try:
            # Start SSH tunnel if configured
            if self.ssh_config:
                self._ssh_tunnel = SSHTunnel(self.ssh_config)
                success, msg = self._ssh_tunnel.start()
                if not success:
                    return ActionResult(success=False, action="ssh_tunnel", error=msg)
            
            # Try a simple command to verify connection
            result = subprocess.run(
                self._build_vncdotool_args("capture", "/dev/null"),
                capture_output=True,
                timeout=self.conn.timeout
            )
            
            if result.returncode != 0:
                return ActionResult(
                    success=False,
                    action="connect",
                    error=result.stderr.decode() or "Connection failed"
                )
            
            return ActionResult(success=True, action="connect")
            
        except subprocess.TimeoutExpired:
            return ActionResult(success=False, action="connect", error="Connection timeout")
        except Exception as e:
            return ActionResult(success=False, action="connect", error=str(e))
    
    def disconnect(self) -> ActionResult:
        """Close VNC connection."""
        if self._ssh_tunnel:
            self._ssh_tunnel.stop()
            self._ssh_tunnel = None
        
        return ActionResult(success=True, action="disconnect")
    
    def screenshot(self, output_path: str) -> ScreenshotResult:
        """Capture screen and save to file."""
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            result = subprocess.run(
                self._build_vncdotool_args("capture", str(path)),
                capture_output=True,
                timeout=self.conn.timeout + 10
            )
            
            if result.returncode != 0:
                return ScreenshotResult(
                    success=False,
                    error=result.stderr.decode() or "Capture failed"
                )
            
            # Get dimensions
            from PIL import Image
            with Image.open(path) as img:
                width, height = img.size
            
            return ScreenshotResult(
                success=True,
                path=str(path.absolute()),
                width=width,
                height=height
            )
            
        except subprocess.TimeoutExpired:
            return ScreenshotResult(success=False, error="Screenshot timeout")
        except Exception as e:
            return ScreenshotResult(success=False, error=str(e))
    
    def send_key(self, key: str) -> ActionResult:
        """Send a key press."""
        try:
            result = subprocess.run(
                self._build_vncdotool_args("key", key),
                capture_output=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return ActionResult(success=False, action=f"key:{key}", 
                                  error=result.stderr.decode())
            
            return ActionResult(success=True, action=f"key:{key}")
        except Exception as e:
            return ActionResult(success=False, action=f"key:{key}", error=str(e))
    
    def send_text(self, text: str) -> ActionResult:
        """Type text string."""
        try:
            result = subprocess.run(
                self._build_vncdotool_args("type", text),
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return ActionResult(success=False, action="type", 
                                  error=result.stderr.decode())
            
            return ActionResult(success=True, action="type")
        except Exception as e:
            return ActionResult(success=False, action="type", error=str(e))
    
    def mouse_click(self, x: int, y: int, button: int = 1) -> ActionResult:
        """Click at coordinates (1=left, 2=middle, 3=right)."""
        try:
            # Move first, then click
            subprocess.run(
                self._build_vncdotool_args("move", str(x), str(y)),
                capture_output=True,
                timeout=10
            )
            
            button_name = {1: "left", 2: "mid", 3: "right"}[button]
            result = subprocess.run(
                self._build_vncdotool_args("click", button_name),
                capture_output=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return ActionResult(success=False, action="mouse_click", 
                                  error=result.stderr.decode())
            
            return ActionResult(success=True, action="mouse_click")
        except Exception as e:
            return ActionResult(success=False, action="mouse_click", error=str(e))
    
    def mouse_move(self, x: int, y: int) -> ActionResult:
        """Move mouse to coordinates."""
        try:
            result = subprocess.run(
                self._build_vncdotool_args("move", str(x), str(y)),
                capture_output=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return ActionResult(success=False, action="mouse_move", 
                                  error=result.stderr.decode())
            
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
    if path.exists():
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception:
            return None
    return None


def _save_session(session: VNCSession) -> None:
    """Save session to disk."""
    path = _get_session_path(session.session_id)
    with open(path, 'wb') as f:
        pickle.dump(session, f)


def _delete_session(session_id: str) -> None:
    """Delete session file."""
    path = _get_session_path(session_id)
    if path.exists():
        path.unlink()


def _build_connection(args) -> Tuple[VNCConnection, Optional[SSHConfig]]:
    """Build connection config from args."""
    vnc_conn = VNCConnection(
        host=args.host,
        port=args.port,
        password=args.password,
        timeout=args.timeout
    )
    
    ssh_config = None
    if args.ssh_host:
        ssh_config = SSHConfig(
            ssh_host=args.ssh_host,
            ssh_port=args.ssh_port or 22,
            ssh_user=args.ssh_user or "root",
            ssh_key_file=args.ssh_key,
            ssh_password=args.ssh_password,
            local_port=args.ssh_local_port or 0
        )
    
    return vnc_conn, ssh_config


def cmd_connect(args) -> int:
    """Connect to VNC server and persist session."""
    vnc_conn, ssh_config = _build_connection(args)
    
    ctl = VNCController(vnc_conn, ssh_config)
    result = ctl.connect()
    
    if result.success:
        # Create and save session
        import uuid
        session_id = str(uuid.uuid4())[:8]
        session = VNCSession(
            session_id=session_id,
            host=args.host,
            port=args.port,
            vnc_password=args.password,
            ssh_config=ssh_config
        )
        
        if ctl._ssh_tunnel:
            session.ssh_tunnel = {
                "local_port": ctl._ssh_tunnel.local_port,
                "pid": ctl._ssh_tunnel.pid
            }
        
        _save_session(session)
        
        output_json({
            "success": True,
            "session_id": session_id,
            "host": args.host,
            "port": args.port,
            "ssh_tunnel": session.ssh_tunnel is not None,
            "message": f"Connected. Use --session {session_id} for subsequent commands."
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
    vnc_conn, ssh_config = _build_connection(args)
    
    ctl = VNCController(vnc_conn, ssh_config)
    result = ctl.connect()
    
    if not result.success:
        output_json({"success": False, "error": result.error})
        return 1
    
    try:
        result = ctl.screenshot(args.output)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def cmd_key(args) -> int:
    """Send key press."""
    vnc_conn, ssh_config = _build_connection(args)
    
    ctl = VNCController(vnc_conn, ssh_config)
    result = ctl.connect()
    
    if not result.success:
        output_json({"success": False, "error": result.error})
        return 1
    
    try:
        result = ctl.send_key(args.key)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def cmd_type(args) -> int:
    """Type text."""
    vnc_conn, ssh_config = _build_connection(args)
    
    ctl = VNCController(vnc_conn, ssh_config)
    result = ctl.connect()
    
    if not result.success:
        output_json({"success": False, "error": result.error})
        return 1
    
    try:
        result = ctl.send_text(args.text)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def cmd_click(args) -> int:
    """Mouse click."""
    vnc_conn, ssh_config = _build_connection(args)
    
    ctl = VNCController(vnc_conn, ssh_config)
    result = ctl.connect()
    
    if not result.success:
        output_json({"success": False, "error": result.error})
        return 1
    
    try:
        result = ctl.mouse_click(args.x, args.y, args.button)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def cmd_move(args) -> int:
    """Mouse move."""
    vnc_conn, ssh_config = _build_connection(args)
    
    ctl = VNCController(vnc_conn, ssh_config)
    result = ctl.connect()
    
    if not result.success:
        output_json({"success": False, "error": result.error})
        return 1
    
    try:
        result = ctl.mouse_move(args.x, args.y)
        output_json(asdict(result))
        return 0 if result.success else 1
    finally:
        ctl.disconnect()


def cmd_session(args) -> int:
    """Session management commands."""
    if args.session_command == "list":
        sessions = []
        for f in _ensure_session_dir().glob("*.pkl"):
            try:
                with open(f, 'rb') as fp:
                    s = pickle.load(fp)
                    s.last_used = os.path.getatime(f)
                    sessions.append({
                        "session_id": s.session_id,
                        "host": s.host,
                        "port": s.port,
                        "has_ssh": s.ssh_config is not None,
                        "last_used": s.last_used
                    })
            except Exception:
                pass
        
        sessions.sort(key=lambda x: x["last_used"], reverse=True)
        output_json({"sessions": sessions})
        return 0
    
    elif args.session_command == "delete":
        _delete_session(args.session_id)
        output_json({"success": True, "message": f"Session {args.session_id} deleted"})
        return 0
    
    elif args.session_command == "status":
        session = _load_session(args.session_id)
        if session:
            output_json({
                "success": True,
                "session": {
                    "session_id": session.session_id,
                    "host": session.host,
                    "port": session.port,
                    "has_ssh": session.ssh_config is not None,
                    "created_at": session.created_at,
                    "last_used": session.last_used
                }
            })
            return 0
        else:
            output_json({"success": False, "error": "Session not found"})
            return 1


def main():
    parser = argparse.ArgumentParser(
        description="shadow-ai-vnc - Headless VNC client for AI agents"
    )
    
    # Global connection args
    parser.add_argument(
        "--host",
        help="VNC server hostname or IP"
    )
    parser.add_argument(
        "--port", type=int, default=5900,
        help="VNC server port (default: 5900)"
    )
    parser.add_argument(
        "--password",
        help="VNC password"
    )
    parser.add_argument(
        "--password-file",
        help="File containing VNC password"
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0,
        help="Connection timeout (default: 30s)"
    )
    parser.add_argument(
        "--session",
        help="Session ID to use (loads saved connection config)"
    )
    
    # SSH tunnel args
    ssh_group = parser.add_argument_group("SSH Tunnel Options")
    ssh_group.add_argument(
        "--ssh-host",
        help="SSH server for tunnel (e.g., user@bastion.host)"
    )
    ssh_group.add_argument(
        "--ssh-port", type=int, default=22,
        help="SSH port (default: 22)"
    )
    ssh_group.add_argument(
        "--ssh-user",
        default="root",
        help="SSH username (default: root)"
    )
    ssh_group.add_argument(
        "--ssh-key",
        help="SSH private key file"
    )
    ssh_group.add_argument(
        "--ssh-password",
        help="SSH password"
    )
    ssh_group.add_argument(
        "--ssh-local-port", type=int, default=0,
        help="Local port for tunnel (0=auto, default: auto)"
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # connect command
    connect_parser = subparsers.add_parser("connect", help="Connect and persist session")
    connect_parser.set_defaults(func=cmd_connect)
    
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
    key_parser = subparsers.add_parser("key", help="Send key press")
    key_parser.add_argument("key", help="Key to press (e.g., 'ctrl', 'Return')")
    key_parser.set_defaults(func=cmd_key)
    
    # type command
    type_parser = subparsers.add_parser("type", help="Type text string")
    type_parser.add_argument("text", help="Text to type")
    type_parser.set_defaults(func=cmd_type)
    
    # click command
    click_parser = subparsers.add_parser("click", help="Mouse click")
    click_parser.add_argument("x", type=int, help="X coordinate")
    click_parser.add_argument("y", type=int, help="Y coordinate")
    click_parser.add_argument(
        "--button", "-b", type=int, default=1,
        choices=[1, 2, 3],
        help="Mouse button: 1=left, 2=middle, 3=right"
    )
    click_parser.set_defaults(func=cmd_click)
    
    # move command
    move_parser = subparsers.add_parser("move", help="Mouse move")
    move_parser.add_argument("x", type=int, help="X coordinate")
    move_parser.add_argument("y", type=int, help="Y coordinate")
    move_parser.set_defaults(func=cmd_move)
    
    # session command
    session_parser = subparsers.add_parser(
        "session",
        help="Manage persistent sessions"
    )
    session_subparsers = session_parser.add_subparsers(
        dest="session_command",
        required=True
    )
    
    session_list = session_subparsers.add_parser(
        "list",
        help="List all sessions"
    )
    session_list.set_defaults(func=lambda a: cmd_session(a))
    
    session_delete = session_subparsers.add_parser(
        "delete",
        help="Delete a session"
    )
    session_delete.add_argument("session_id", help="Session ID to delete")
    session_delete.set_defaults(func=lambda a: cmd_session(a))
    
    session_status = session_subparsers.add_parser(
        "status",
        help="Show session status"
    )
    session_status.add_argument("session_id", help="Session ID to check")
    session_status.set_defaults(func=lambda a: cmd_session(a))
    
    args = parser.parse_args()
    
    # Handle session-based connection
    if args.session:
        session = _load_session(args.session)
        if not session:
            output_json({"success": False, "error": f"Session {args.session} not found"})
            return 1
        
        # Override args with session config
        args.host = session.host
        args.port = session.port
        args.password = session.vnc_password
        if session.ssh_config:
            args.ssh_host = session.ssh_config.ssh_host
            args.ssh_port = session.ssh_config.ssh_port
            args.ssh_user = session.ssh_config.ssh_user
            args.ssh_key = session.ssh_config.ssh_key_file
            args.ssh_password = session.ssh_config.ssh_password
            args.ssh_local_port = session.ssh_config.local_port
        
        # Update last_used
        Path(_get_session_path(args.session)).touch()
    
    # Load password from file if specified
    if args.password_file:
        args.password = Path(args.password_file).read_text().strip()
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())