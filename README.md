# shadow-ai-vnc

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/shadow-ai-vnc.svg)](https://pypi.org/project/shadow-ai-vnc/)

Headless VNC client designed for AI agents and automation. Provides a clean CLI interface for connecting to VNC servers, capturing screenshots, and sending input commands — with SSH tunneling and session persistence.

**Compatible with [OpenClaw](https://github.com/openclaw/openclaw) and [Hermes Agent](https://hermes-agent.nousresearch.com/)** — includes ready-to-use skill wrappers for both platforms.

## Installation

```bash
# From PyPI (recommended)
pip install shadow-ai-vnc

# From GitHub releases (standalone binary)
# Download from https://github.com/engraver4ever-ctrl/shadow-ai-vnc/releases

# From Docker
docker pull ghcr.io/engraver4ever-ctrl/shadow-ai-vnc:latest

# Clone and install (includes asyncio-native RFB client)
git clone https://github.com/engraver4ever-ctrl/shadow-ai-vnc.git
cd shadow-ai-vnc
pip install -e .
```

## Features

- **Asyncio-native RFB 3.8 client** — no subprocess overhead, pure Python
- **Screenshot capture** — PNG, JPEG, WebP with scaling and region support
- **Input automation** — key presses, text typing, mouse clicks and moves
- **Session persistence** — reusable connections across commands
- **SSH tunneling** — connect through bastion hosts
- **Resolution control** — set VNC server resolution (x11vnc/Xvfb)
- **OpenClaw integration** — ready-to-use skill wrapper
- **Hermes Agent integration** — skill wrapper with config support

## Quick Start

```bash
# Screenshot (uses asyncio-native client)
shadow-ai-vnc -s localhost:5901 screenshot /tmp/screen.png

# Send key
shadow-ai-vnc -s localhost:5901 key Return

# Type text
shadow-ai-vnc -s localhost:5901 type "Hello, World!"

# Click
shadow-ai-vnc -s localhost:5901 click 500 300

# Set resolution (x11vnc/Xvfb only)
shadow-ai-vnc set-resolution 1920 1080
```

## Asyncio-Native Client

The package includes a custom asyncio-native RFB 3.8 implementation (`shadow_ai_vnc/` package):

```python
import asyncio
from shadow_ai_vnc import VNCClient

async def main():
    client = VNCClient('localhost:5901', password='secret')
    await client.connect()
    
    # Screenshot
    result = await client.screenshot(save='/tmp/screen.png')
    print(f"Captured {result.width}x{result.height}")
    
    # Input
    await client.click(100, 100)
    await client.type('Hello!')
    await client.key('Return')
    
    await client.disconnect()

asyncio.run(main())
```

### Supported Commands

| Command | Description |
|---------|-------------|
| `screenshot [output]` | Capture screenshot (PNG/JPEG/WEBP) |
| `click <x> <y>` | Mouse click |
| `move <x> <y>` | Mouse move |
| `type <text>` | Type text |
| `key <key>` | Key press (Return, ctrl-c, etc.) |
| `scroll <x> <y>` | Scroll wheel |
| `set-resolution <w> <h>` | Set VNC resolution (x11vnc/Xvfb) |

### Resolution Control

For x11vnc/Xvfb servers, you can change the display resolution:

```bash
# Set to 1920x1080 (default)
shadow-ai-vnc set-resolution 1920 1080

# Set to 1280x720
shadow-ai-vnc set-resolution 1280 720
```

This modifies the systemd service and restarts Xvfb.

## Legacy Client (vncdotool-based)

The original `shadow_ai_vnc_legacy.py` provides session persistence and SSH tunneling via vncdotool:

```bash
# Session management
shadow-ai-vnc --host 192.168.1.100 connect
shadow-ai-vnc --session abc123 screenshot --output /tmp/screen.png

# SSH tunneling
shadow-ai-vnc --host localhost --port 5901 \
  --ssh-host bastion.example.com --ssh-user ubuntu \
  screenshot --output /tmp/screen.png
```

## OpenClaw Integration

[OpenClaw](https://github.com/openclaw/openclaw) is a multi-provider AI assistant framework.

### Requirements

- Python 3.8+
- OpenClaw AI assistant

### Skill Setup

1. **Install the package:**
   ```bash
   pip install shadow-ai-vnc
   ```

2. **Configure OpenClaw skills directory:**
   Copy `skills/vnc/vnc_skill.py` to your OpenClaw skills directory.

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
     - screenshot <path> [scale]
     - resolution [WxH]
     - key <key>
     - type <text>
     - click <x> <y>
     - move <x> <y>
   env:
     VNC_SERVER: your-vnc-server.com
     VNC_PORT: 5900
     VNC_PASSWORD: your_password
     VNC_RESOLUTION: 1920x1080
   ```

### Python API for OpenClaw Agents

```python
from vnc_skill import vnc_screenshot, vnc_key, vnc_type, vnc_click, vnc_move, set_resolution

# Capture screenshot
result = vnc_screenshot("/tmp/screen.png")
if result["success"]:
    print(f"Saved to {result['path']} ({result['width']}x{result['height']})")

# Set resolution (x11vnc/Xvfb only)
result = set_resolution(1920, 1080)

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
| `VNC_RESOLUTION` | `1920x1080` | Default VNC resolution |

## Hermes Agent Integration

[Hermes Agent](https://hermes-agent.nousresearch.com/) is a self-improving AI agent by Nous Research with a built-in learning loop.

### Skill Setup

1. **Install the package:**
   ```bash
   pip install shadow-ai-vnc
   ```

2. **Copy the skill to your Hermes skills directory:**
   ```bash
   cp -r skills/vnc-hermes/ ~/.config/hermes/skills/
   ```

3. **Configure via Hermes config:**
   ```bash
   hermes config set vnc.server "your-vnc-server.com"
   hermes config set vnc.port "5900"
   hermes config set vnc.password "your_password"
   ```

4. **Or set environment variables:**
   ```bash
   export VNC_SERVER="your-vnc-server.com"
   export VNC_PORT="5900"
   export VNC_PASSWORD="your_password"
   ```

The skill auto-loads when terminal tools are available. Hermes will use `shadow-ai-vnc` CLI commands via the terminal toolset.

### Skill Features

- **Auto-discovery** — loads when `terminal` toolset and `exec` tool are available
- **Config integration** — uses Hermes config system for server settings
- **Platform-aware** — only loads on Linux (where VNC servers typically run)
- **Documentation** — built-in procedures, pitfalls, and verification steps

See `skills/vnc-hermes/SKILL.md` for full details.

## Supported Keys

- **Basic:** Return, Enter, Escape, Tab, BackSpace, Delete
- **Arrows:** Home, End, Page_Up, Page_Down, Left, Right, Up, Down
- **Function:** F1 through F12
- **Combinations:** ctrl-c, ctrl-alt-t, alt-f4, etc.

## Architecture

- `shadow_ai_vnc/` — Asyncio-native RFB 3.8 client
  - `transport.py` — Asyncio protocol handler with framebuffer fix
  - `protocol.py` — RFB message types and data structures
  - `client.py` — High-level VNCClient API
  - `cli.py` — CLI interface
- `shadow_ai_vnc_legacy.py` — vncdotool-based client with sessions & SSH
- `skills/vnc/vnc_skill.py` — OpenClaw skill wrapper
- `skills/vnc-hermes/` — Hermes Agent skill wrapper
- `vncctl.py` — VNC control utility

## Security Notes

- Passwords via `--password` appear in process lists — use `--password-file` or sessions
- Session files stored in `/tmp/shadow-ai-vnc/` (contains passwords, keep secure)
- SSH tunnels use `paramiko` — key auth preferred over password

## License

MIT License
