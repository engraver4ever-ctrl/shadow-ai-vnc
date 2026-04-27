"""
shadow_ai_vnc.cli - Command-line interface

Drop-in replacement for vncdotool with better features:
- Async operation
- Format choice (PNG, JPEG, WebP)
- Scaling and region capture
- Base64 output for API integration

Usage:
    shadow-ai-vnc screenshot [options] <filename>
    shadow-ai-vnc click <x> <y>
    shadow-ai-vnc type "hello world"
    shadow-ai-vnc key Return
    shadow-ai-vnc key ctrl-c
"""

import argparse
import asyncio
import logging
import sys
import os

from .client import VNCClient

logger = logging.getLogger('shadow_ai_vnc.cli')


def get_server_from_env():
    """Get VNC server from environment variables"""
    host = os.environ.get('VNC_SERVER', 'localhost')
    port = os.environ.get('VNC_PORT', '5901')
    password = os.environ.get('VNC_PASSWORD', '')
    return f'{host}:{port}', password or None


async def cmd_set_resolution(args):
    """Set VNC server resolution (x11vnc/Xvfb only)"""
    width = args.width
    height = args.height
    display = args.display

    import subprocess
    import shutil

    # Check if we need sudo
    need_sudo = False
    try:
        lock_file = f'/tmp/.X{display.lstrip(":")}-lock'
        if os.path.exists(lock_file):
            import stat
            lock_stat = os.stat(lock_file)
            if lock_stat.st_uid != os.getuid():
                need_sudo = True
    except Exception:
        pass

    sudo_prefix = ['sudo', '-n'] if need_sudo else []

    # Method 1: Try xrandr for live resize
    try:
        cmd = sudo_prefix + ['xrandr', '-display', display, '--output', 'screen', '--mode', f'{width}x{height}']
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f'Resized display {display} to {width}x{height} via xrandr')
            return
        else:
            stderr = result.stderr.decode() if result.stderr else ''
            if 'cannot find output' in stderr.lower() or 'badoutput' in stderr.lower():
                print(f'xrandr resize not supported on {display}')
            else:
                print(f'xrandr failed: {stderr}')
    except FileNotFoundError:
        print('xrandr not found')
    except Exception as e:
        print(f'xrandr error: {e}')

    # Method 2: Kill and restart Xvfb
    print(f'Restarting Xvfb {display} with {width}x{height}...')

    # Find and kill existing Xvfb
    try:
        cmd = ['pgrep', '-f', f'Xvfb {display}']
        if need_sudo:
            cmd = ['sudo', '-n'] + cmd[1:]  # pgrep doesn't need sudo to find processes
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                kill_cmd = sudo_prefix + ['kill', '-9', pid]
                subprocess.run(kill_cmd, capture_output=True)
            await asyncio.sleep(1)
            print(f'Killed existing Xvfb processes')
    except Exception as e:
        print(f'Warning: Could not kill existing Xvfb: {e}')

    # Start new Xvfb
    try:
        xvfb_cmd = sudo_prefix + ['Xvfb', display, '-screen', '0', f'{width}x{height}x24', '-nolisten', 'tcp']
        proc = subprocess.Popen(
            xvfb_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(2)
        print(f'Started Xvfb {display} at {width}x{height}')
    except FileNotFoundError:
        print('Error: Xvfb not found. Install with: sudo apt install xvfb', file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f'Error starting Xvfb: {e}', file=sys.stderr)
        sys.exit(1)

    # Restart x11vnc if needed
    try:
        result = subprocess.run(['pgrep', '-f', f'x11vnc.*{display}'], capture_output=True, text=True)
        if result.stdout.strip():
            print(f'x11vnc should auto-reconnect to {display}')
        else:
            print(f'Warning: x11vnc not running. Start with: x11vnc -display {display} -nopw -forever -shared -rfbport 5901 -bg')
    except Exception:
        pass


async def cmd_screenshot(args):
    """Take a screenshot"""
    server, password = get_server_from_env()
    if args.server:
        server = args.server
    if args.password:
        password = args.password

    client = VNCClient(server, password=password)
    await client.connect()

    try:
        result = await client.screenshot(
            format=args.format,
            quality=args.quality,
            scale=args.scale,
            region=args.region,
            save=args.output,
        )

        if args.base64:
            print(result.to_base64(format=args.format, quality=args.quality))
        elif not args.output:
            # Default: save to /tmp/screenshot.png
            default_path = '/tmp/screenshot.png'
            result.save(default_path, format=args.format, quality=args.quality)
            print(default_path)
        else:
            print(f'{result.width}x{result.height}')

    finally:
        await client.disconnect()


async def cmd_click(args):
    """Click at coordinates"""
    server, password = get_server_from_env()
    if args.server:
        server = args.server
    if args.password:
        password = args.password

    client = VNCClient(server, password=password)
    await client.connect()

    try:
        if args.button == 'right':
            await client.right_click(args.x, args.y)
        elif args.button == 'middle':
            await client.click(args.x, args.y, button=2)
        elif args.count == 2:
            await client.double_click(args.x, args.y)
        else:
            await client.click(args.x, args.y)
    finally:
        await client.disconnect()


async def cmd_type(args):
    """Type text"""
    server, password = get_server_from_env()
    if args.server:
        server = args.server
    if args.password:
        password = args.password

    client = VNCClient(server, password=password)
    await client.connect()

    try:
        await client.type(args.text, interval=args.interval)
    finally:
        await client.disconnect()


async def cmd_key(args):
    """Press a key or key combo"""
    server, password = get_server_from_env()
    if args.server:
        server = args.server
    if args.password:
        password = args.password

    client = VNCClient(server, password=password)
    await client.connect()

    try:
        await client.key(args.key)
    finally:
        await client.disconnect()


async def cmd_scroll(args):
    """Scroll at coordinates"""
    server, password = get_server_from_env()
    if args.server:
        server = args.server
    if args.password:
        password = args.password

    client = VNCClient(server, password=password)
    await client.connect()

    try:
        await client.scroll(args.x, args.y, direction=args.direction, amount=args.amount)
    finally:
        await client.disconnect()


def parse_region(region_str):
    """Parse region string 'x,y,w,h' to tuple"""
    try:
        parts = [int(x.strip()) for x in region_str.split(',')]
        if len(parts) != 4:
            raise ValueError
        return tuple(parts)
    except ValueError:
        print(f'Error: Invalid region format: {region_str}', file=sys.stderr)
        print('Expected: x,y,width,height', file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog='shadow-ai-vnc',
        description='Asyncio-native VNC client (vncdotool replacement)'
    )
    parser.add_argument('-s', '--server', help='VNC server (host:port)')
    parser.add_argument('-p', '--password', help='VNC password')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-t', '--timeout', type=float, default=10.0, help='Timeout (seconds)')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # screenshot
    ss = subparsers.add_parser('screenshot', help='Capture screenshot')
    ss.add_argument('output', nargs='?', help='Output filename')
    ss.add_argument('-f', '--format', default='PNG', choices=['PNG', 'JPEG', 'WEBP'],
                    help='Image format')
    ss.add_argument('-q', '--quality', type=int, default=95, help='JPEG/WebP quality (1-100)')
    ss.add_argument('--scale', type=float, default=1.0, help='Scale factor (0.5 = half size)')
    ss.add_argument('-r', '--region', help='Crop region (x,y,w,h)')
    ss.add_argument('--base64', action='store_true', help='Output base64 data URI')

    # click
    cl = subparsers.add_parser('click', help='Click at coordinates')
    cl.add_argument('x', type=int, help='X coordinate')
    cl.add_argument('y', type=int, help='Y coordinate')
    cl.add_argument('-b', '--button', default='left', choices=['left', 'middle', 'right'],
                    help='Mouse button')
    cl.add_argument('-c', '--count', type=int, default=1, help='Number of clicks')

    # type
    ty = subparsers.add_parser('type', help='Type text')
    ty.add_argument('text', help='Text to type')
    ty.add_argument('-i', '--interval', type=float, default=0.02, help='Delay between chars')

    # key
    ky = subparsers.add_parser('key', help='Press key or combo')
    ky.add_argument('key', help='Key name (Return, ctrl-c, etc.)')

    # scroll
    sc = subparsers.add_parser('scroll', help='Scroll at coordinates')
    sc.add_argument('x', type=int, help='X coordinate')
    sc.add_argument('y', type=int, help='Y coordinate')
    sc.add_argument('-d', '--direction', default='down', choices=['up', 'down', 'left', 'right'],
                    help='Scroll direction')
    sc.add_argument('-a', '--amount', type=int, default=3, help='Scroll amount')

    # set-resolution
    sr = subparsers.add_parser('set-resolution', help='Set VNC server resolution (x11vnc/Xvfb only)')
    sr.add_argument('width', type=int, help='Screen width')
    sr.add_argument('height', type=int, help='Screen height')
    sr.add_argument('-d', '--display', default=':1', help='X11 display (default: :1)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Parse region if provided
    if hasattr(args, 'region') and args.region:
        args.region = parse_region(args.region)

    # Set up logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Run command
    cmd_map = {
        'screenshot': cmd_screenshot,
        'click': cmd_click,
        'type': cmd_type,
        'key': cmd_key,
        'scroll': cmd_scroll,
        'set-resolution': cmd_set_resolution,
    }

    asyncio.run(cmd_map[args.command](args))


if __name__ == '__main__':
    main()