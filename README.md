# shadow-ai-vnc

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/shadow-ai-vnc.svg)](https://pypi.org/project/shadow-ai-vnc/)

Headless VNC client designed for AI agents and automation. Provides a clean CLI interface for connecting to VNC servers, capturing screenshots, and sending input commands — with SSH tunneling and session persistence.

**Built for [OpenClaw](https://github.com/openclaw/openclaw)** — includes a ready-to-use skill wrapper.

## Installation

```bash
# From PyPI (recommended)
pip install shadow-ai-vnc

# From GitHub releases (standalone binary)
# Download from https://github.com/engraver4ever-ctrl/shadow-ai-vnc/releases

# From Docker
docker pull ghcr.io/engraver4ever-ctrl/shadow-ai-vnc:latest

# Clone and install
git clone https://github.com/engraver4ever-ctrl/shadow-ai-vnc.git
cd shadow-ai-vnc
pip install -e .
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
```

## OpenClaw Integration

### Requirements

- Python 3.8+
- `vncdotool>=1.2.0`
- `Pillow>=10.0.0` (for screenshot metadata)
- OpenClaw AI assistant

### Skill Setup

1. **Install the package:**
   ```bash
   pip install shadow-ai-vnc
   ```

2. **Configure OpenClaw skills directory:**
   Copy `vnc_skill.py` to your OpenClaw skills directory.

3. **Add to TOOLS.md:**
   ```markdown
   ### VNC (shadow-ai-vnc)
   - **Host:** your-vnc-server.com
   - **Port:** 5900
   - **Password:** [your VNC password]
   - **Skill:** skills/vnc/vnc_skill.py
   ```

4. **Create skill config** at `skills/vnc/SKILL.md`:
   ```yaml
   name: vnc
   description: Headless VNC client for screenshots and input
   commands:
     - screenshot <path>
     - key <key>
     - type <text>
     - click <x> <y>
     - move <x> <y>
   env:
     VNC_SERVER: your-vnc-server.com
     VNC_PORT: 5900
     VNC_PASSWORD: your_password
   ```

### Python API for OpenClaw Agents

```python
from vnc_skill import vnc_screenshot, vnc_key, vnc_type, vnc_click, vnc_move

# Capture screenshot
result = vnc_screenshot("/tmp/screen.png")
if result["success"]:
    print(f"Saved to {result['path']}")

# Send key
vnc_key("ctrl-alt-t")

# Type text
vnc_type("Hello, World!")

# Click (left=1, mid=2, right=3)
vnc_click(100, 200)      # left click
vnc_click(100, 200, 3)  # right click
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VNC_SERVER` | `localhost` | VNC server IP/hostname |
| `VNC_PORT` | `5900` | VNC port |
| `VNC_PASSWORD` | _(required)_ | VNC password |
| `VNC_TIMEOUT` | `30` | Connection timeout (seconds) |

## Supported Keys

- **Basic:** Return, Enter, Escape, Tab, BackSpace, Delete
- **Arrows:** Home, End, Page_Up, Page_Down, Left, Right, Up, Down
- **Function:** F1 through F12
- **Combinations:** ctrl-c, ctrl-alt-t, alt-f4, etc.

## Security Notes

- Passwords via `--password` appear in process lists — use `--password-file` or sessions
- Session files stored in `/tmp/shadow-ai-vnc/` (contains passwords, keep secure)
- SSH tunnels use `paramiko` — key auth preferred over password

## Files

- `shadow-ai-vnc.py` — Full CLI with sessions & SSH tunneling
- `vnc_skill.py` — Lightweight OpenClaw skill wrapper (no extra deps)
- `vncctl.py` — VNC control utility

## License

MIT License