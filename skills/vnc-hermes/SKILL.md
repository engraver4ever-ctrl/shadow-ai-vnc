---
name: vnc
description: Headless VNC client for AI agents. Capture screenshots, send keystrokes, type text, and control mouse via VNC connection.
version: 1.1.0
author: engraver4ever-ctrl
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [automation, remote-desktop, vnc, screenshot]
    related_skills: []
    requires_toolsets: [terminal]
    requires_tools: [exec]
config:
  - key: vnc.server
    description: "VNC server hostname or IP"
    default: "localhost"
    prompt: "Enter VNC server IP or hostname"
  - key: vnc.port
    description: "VNC server port"
    default: "5900"
    prompt: "Enter VNC port"
  - key: vnc.password
    description: "VNC authentication password"
    default: ""
    prompt: "Enter VNC password"
  - key: vnc.timeout
    description: "Connection timeout in seconds"
    default: "30"
    prompt: "Enter timeout in seconds"
required_environment_variables:
  - name: VNC_SERVER
    prompt: "VNC server IP or hostname"
    help: "The IP or hostname of the VNC server"
    required_for: "VNC connection"
  - name: VNC_PORT
    prompt: "VNC port number"
    help: "Default is 5900"
    required_for: "VNC connection"
  - name: VNC_PASSWORD
    prompt: "VNC password"
    help: "Authentication password for VNC server"
    required_for: "VNC authentication"
---

# VNC Remote Desktop Control

Control remote machines via VNC. Capture screenshots, send keyboard input, move/click mouse.

## When to Use

- Need to see what's on a remote screen
- Automating tasks on a remote machine
- Testing GUI applications
- Debugging visual issues
- Sending keyboard/mouse input to headless servers

## Quick Reference

| Command | Description | Example |
|---------|-------------|---------|
| `screenshot <path>` | Capture screenshot | `screenshot /tmp/screen.png` |
| `key <key>` | Send key press | `key Return`, `key ctrl-alt-t` |
| `type <text>` | Type text | `type "Hello World"` |
| `click <x> <y>` | Click at coordinates | `click 500 300` |
| `move <x> <y>` | Move cursor | `move 500 300` |

## Setup

1. Install shadow-ai-vnc:
```bash
pip install shadow-ai-vnc
```

2. Set environment variables:
```bash
export VNC_SERVER="your.server.ip"
export VNC_PORT="5900"
export VNC_PASSWORD="yourpassword"
```

Or configure in Hermes config:
```bash
hermes config set vnc.server "your.server.ip"
hermes config set vnc.port "5900"
hermes config set vnc.password "yourpassword"
```

## Procedure

### Capture Screenshot

```bash
shadow-ai-vnc -s ${VNC_SERVER}:${VNC_PORT} -p ${VNC_PASSWORD} screenshot /tmp/screen.png
```

### Send Keyboard Input

Single key:
```bash
shadow-ai-vnc -s ${VNC_SERVER}:${VNC_PORT} -p ${VNC_PASSWORD} key Return
```

Key combo:
```bash
shadow-ai-vnc -s ${VNC_SERVER}:${VNC_PORT} -p ${VNC_PASSWORD} key ctrl-alt-t
```

Type text:
```bash
shadow-ai-vnc -s ${VNC_SERVER}:${VNC_PORT} -p ${VNC_PASSWORD} type "Hello World"
```

### Mouse Control

Click:
```bash
shadow-ai-vnc -s ${VNC_SERVER}:${VNC_PORT} -p ${VNC_PASSWORD} click 500 300
```

Move cursor:
```bash
shadow-ai-vnc -s ${VNC_SERVER}:${VNC_PORT} -p ${VNC_PASSWORD} click 500 300
```

Note: `move` uses `click` internally since shadow-ai-vnc doesn't have a separate move command.

## Pitfalls

- **Connection refused**: VNC server not running or firewall blocking port
- **Authentication failed**: Wrong password
- **Black screen**: VNC session not active, need to start Xvfb or desktop session
- **Low resolution**: Default is 720x400 for Xvfb. Use `set-resolution` to increase
- **Timeout**: Increase `-t` value for slow connections
- **Move vs Click**: No separate move command — click moves cursor but may trigger unintended clicks

## Verification

After screenshot, verify file exists:
```bash
ls -lh /tmp/screen.png
```

Check image dimensions:
```bash
file /tmp/screen.png
```

## Scaling for OCR

Low-res VNC screenshots may need upscaling for OCR:
```bash
# Scale 2x for better text recognition
python3 -c "from PIL import Image; img = Image.open('/tmp/screen.png'); img = img.resize((img.width*2, img.height*2), Image.NEAREST); img.save('/tmp/screen_scaled.png')"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VNC_SERVER` | `localhost` | VNC server IP/hostname |
| `VNC_PORT` | `5900` | VNC port |
| `VNC_PASSWORD` | *(required)* | VNC password |
| `VNC_TIMEOUT` | `30` | Connection timeout |
| `VNC_RESOLUTION` | `1920x1080` | Default resolution |

## Python API

```python
from vnc_skill import vnc_screenshot, vnc_key, vnc_type, vnc_click, vnc_move

# Screenshot
result = vnc_screenshot("/tmp/screen.png", scale=2.0)

# Key press
vnc_key("ctrl-alt-t")

# Type text
vnc_type("Hello World")

# Click
vnc_click(100, 200)

# Move cursor
vnc_move(300, 400)
```
