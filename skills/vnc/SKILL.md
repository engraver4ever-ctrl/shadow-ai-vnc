# shadow-ai-vnc Skill for OpenClaw

Headless VNC client for AI agents. Capture screenshots, send keystrokes, type text, and control mouse.

## Installation

Requires `vncdotool`:
```bash
pip install vncdotool
```

## Environment Variables

Configure the VNC connection:

| Variable | Default | Description |
|----------|---------|-------------|
| `VNC_SERVER` | `localhost` | VNC server IP/hostname |
| `VNC_PORT` | `5900` | VNC port |
| `VNC_PASSWORD` | _(required)_ | VNC password |
| `VNC_TIMEOUT` | `30` | Connection timeout (seconds) |

## Commands

### Screenshot
```bash
vnc_skill.py screenshot /tmp/screen.png
```
Returns: `{"success": true, "path": "...", "width": 1920, "height": 1080}`

### Key Press
```bash
vnc_skill.py key Return
vnc_skill.py key ctrl-c
vnc_skill.py key alt-f4
```
Supported: Return, Enter, Escape, Tab, BackSpace, Delete, arrows, F1-F12, combinations

### Type Text
```bash
vnc_skill.py type "Hello, World!"
```

### Mouse Click
```bash
vnc_skill.py click 500 300      # left click
vnc_skill.py click 500 300 3   # right click (button 3)
```

### Mouse Move
```bash
vnc_skill.py move 100 200
```

## OpenClaw Integration

### Skill File
Copy `vnc_skill.py` to your OpenClaw skills directory.

### Configuration (TOOLS.md)
```markdown
### VNC (shadow-ai-vnc)
- **Host:** 209.126.0.181
- **Port:** 63068
- **Password:** [your password]
- **Skill:** projects/shadow-ai-vnc/vnc_skill.py
```

### OpenClaw Skill Config
Create `skills/vnc/SKILL.md` with:
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
  VNC_SERVER: 209.126.0.181
  VNC_PORT: 63068
  VNC_PASSWORD: your_password
```

## Python API

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

# Click
vnc_click(100, 200)  # left
vnc_click(100, 200, 3)  # right
```

## Dependencies

- `vncdotool>=1.2.0`
- `Pillow>=10.0.0` (for screenshot metadata)
- OpenClaw skill wrapper