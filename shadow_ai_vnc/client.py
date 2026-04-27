"""
shadow_ai_vnc.client - High-level async VNC client

Provides the user-facing VNCClient class that wraps the low-level
RFBTransport with convenience methods for screenshots, clicks,
typing, and session management.

Design goals (from architecture-v2.md):
- Session persistence with auto-reconnect
- Screenshot pipeline: format choice, scaling, regions
- Action engine: click, type, key combos, drag
- Backward-compatible CLI interface with vncdotool
"""

import asyncio
import io
import logging
import base64
from datetime import datetime, timezone
from typing import Optional, Tuple, Union

from PIL import Image

from .transport import RFBTransport, ConnectionState
from .protocol import (
    KEYSYM, MODIFIER_KEYS, MouseButton, PixelFormat, DEFAULT_PIXEL_FORMAT,
    SecurityType, Encoding
)

logger = logging.getLogger('shadow_ai_vnc.client')


# ─── Screenshot Result ───────────────────────────────────────────

class ScreenshotResult:
    """Rich screenshot result with metadata"""
    
    def __init__(self, image: Image.Image, server_name: str = '',
                 server_width: int = 0, server_height: int = 0,
                 timestamp: Optional[datetime] = None):
        self.image = image
        self.server_name = server_name
        self.server_width = server_width
        self.server_height = server_height
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.format = 'PNG'
        self.quality = 95
        self.scale = 1.0
        self.region = None
    
    @property
    def width(self) -> int:
        return self.image.width
    
    @property
    def height(self) -> int:
        return self.image.height
    
    def save(self, path: str, format: str = None, quality: int = None):
        """Save screenshot to file"""
        fmt = format or self.format
        q = quality or self.quality
        if fmt.upper() == 'JPEG':
            self.image.save(path, 'JPEG', quality=q)
        elif fmt.upper() == 'WEBP':
            self.image.save(path, 'WEBP', quality=q)
        else:
            self.image.save(path, 'PNG')
        logger.info(f'Screenshot saved: {path} ({self.width}x{self.height})')
    
    def to_bytes(self, format: str = 'PNG', quality: int = 95) -> bytes:
        """Convert screenshot to bytes"""
        buf = io.BytesIO()
        if format.upper() == 'JPEG':
            self.image.save(buf, 'JPEG', quality=quality)
        elif format.upper() == 'WEBP':
            self.image.save(buf, 'WEBP', quality=quality)
        else:
            self.image.save(buf, 'PNG')
        return buf.getvalue()
    
    def to_base64(self, format: str = 'PNG', quality: int = 95) -> str:
        """Return base64-encoded data URI"""
        data = self.to_bytes(format, quality)
        mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[format.upper()]
        b64 = base64.b64encode(data).decode('ascii')
        return f'data:{mime};base64,{b64}'
    
    def to_dict(self) -> dict:
        """Return screenshot metadata as dict"""
        return {
            'width': self.width,
            'height': self.height,
            'server_width': self.server_width,
            'server_height': self.server_height,
            'server_name': self.server_name,
            'format': self.format,
            'scale': self.scale,
            'timestamp': self.timestamp.isoformat(),
        }


# ─── Parse Key String ────────────────────────────────────────────

def parse_key_combo(key_string: str) -> list:
    """
    Parse a key combo string like 'ctrl-alt-t' or 'Return'.
    
    Returns a list of keysyms to press in order, then release in reverse.
    
    Supports:
    - Single keys: 'Return', 'Escape', 'a', 'A'
    - Combos with dashes: 'ctrl-c', 'ctrl-alt-t'
    - Special keys from KEYSYM dict
    """
    parts = [p.strip() for p in key_string.split('-')]
    result = []
    
    for part in parts:
        # Check if it's a modifier
        if part.lower() in MODIFIER_KEYS:
            key_name = MODIFIER_KEYS[part.lower()]
            result.append(KEYSYM[key_name])
        # Check if it's a named key
        elif part in KEYSYM:
            result.append(KEYSYM[part])
        # Check if it's a single character
        elif len(part) == 1:
            result.append(ord(part))
        else:
            logger.warning(f'Unknown key: {part}')
            result.append(ord(part[0]))
    
    return result


# ─── VNC Client ──────────────────────────────────────────────────

class VNCClient:
    """
    High-level async VNC client with session management.
    
    Usage:
        async with VNCClient('localhost:5901') as client:
            img = await client.screenshot()
            img.save('/tmp/screen.png')
            await client.click(100, 200)
            await client.type('Hello World')
            await client.key('ctrl-c')
    
    Or without context manager:
        client = VNCClient('localhost:5901')
        await client.connect(password='secret')
        try:
            img = await client.screenshot()
        finally:
            await client.disconnect()
    """

    def __init__(self, server: str, password: Optional[str] = None,
                 timeout: float = 10.0, reconnect: bool = True,
                 max_retries: int = 3):
        """
        Args:
            server: VNC server address (host:port or host)
            password: VNC password (None for no-auth servers)
            timeout: Connection and operation timeout in seconds
            reconnect: Auto-reconnect on disconnect
            max_retries: Max reconnect attempts
        """
        # Parse server address
        if ':' in server:
            self.host, port_str = server.rsplit(':', 1)
            self.port = int(port_str)
        else:
            self.host = server
            self.port = 5901

        self.password = password
        self.timeout = timeout
        self.reconnect = reconnect
        self.max_retries = max_retries

        # Internal state
        self._transport: Optional[asyncio.Transport] = None
        self._protocol: Optional[RFBTransport] = None
        self._connected = False
        self._retry_count = 0

    async def connect(self):
        """Establish connection and complete RFB handshake"""
        loop = asyncio.get_event_loop()

        for attempt in range(self.max_retries + 1):
            try:
                self._transport, self._protocol = await loop.create_connection(
                    RFBTransport, self.host, self.port
                )
                await self._protocol.handshake(password=self.password, timeout=self.timeout)
                self._connected = True
                self._retry_count = 0
                logger.info(f'Connected to {self.host}:{self.port} '
                           f'({self._protocol.width}x{self._protocol.height})')
                return
            except Exception as e:
                self._connected = False
                if attempt < self.max_retries and self.reconnect:
                    wait = min(2 ** attempt, 30)  # Exponential backoff
                    logger.warning(f'Connection attempt {attempt + 1} failed: {e}, '
                                  f'retrying in {wait}s')
                    await asyncio.sleep(wait)
                else:
                    raise ConnectionError(f'Failed to connect to {self.host}:{self.port}: {e}')

    async def disconnect(self):
        """Close the connection"""
        if self._protocol:
            self._protocol.close()
        self._connected = False
        self._transport = None
        self._protocol = None

    def _ensure_connected(self):
        """Raise if not connected"""
        if not self._connected or not self._protocol:
            raise RuntimeError('Not connected to VNC server')

    # ── Screenshot ──────────────────────────────────────────────

    async def screenshot(self, format: str = 'PNG', quality: int = 95,
                         scale: float = 1.0, region: Optional[Tuple[int,int,int,int]] = None,
                         base64: bool = False, save: Optional[str] = None) -> Union[ScreenshotResult, str]:
        """
        Capture a screenshot from the VNC server.
        
        Args:
            format: Image format ('PNG', 'JPEG', 'WEBP')
            quality: JPEG/WebP quality (1-100, default 95)
            scale: Scale factor (1.0 = original, 0.5 = half size)
            region: Crop region (x, y, width, height)
            base64: Return base64 data URI instead of ScreenshotResult
            save: Save to file path (optional)
        
        Returns:
            ScreenshotResult or base64 data URI string
        """
        self._ensure_connected()
        fb_data = await self._protocol.screenshot(timeout=self.timeout)

        # Convert framebuffer to PIL Image
        width = self._protocol.width
        height = self._protocol.height
        img = Image.frombytes('RGBA', (width, height), bytes(fb_data))
        img = img.convert('RGB')  # Drop alpha for output

        # Apply region crop
        if region:
            x, y, w, h = region
            img = img.crop((x, y, x + w, y + h))

        # Apply scale
        if scale != 1.0:
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            # Use NEAREST for >=2x downscale (pixel art), LANCZOS for <2x
            resample = Image.NEAREST if scale <= 0.5 else Image.LANCZOS
            img = img.resize((new_w, new_h), resample)

        # Build result
        result = ScreenshotResult(
            image=img,
            server_name=self._protocol.server_name,
            server_width=width,
            server_height=height,
        )
        result.format = format.upper()
        result.quality = quality
        result.scale = scale
        result.region = region

        # Save if requested
        if save:
            result.save(save, format=format, quality=quality)

        # Return base64 if requested
        if base64:
            return result.to_base64(format=format, quality=quality)

        return result

    # ── Mouse Actions ───────────────────────────────────────────

    async def click(self, x: int, y: int, button: int = 1, count: int = 1,
                    delay: float = 0.05):
        """
        Click at coordinates.
        
        Args:
            x: X coordinate (pixels)
            y: Y coordinate (pixels)
            button: Mouse button (1=left, 2=middle, 3=right)
            count: Number of clicks (1=single, 2=double)
            delay: Delay between press and release (seconds)
        """
        self._ensure_connected()
        mask = 1 << (button - 1)  # button 1=0x01, 2=0x02, 3=0x04

        for _ in range(count):
            self._protocol.pointer_event(x, y, mask)
            await asyncio.sleep(delay)
            self._protocol.pointer_event(x, y, 0)
            if count > 1:
                await asyncio.sleep(delay)

    async def right_click(self, x: int, y: int):
        """Right-click at coordinates"""
        await self.click(x, y, button=3)

    async def double_click(self, x: int, y: int):
        """Double-click at coordinates"""
        await self.click(x, y, count=2)

    async def scroll(self, x: int, y: int, direction: str = 'down', amount: int = 3):
        """
        Scroll at coordinates.
        
        Args:
            x: X coordinate
            y: Y coordinate
            direction: 'up', 'down', 'left', 'right'
            amount: Number of scroll steps
        """
        self._ensure_connected()
        
        scroll_map = {
            'up': MouseButton.SCROLL_UP,
            'down': MouseButton.SCROLL_DOWN,
            'left': MouseButton.SCROLL_LEFT,
            'right': MouseButton.SCROLL_RIGHT,
        }
        button_mask = scroll_map.get(direction, MouseButton.SCROLL_DOWN)
        
        for _ in range(amount):
            self._protocol.pointer_event(x, y, button_mask)
            await asyncio.sleep(0.01)
            self._protocol.pointer_event(x, y, 0)

    async def drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
                    button: int = 1, steps: int = 10):
        """
        Drag from start to end coordinates.
        
        Args:
            start_x, start_y: Start position
            end_x, end_y: End position
            button: Mouse button (1=left, 2=middle, 3=right)
            steps: Number of intermediate steps
        """
        self._ensure_connected()
        mask = 1 << (button - 1)
        
        # Move to start, press button
        self._protocol.pointer_event(start_x, start_y, mask)
        await asyncio.sleep(0.05)
        
        # Drag to end
        for i in range(1, steps + 1):
            x = int(start_x + (end_x - start_x) * i / steps)
            y = int(start_y + (end_y - start_y) * i / steps)
            self._protocol.pointer_event(x, y, mask)
            await asyncio.sleep(0.01)
        
        # Release
        self._protocol.pointer_event(end_x, end_y, 0)

    # ── Keyboard Actions ────────────────────────────────────────

    async def key(self, key_string: str, delay: float = 0.01):
        """
        Press a key or key combo.
        
        Args:
            key_string: Key name ('Return', 'Escape') or combo ('ctrl-c', 'ctrl-alt-t')
            delay: Delay between key down and up
        """
        self._ensure_connected()
        keysyms = parse_key_combo(key_string)
        
        # Press all keys
        for ks in keysyms:
            self._protocol.key_down(ks)
        
        await asyncio.sleep(delay)
        
        # Release in reverse order
        for ks in reversed(keysyms):
            self._protocol.key_up(ks)

    async def type(self, text: str, interval: float = 0.02):
        """
        Type a string of text.
        
        Args:
            text: Text to type
            interval: Delay between characters (seconds)
        """
        self._ensure_connected()
        for char in text:
            keysym = ord(char)
            self._protocol.key_down(keysym)
            await asyncio.sleep(interval)
            self._protocol.key_up(keysym)
            await asyncio.sleep(interval)

    # ── Clipboard ───────────────────────────────────────────────

    async def clipboard_set(self, text: str):
        """Set the VNC server clipboard text"""
        self._ensure_connected()
        self._protocol.client_cut_text(text)

    # ── Context Manager ─────────────────────────────────────────

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    # ── Properties ───────────────────────────────────────────────

    @property
    def width(self) -> int:
        """Server framebuffer width"""
        if self._protocol:
            return self._protocol.width
        return 0

    @property
    def height(self) -> int:
        """Server framebuffer height"""
        if self._protocol:
            return self._protocol.height
        return 0

    @property
    def server_name(self) -> str:
        """Server desktop name"""
        if self._protocol:
            return self._protocol.server_name
        return ''

    @property
    def is_connected(self) -> bool:
        """Whether the client is connected"""
        return self._connected and self._protocol and self._protocol.connected