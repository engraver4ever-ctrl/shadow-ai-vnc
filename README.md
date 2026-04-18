# shadow-ai-vnc

Headless VNC client designed for AI agents and automation. Provides a clean CLI interface for connecting to VNC servers, capturing screenshots, and sending input commands — with SSH tunneling and session persistence.

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

## Integration with OpenClaw

```python
import subprocess
import json

def vnc_command(*args) -> dict:
    result = subprocess.run(
        ["shadow-ai-vnc", *args],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

# Screenshot
result = vnc_command("--host", "192.168.1.100", "screenshot", "--output", "/tmp/screen.png")

# With session
vnc_command("--host", "192.168.1.100", "connect")  # returns session_id
vnc_command("--session", "abc123", "screenshot", "--output", "/tmp/screen.png")
```

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
├── shadow-ai-vnc.py    # Main CLI
├── requirements.txt    # Dependencies
├── setup.py           # Package setup
└── README.md          # This file
```
