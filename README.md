# shadow-ai-vnc

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

Headless VNC client designed for AI agents and automation. Provides a clean CLI interface for connecting to VNC servers, capturing screenshots, and sending input commands — with SSH tunneling and session persistence.

**Built for [OpenClaw](https://github.com/openclaw/openclaw)** — includes a ready-to-use skill wrapper.

## Installation

```bash
cd shadow-ai-vnc
pip install -e .
# or
pip install -r requirements.txt
```

## Usage

All commands output JSON for easy parsing by AI agents.

### Basic Commands

```bash
# Screenshot
shadow-ai-vnc --host 192.168.1.100 screenshot --output /tmp/screen.png

# Send key
shadow-ai-vnc --host 192.168.1.100 key Return
shadow-ai-vnc --host 192.168.1.100 key ctrl-alt-t

# Type text
shadow-ai-vnc --host 192.168.1.100 type "Hello, World!"

# Mouse click
shadow-ai-vnc --host 192.168.1.100 click 500 300
shadow-ai-vnc --host 192.168.1.100 click 500 300 --button 3  # right click

# Mouse move
shadow-ai-vnc --host 192.168.1.100 move 100 200
```

### Session Persistence

```bash
# Connect and save session (returns session ID)
shadow-ai-vnc --host 192.168.1.100 connect
# Output: {"session_id": "abc123", ...}

# Reuse session for subsequent commands
shadow-ai-vnc --session abc123 screenshot --output /tmp/screen.png
shadow-ai-vnc --session abc123 click 500 300

# List sessions
shadow-ai-vnc session list

# Check session status
shadow-ai-vnc session status abc123

# Delete session
shadow-ai-vnc session delete abc123
```

### SSH Tunneling

Connect through an SSH bastion host:

```bash
# SSH with key auth
shadow-ai-vnc \
  --host localhost \
  --port 5901 \
  --ssh-host bastion.example.com \
  --ssh-user ubuntu \
  --ssh-key ~/.ssh/id_rsa \
  screenshot --output /tmp/screen.png

# SSH with password auth
shadow-ai-vnc \
  --host localhost \
  --port 5901 \
  --ssh-host bastion.example.com \
  --ssh-user ubuntu \
  --ssh-password secret123 \
  screenshot --output /tmp/screen.png

# Save tunnel session for reuse
shadow-ai-vnc \
  --host localhost \
  --port 5901 \
  --ssh-host bastion.example.com \
  --ssh-key ~/.ssh/id_rsa \
  connect
# Returns session ID — use with --session for all commands
```

## Authentication

```bash
# Password inline
shadow-ai-vnc --host 192.168.1.100 --password secret123 screenshot -o /tmp/screen.png

# Password from file
shadow-ai-vnc --host 192.168.1.100 --password-file ~/.vnc/passwd screenshot -o /tmp/screen.png
```

## OpenClaw Skill

This repository includes `vnc_skill.py` — a lightweight skill wrapper designed for [OpenClaw](https://github.com/openclaw/openclaw) AI agents.

### Quick Start

```bash
# Set environment variables
export VNC_SERVER=192.168.1.100
export VNC_PORT=5900
export VNC_PASSWORD=yourpassword
export VNC_TIMEOUT=30

# Capture screenshot
python3 vnc_skill.py screenshot /tmp/screen.png

# Send input
python3 vnc_skill.py type "Hello World"
python3 vnc_skill.py key Return
python3 vnc_skill.py click 500 300
```

### Skill Functions

| Function | Description | Example |
|----------|-------------|---------|
| `vnc_screenshot(path)` | Capture screen to file | `vnc_screenshot("/tmp/screen.png")` |
| `vnc_type(text)` | Type text string | `vnc_type("Hello")` |
| `vnc_key(key)` | Send key press | `vnc_key("ctrl-c")` |
| `vnc_click(x, y, button)` | Mouse click (button: 1=left, 2=middle, 3=right) | `vnc_click(100, 200)` |
| `vnc_move(x, y)` | Move mouse to coordinates | `vnc_move(500, 300)` |

### Integration Example

```python
import subprocess
import json

def vnc_screenshot(output: str = "/tmp/vnc_screenshot.png") -> dict:
    result = subprocess.run(
        ["python3", "vnc_skill.py", "screenshot", output],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

def vnc_type(text: str) -> dict:
    result = subprocess.run(
        ["python3", "vnc_skill.py", "type", text],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)
```

---

## Standalone CLI

The main `shadow-ai-vnc` CLI provides additional features like session persistence and SSH tunneling.

## Key Mappings

- `Return`, `Enter`, `Escape`, `Tab`, `BackSpace`, `Delete`
- `Home`, `End`, `Page_Up`, `Page_Down`
- `Left`, `Right`, `Up`, `Down`
- `F1` through `F12`
- Combinations: `ctrl-alt-t`, `ctrl-c`, etc.

## Security Notes

- Passwords via `--password` appear in process lists — use `--password-file` or sessions
- Session files stored in `/tmp/shadow-ai-vnc/` (pickle format, includes passwords)
- SSH tunnels use paramiko; key auth preferred over password

## Project Structure

```
shadow-ai-vnc/
├── vnc_skill.py        # OpenClaw skill wrapper (simple, no deps)
├── shadow-ai-vnc.py    # Full CLI with sessions & SSH tunneling
├── shadow-ai-vnc-fixed.py  # Enhanced version with fixes
├── vncctl.py         # VNC control utility
├── requirements.txt    # Dependencies
├── setup.py           # Package setup
├── LICENSE            # MIT License
└── README.md          # This file
```
