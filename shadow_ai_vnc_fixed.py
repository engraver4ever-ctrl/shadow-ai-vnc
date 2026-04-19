#!/usr/bin/env python3
"""
shadow-ai-vnc - Headless VNC client for AI agents
Fixed version using direct vncdotool CLI subprocess calls.
"""

import argparse
import json
import os
import pickle
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Tuple

import paramiko

SESSION_DIR = Path(tempfile.gettempdir()) / "shadow-ai-vnc"


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


@dataclass
class VNCSession:
    """Persistent VNC session."""
    session_id: str
    host: str
    port: int
    vnc_password: Optional[str] = None
    ssh_config: Optional[SSHConfig] = None
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


def run_vncdotool(server: str, password: Optional[str], timeout: float, *args) -> Tuple[int, str, str]:
    """Run vncdotool CLI and return (returncode, stdout, stderr)."""
    cmd = ["vncdotool", "-s", server, "-t", str(timeout)]
    if password:
        cmd.extend(["-p", password])
    cmd.extend(args)
    
    result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    return result.returncode, result.stdout.decode(), result.stderr.decode()


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


def cmd_connect(args) -> int:
    """Connect to VNC server and persist session."""
    server = f"{args.host}::{args.port}"
    
    # Test connection
    returncode, stdout, stderr = run_vncdotool(server, args.password, args.timeout, "capture", "/dev/null")
    
    if returncode != 0:
        output_json({"success": False, "error": stderr or "Connection failed"})
        return 1
    
    # Create session
    import uuid
    session_id = str(uuid.uuid4())[:8]
    
    ssh_config = None
    if args.ssh_host:
        ssh_config = SSHConfig(
            ssh_host=args.ssh_host,
            ssh_port=args.ssh_port,
            ssh_user=args.ssh_user,
            ssh_key_file=args.ssh_key,
            ssh_password=args.ssh_password
        )
    
    session = VNCSession(
        session_id=session_id,
        host=args.host,
        port=args.port,
        vnc_password=args.password,
        ssh_config=ssh_config
    )
    _save_session(session)
    
    output_json({
        "success": True,
        "session_id": session_id,
        "host": args.host,
        "port": args.port,
        "message": f"Connected. Use --session {session_id} for subsequent commands."
    })
    return 0


def cmd_screenshot(args) -> int:
    """Capture screenshot."""
    server = f"{args.host}::{args.port}"
    
    returncode, stdout, stderr = run_vncdotool(server, args.password, args.timeout, "capture", args.output)
    
    if returncode != 0:
        output_json({"success": False, "error": stderr or "Screenshot failed"})
        return 1
    
    # Get dimensions
    try:
        from PIL import Image
        with Image.open(args.output) as img:
            width, height = img.size
        
        output_json({
            "success": True,
            "path": str(Path(args.output).absolute()),
            "width": width,
            "height": height
        })
        return 0
    except Exception as e:
        output_json({"success": False, "error": str(e)})
        return 1


def cmd_key(args) -> int:
    """Send key press."""
    server = f"{args.host}::{args.port}"
    
    returncode, stdout, stderr = run_vncdotool(server, args.password, args.timeout, "key", args.key)
    
    if returncode != 0:
        output_json({"success": False, "action": f"key:{args.key}", "error": stderr})
        return 1
    
    output_json({"success": True, "action": f"key:{args.key}"})
    return 0


def cmd_type(args) -> int:
    """Type text."""
    server = f"{args.host}::{args.port}"
    
    returncode, stdout, stderr = run_vncdotool(server, args.password, args.timeout, "type", args.text)
    
    if returncode != 0:
        output_json({"success": False, "action": "type", "error": stderr})
        return 1
    
    output_json({"success": True, "action": "type"})
    return 0


def cmd_click(args) -> int:
    """Mouse click."""
    server = f"{args.host}::{args.port}"
    
    # Move first
    returncode, stdout, stderr = run_vncdotool(server, args.password, args.timeout, "move", str(args.x), str(args.y))
    if returncode != 0:
        output_json({"success": False, "action": "move", "error": stderr})
        return 1
    
    # Then click
    button_map = {1: "left", 2: "mid", 3: "right"}
    button_name = button_map.get(args.button, "left")
    
    returncode, stdout, stderr = run_vncdotool(server, args.password, args.timeout, "click", button_name)
    if returncode != 0:
        output_json({"success": False, "action": "click", "error": stderr})
        return 1
    
    output_json({"success": True, "action": "click"})
    return 0


def cmd_move(args) -> int:
    """Mouse move."""
    server = f"{args.host}::{args.port}"
    
    returncode, stdout, stderr = run_vncdotool(server, args.password, args.timeout, "move", str(args.x), str(args.y))
    
    if returncode != 0:
        output_json({"success": False, "action": "move", "error": stderr})
        return 1
    
    output_json({"success": True, "action": "move"})
    return 0


def cmd_session(args) -> int:
    """Session management."""
    if args.session_command == "list":
        sessions = []
        for f in _ensure_session_dir().glob("*.pkl"):
            try:
                with open(f, 'rb') as fp:
                    s = pickle.load(fp)
                    sessions.append({
                        "session_id": s.session_id,
                        "host": s.host,
                        "port": s.port,
                        "has_ssh": s.ssh_config is not None
                    })
            except Exception:
                pass
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
                    "port": session.port
                }
            })
            return 0
        else:
            output_json({"success": False, "error": "Session not found"})
            return 1


def main():
    parser = argparse.ArgumentParser(description="shadow-ai-vnc - VNC client for AI agents")
    
    parser.add_argument("--host", help="VNC server hostname or IP")
    parser.add_argument("--port", type=int, default=5900)
    parser.add_argument("--password", default=None)
    parser.add_argument("--password-file", help="File containing VNC password")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--session", help="Session ID to use")
    
    # SSH tunnel args
    ssh_group = parser.add_argument_group("SSH Tunnel")
    ssh_group.add_argument("--ssh-host", help="SSH server for tunnel")
    ssh_group.add_argument("--ssh-port", type=int, default=22)
    ssh_group.add_argument("--ssh-user", default="root")
    ssh_group.add_argument("--ssh-key", help="SSH private key file")
    ssh_group.add_argument("--ssh-password", help="SSH password")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Commands
    subparsers.add_parser("connect", help="Connect and save session").set_defaults(func=cmd_connect)
    
    screenshot_parser = subparsers.add_parser("screenshot", help="Capture screen")
    screenshot_parser.add_argument("--output", "-o", required=True)
    screenshot_parser.set_defaults(func=cmd_screenshot)
    
    key_parser = subparsers.add_parser("key", help="Send key press")
    key_parser.add_argument("key")
    key_parser.set_defaults(func=cmd_key)
    
    type_parser = subparsers.add_parser("type", help="Type text")
    type_parser.add_argument("text")
    type_parser.set_defaults(func=cmd_type)
    
    click_parser = subparsers.add_parser("click", help="Mouse click")
    click_parser.add_argument("x", type=int)
    click_parser.add_argument("y", type=int)
    click_parser.add_argument("--button", "-b", type=int, default=1, choices=[1, 2, 3])
    click_parser.set_defaults(func=cmd_click)
    
    move_parser = subparsers.add_parser("move", help="Mouse move")
    move_parser.add_argument("x", type=int)
    move_parser.add_argument("y", type=int)
    move_parser.set_defaults(func=cmd_move)
    
    session_parser = subparsers.add_parser("session", help="Manage sessions")
    session_sub = session_parser.add_subparsers(dest="session_command", required=True)
    session_sub.add_parser("list").set_defaults(func=cmd_session)
    session_del = session_sub.add_parser("delete")
    session_del.add_argument("session_id")
    session_del.set_defaults(func=cmd_session)
    session_status = session_sub.add_parser("status")
    session_status.add_argument("session_id")
    session_status.set_defaults(func=cmd_session)
    
    args = parser.parse_args()
    
    # Load session if specified
    if args.session:
        session = _load_session(args.session)
        if not session:
            output_json({"success": False, "error": f"Session {args.session} not found"})
            return 1
        args.host = session.host
        args.port = session.port
        args.password = session.vnc_password
        Path(_get_session_path(args.session)).touch()
    
    # Load password from file
    if args.password_file:
        args.password = Path(args.password_file).read_text().strip()
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
