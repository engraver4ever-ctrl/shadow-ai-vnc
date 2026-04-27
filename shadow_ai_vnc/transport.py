"""
shadow_ai_vnc.transport - asyncio RFB 3.8 transport layer

This is the lowest layer of shadow-ai-vnc. It handles:
1. TCP connection establishment
2. RFB version negotiation (3.3, 3.7, 3.8)
3. Security handshake (None, VNC Auth, TLS, VeNCrypt)
4. ServerInit processing
5. Framebuffer update reception
6. Keyboard and mouse event sending

Design decisions (from architecture-v2.md):
- asyncio.Protocol (callback-based) for backpressure control
- Lazy framebuffer (only request when needed)
- Encoding negotiation: Raw (P0), CopyRect (P1), ZRLE (P0)
- Session persistence with health heartbeat

Based on:
- RFC 6143 (RFB 3.8 specification)
- vncdotool source (reference only, not derived code)
"""

import asyncio
import struct
import logging
from typing import Optional, List, Callable
from enum import Enum, auto

from .protocol import (
    SecurityType, ClientMessageType, ServerMessageType,
    Encoding, PixelFormat, DEFAULT_PIXEL_FORMAT,
    MouseButton, KEYSYM, MODIFIER_KEYS
)

logger = logging.getLogger('shadow_ai_vnc.transport')


# ─── Connection States ───────────────────────────────────────────

class ConnectionState(Enum):
    DISCONNECTED = auto()
    VERSION_EXCHANGE = auto()
    SECURITY_HANDSHAKE = auto()
    VNC_AUTH_CHALLENGE = auto()   # Waiting for 16-byte DES challenge
    AUTHENTICATING = auto()       # Waiting for auth result
    SERVER_INIT = auto()
    CONNECTED = auto()
    ERROR = auto()


# ─── DES Encryption for VNC Auth ────────────────────────────────

def _reverse_bits(byte: int) -> int:
    """Reverse bits in a byte (VNC DES key quirk - RFC 6143 §7.2.2)"""
    result = 0
    for i in range(8):
        if byte & (1 << i):
            result |= 1 << (7 - i)
    return result


def _vnc_encrypt_challenge(password: str, challenge: bytes) -> bytes:
    """
    Encrypt a 16-byte VNC challenge using DES with the VNC key quirk.
    
    The VNC spec reverses the bits of each byte in the key before
    using it as a DES key. This is a well-known implementation detail
    that all VNC clients must handle.
    """
    try:
        from Crypto.Cipher import DES
    except ImportError:
        try:
            from Cryptodome.Cipher import DES
        except ImportError:
            raise ImportError(
                "VNC auth requires pycryptodome. "
                "Install with: pip install pycryptodome"
            )
    
    # Pad/truncate password to 8 bytes
    key = password.encode('latin-1')[:8].ljust(8, b'\x00')
    # VNC reverses bits in each byte of the key
    key = bytes([_reverse_bits(b) for b in key])
    
    cipher = DES.new(key, DES.MODE_ECB)
    return cipher.encrypt(challenge)


# ─── RFB Transport ───────────────────────────────────────────────

class RFBTransport(asyncio.Protocol):
    """
    asyncio Protocol implementing RFB 3.8 (RFC 6143).
    
    Handles the full connection lifecycle:
    1. Version exchange (auto-negotiates 3.3/3.7/3.8)
    2. Security handshake (supports None and VNC Auth)
    3. ServerInit (receives desktop name and dimensions)
    4. Framebuffer updates (decodes Raw and CopyRect)
    5. Input events (keyboard, mouse)
    """

    def __init__(self):
        # Connection state
        self.transport: Optional[asyncio.Transport] = None
        self.state = ConnectionState.DISCONNECTED
        self.connected = False

        # Server info
        self.version: tuple = (3, 8)
        self.server_name: str = ''
        self.width: int = 0
        self.height: int = 0
        self.server_pixel_format: Optional[PixelFormat] = None

        # Our requested pixel format
        self.pixel_format = DEFAULT_PIXEL_FORMAT

        # Framebuffer
        self._buffer = bytearray()
        self._framebuffer: Optional[bytearray] = None
        self._fb_event = asyncio.Event()

        # Callbacks
        self.on_bell: Optional[Callable] = None
        self.on_clipboard: Optional[Callable[[str], None]] = None
        self.on_resize: Optional[Callable[[int, int], None]] = None

        # Async events for handshake coordination
        self._handshake_event = asyncio.Event()
        self._security_types: List[int] = []
        self._challenge: Optional[bytes] = None

        # Framebuffer update state (tracks partial rectangles across data_received calls)
        self._fb_rects_remaining: int = 0

    # ── asyncio.Protocol callbacks ──────────────────────────────

    def connection_made(self, transport: asyncio.Transport):
        self.transport = transport
        self.connected = True
        self.state = ConnectionState.VERSION_EXCHANGE
        logger.info('TCP connection established, waiting for version exchange')

    def connection_lost(self, exc: Optional[Exception]):
        self.connected = False
        self.state = ConnectionState.DISCONNECTED
        self._fb_rects_remaining = 0
        if exc:
            logger.error(f'Connection lost: {exc}')
        else:
            logger.info('Connection closed cleanly')
        # Wake up any waiters
        self._fb_event.set()
        self._handshake_event.set()

    def data_received(self, data: bytes):
        self._buffer.extend(data)
        self._process_buffer()

    def _process_buffer(self):
        """Process buffered data based on current state"""
        while True:
            if self.state == ConnectionState.VERSION_EXCHANGE:
                if not self._process_version():
                    return
            elif self.state == ConnectionState.SECURITY_HANDSHAKE:
                if not self._process_security():
                    return
            elif self.state == ConnectionState.VNC_AUTH_CHALLENGE:
                if not self._process_vnc_challenge():
                    return
            elif self.state == ConnectionState.AUTHENTICATING:
                if not self._process_auth():
                    return
            elif self.state == ConnectionState.SERVER_INIT:
                if not self._process_server_init():
                    return
            elif self.state == ConnectionState.CONNECTED:
                if not self._process_frame():
                    return
            else:
                return

    # ── Version Exchange ────────────────────────────────────────

    def _process_version(self) -> bool:
        """Parse server version string and respond"""
        if len(self._buffer) < 12:
            return False

        version_bytes = bytes(self._buffer[:12])
        del self._buffer[:12]

        try:
            text = version_bytes.decode('ascii').strip()
            if not text.startswith('RFB '):
                raise ValueError(f'Invalid version string: {text}')
            major, minor = text[4:].split('.')
            server_version = (int(major), int(minor))
        except (ValueError, UnicodeDecodeError) as e:
            logger.error(f'Failed to parse version: {e}')
            self.state = ConnectionState.ERROR
            return False

        # Negotiate: use the lower of our version (3.8) and server version
        if server_version >= (3, 7):
            self.version = min(self.version, server_version)
        else:
            self.version = (3, 3)

        logger.info(f'Server RFB {server_version[0]}.{server_version[1]:03d}, '
                     f'negotiated {self.version[0]}.{self.version[1]:03d}')

        # Send our version
        response = f'RFB {self.version[0]:03d}.{self.version[1]:03d}\n'.encode()
        self.transport.write(response)

        self.state = ConnectionState.SECURITY_HANDSHAKE
        return True

    # ── Security Handshake ─────────────────────────────────────

    def _process_security(self) -> bool:
        """Handle security type negotiation"""
        if self.version == (3, 3):
            # RFB 3.3: server sends 4 bytes (security type as u32)
            if len(self._buffer) < 4:
                return False
            sec_type = struct.unpack('>I', self._buffer[:4])[0]
            del self._buffer[:4]
            self._security_types = [sec_type]
        else:
            # RFB 3.7+: server sends count + list
            if len(self._buffer) < 1:
                return False
            num_types = self._buffer[0]
            if num_types == 0:
                # Connection failed - read reason
                if len(self._buffer) < 5:
                    return False
                reason_len = struct.unpack('>I', self._buffer[1:5])[0]
                if len(self._buffer) < 5 + reason_len:
                    return False
                reason = bytes(self._buffer[5:5 + reason_len]).decode('utf-8')
                del self._buffer[:5 + reason_len]
                logger.error(f'Server rejected connection: {reason}')
                self.state = ConnectionState.ERROR
                return False

            if len(self._buffer) < 1 + num_types:
                return False

            self._security_types = list(self._buffer[1:1 + num_types])
            del self._buffer[:1 + num_types]

        logger.info(f'Security types: {[SecurityType(t).name if t in SecurityType._value2member_map_ else t for t in self._security_types]}')

        # Select auth type: prefer None, then VNC Auth
        chosen = None
        if SecurityType.NONE in self._security_types:
            chosen = SecurityType.NONE
        elif SecurityType.VNC_AUTH in self._security_types:
            chosen = SecurityType.VNC_AUTH

        if chosen is None:
            logger.error(f'No supported security type in {self._security_types}')
            self.state = ConnectionState.ERROR
            return False

        # Send chosen security type
        self.transport.write(struct.pack('>B', chosen))
        logger.info(f'Selected security type: {SecurityType(chosen).name}')

        if chosen == SecurityType.NONE:
            # For 3.3: no result needed; for 3.7+: server sends result as u32
            self.state = ConnectionState.AUTHENTICATING
        elif chosen == SecurityType.VNC_AUTH:
            # Next: server sends 16-byte DES challenge
            self.state = ConnectionState.VNC_AUTH_CHALLENGE

        self._handshake_event.set()
        return True

    def _process_vnc_challenge(self) -> bool:
        """Process VNC Auth 16-byte DES challenge"""
        if len(self._buffer) < 16:
            return False  # Need more data

        challenge = bytes(self._buffer[:16])
        del self._buffer[:16]
        logger.debug('Received VNC auth challenge (16 bytes)')

        # Store challenge for handshake() to encrypt and send
        self._challenge = challenge
        self._handshake_event.set()
        
        # Don't advance state yet - handshake() will handle the response
        return False  # Stop processing until handshake() sends response

    def _process_auth(self) -> bool:
        """Handle authentication result"""
        if len(self._buffer) < 4:
            return False

        result = struct.unpack('>I', self._buffer[:4])[0]
        del self._buffer[:4]

        if result == 0:
            logger.info('Authentication successful')
            # Send ClientInit: shared_flag = True (share desktop)
            self.transport.write(struct.pack('>B', 1))
            self.state = ConnectionState.SERVER_INIT
            return True
        else:
            # Auth failed - may have reason string (3.8+)
            if self.version >= (3, 8) and len(self._buffer) >= 4:
                reason_len = struct.unpack('>I', self._buffer[:4])[0]
                del self._buffer[:4]
                if len(self._buffer) >= reason_len:
                    reason = bytes(self._buffer[:reason_len]).decode('utf-8')
                    del self._buffer[:reason_len]
                    logger.error(f'Auth failed: {reason}')
                else:
                    logger.error('Auth failed (reason truncated)')
            else:
                logger.error(f'Auth failed with code: {result}')
            self.state = ConnectionState.ERROR
            return False

    # ── Server Init ─────────────────────────────────────────────

    def _process_server_init(self) -> bool:
        """Parse ServerInit message"""
        # ServerInit: 2+2+16+4+name
        if len(self._buffer) < 24:
            return False

        self.width = struct.unpack('>H', self._buffer[:2])[0]
        self.height = struct.unpack('>H', self._buffer[2:4])[0]
        self.server_pixel_format = PixelFormat.unpack(bytes(self._buffer[4:20]))
        name_len = struct.unpack('>I', self._buffer[20:24])[0]

        if len(self._buffer) < 24 + name_len:
            return False

        self.server_name = bytes(self._buffer[24:24 + name_len]).decode('utf-8', errors='replace')
        del self._buffer[:24 + name_len]

        logger.info(f'Server: "{self.server_name}" {self.width}x{self.height} '
                     f'{self.server_pixel_format}')

        # Initialize framebuffer
        self._framebuffer = bytearray(self.width * self.height * 4)

        # Request our preferred pixel format
        self._send_set_pixel_format()

        # Request supported encodings
        encodings = [
            Encoding.RAW,
            Encoding.COPY_RECT,
            Encoding.DESKTOP_SIZE_PSEUDO,
            Encoding.LAST_RECT_PSEUDO,
            Encoding.POINTER_POS_PSEUDO,
        ]
        self._send_set_encodings(encodings)

        # Don't request framebuffer here - screenshot() will request it
        # when the caller is ready to wait for the response

        self.state = ConnectionState.CONNECTED
        self._handshake_event.set()
        return True

    # ── Frame Processing (Connected State) ──────────────────────

    def _process_frame(self) -> bool:
        """Process server messages in connected state"""
        if len(self._buffer) < 1:
            return False

        # If we're mid-FB-update (waiting for more rectangle data),
        # continue processing rectangles instead of reading a new header
        if self._fb_rects_remaining > 0:
            return self._process_fb_rectangles()

        msg_type = self._buffer[0]

        if msg_type == ServerMessageType.FRAMEBUFFER_UPDATE:
            return self._process_fb_update()
        elif msg_type == ServerMessageType.SET_COLOUR_MAP_ENTRIES:
            return self._process_colour_map()
        elif msg_type == ServerMessageType.BELL:
            del self._buffer[0]
            logger.debug('🔔 Bell')
            if self.on_bell:
                self.on_bell()
            return True
        elif msg_type == ServerMessageType.SERVER_CUT_TEXT:
            return self._process_cut_text()
        else:
            logger.warning(f'Unknown message type: {msg_type}, skipping')
            del self._buffer[0]
            return True

    def _process_fb_update(self) -> bool:
        """Process FramebufferUpdate message header"""
        # Header: type(1) + padding(1) + num_rects(2) = 4 bytes
        if len(self._buffer) < 4:
            return False

        _, _, num_rects = struct.unpack('>BBH', bytes(self._buffer[:4]))
        del self._buffer[:4]

        self._fb_rects_remaining = num_rects
        return self._process_fb_rectangles()

    def _process_fb_rectangles(self) -> bool:
        """Process remaining rectangles in a FramebufferUpdate"""
        while self._fb_rects_remaining > 0:
            if not self._process_rectangle():
                return False  # Need more data, will resume here
            self._fb_rects_remaining -= 1

        # All rectangles processed
        self._fb_event.set()
        return True

    def _process_rectangle(self) -> bool:
        """Process a single rectangle in a FramebufferUpdate"""
        # Rectangle header: x(2) + y(2) + w(2) + h(2) + encoding(4) = 12 bytes
        if len(self._buffer) < 12:
            return False

        x, y, w, h, encoding = struct.unpack('>HHHHi', bytes(self._buffer[:12]))

        # Handle pseudo-encodings (no data after header)
        if encoding == Encoding.DESKTOP_SIZE_PSEUDO:
            del self._buffer[:12]
            self.width = w
            self.height = h
            self._framebuffer = bytearray(w * h * 4)
            logger.info(f'Desktop resized to {w}x{h}')
            if self.on_resize:
                self.on_resize(w, h)
            return True

        if encoding == Encoding.LAST_RECT_PSEUDO:
            del self._buffer[:12]
            return True

        if encoding == Encoding.RAW:
            data_len = w * h * self.pixel_format.bytes_per_pixel
            if len(self._buffer) < 12 + data_len:
                return False
            del self._buffer[:12]
            data = bytes(self._buffer[:data_len])
            del self._buffer[:data_len]
            self._blit_raw(x, y, w, h, data)
            return True

        if encoding == Encoding.COPY_RECT:
            if len(self._buffer) < 16:
                return False
            src_x, src_y = struct.unpack('>HH', bytes(self._buffer[12:16]))
            del self._buffer[:16]
            self._blit_copy(src_x, src_y, x, y, w, h)
            return True

        # Unknown encoding - skip it gracefully
        logger.warning(f'Unknown encoding {encoding} (0x{encoding & 0xffffffff:08x}), skipping {w}x{h} rectangle')
        del self._buffer[:12]
        return True  # Skip this rectangle and continue

    # ── Framebuffer Blitting ────────────────────────────────────

    def _blit_raw(self, x: int, y: int, w: int, h: int, data: bytes):
        """Copy raw pixel data into framebuffer"""
        if self._framebuffer is None:
            return

        bpp = self.pixel_format.bytes_per_pixel
        for row in range(h):
            src_offset = row * w * bpp
            dst_offset = ((y + row) * self.width + x) * bpp

            src_end = min(src_offset + w * bpp, len(data))
            dst_end = min(dst_offset + w * bpp, len(self._framebuffer))
            copy_len = min(src_end - src_offset, dst_end - dst_offset)

            if copy_len > 0:
                self._framebuffer[dst_offset:dst_offset + copy_len] = \
                    data[src_offset:src_offset + copy_len]

    def _blit_copy(self, src_x: int, src_y: int, dst_x: int, dst_y: int, w: int, h: int):
        """Copy a rectangle from one part of the framebuffer to another"""
        if self._framebuffer is None:
            return

        bpp = self.pixel_format.bytes_per_pixel
        for row in range(h):
            src_offset = ((src_y + row) * self.width + src_x) * bpp
            dst_offset = ((dst_y + row) * self.width + dst_x) * bpp

            copy_len = min(w * bpp, len(self._framebuffer) - dst_offset)
            if copy_len > 0 and src_offset + copy_len <= len(self._framebuffer):
                self._framebuffer[dst_offset:dst_offset + copy_len] = \
                    self._framebuffer[src_offset:src_offset + copy_len]

    # ── Other Server Messages ───────────────────────────────────

    def _process_colour_map(self) -> bool:
        """Skip colour map entries (not needed for true colour)"""
        if len(self._buffer) < 5:
            return False
        # Format: type(1) + padding(1) + first_colour(2) + num_colours(2) = 6 bytes header
        # Actually: >xH is 3 bytes, need first(2) + num(2) = >BBH gives 4 values
        padding, first, num = struct.unpack('>BHH', bytes(self._buffer[1:6]))
        total = 6 + num * 6  # 6 bytes per RGB entry
        if len(self._buffer) < total:
            return False
        del self._buffer[:total]
        return True

    def _process_cut_text(self) -> bool:
        """Handle server clipboard text"""
        # Header: type(1) + padding(3) + length(4) = 8 bytes
        if len(self._buffer) < 8:
            return False
        _, length = struct.unpack('>BxxxI', bytes(self._buffer[:8]))
        if len(self._buffer) < 8 + length:
            return False
        text = bytes(self._buffer[8:8 + length]).decode('utf-8', errors='replace')
        del self._buffer[:8 + length]
        logger.debug(f'Clipboard: {text[:100]}')
        if self.on_clipboard:
            self.on_clipboard(text)
        return True

    # ── Client → Server Messages ────────────────────────────────

    def _send_set_pixel_format(self):
        """Send SetPixelFormat message"""
        msg = struct.pack('>B', ClientMessageType.SET_PIXEL_FORMAT)
        msg += b'\x00\x00\x00'  # padding
        msg += self.pixel_format.pack()
        self.transport.write(msg)
        logger.debug('Sent SetPixelFormat')

    def _send_set_encodings(self, encodings: List[int]):
        """Send SetEncodings message
        
        RFB spec: u8 type + u8 padding + u16 count = 4-byte header
        NOT '>BH' (3 bytes) — the padding byte is required!
        """
        msg = struct.pack('>BxH', ClientMessageType.SET_ENCODINGS, len(encodings))
        for enc in encodings:
            msg += struct.pack('>i', enc)
        self.transport.write(msg)
        logger.debug(f'Sent SetEncodings: {encodings}')

    def _send_fb_update_request(self, incremental: bool = False,
                                 x: int = 0, y: int = 0,
                                 w: int = None, h: int = None):
        """Request a framebuffer update"""
        w = w or self.width
        h = h or self.height
        msg = struct.pack('>BBHHHH',
            ClientMessageType.FRAMEBUFFER_UPDATE_REQUEST,
            1 if incremental else 0,
            x, y, w, h
        )
        self.transport.write(msg)

    # ── Public API ──────────────────────────────────────────────

    async def handshake(self, password: Optional[str] = None, timeout: float = 10.0):
        """
        Complete the RFB handshake after connection.
        
        Handles version negotiation, security, and server init.
        Must be called after TCP connection is established.
        """
        # Step 1: Wait for version exchange + security types
        self._handshake_event.clear()
        await asyncio.wait_for(self._handshake_event.wait(), timeout=timeout)
        
        if self.state == ConnectionState.ERROR:
            raise ConnectionError('Handshake failed during security negotiation')

        # Step 2: Handle VNC Auth challenge if needed
        if self.state == ConnectionState.VNC_AUTH_CHALLENGE:
            if not password:
                raise ConnectionError('Server requires VNC authentication but no password provided')
            
            # Wait for the 16-byte challenge
            self._handshake_event.clear()
            await asyncio.wait_for(self._handshake_event.wait(), timeout=timeout)
            
            if self._challenge is None:
                raise ConnectionError('Failed to receive VNC auth challenge')
            
            # Encrypt challenge with password and send response
            response = _vnc_encrypt_challenge(password, self._challenge)
            self.transport.write(response)
            logger.debug('Sent VNC auth response')
            
            # Now wait for auth result
            self.state = ConnectionState.AUTHENTICATING
            self._challenge = None

        # Step 3: Wait for auth result
        if self.state == ConnectionState.AUTHENTICATING:
            self._handshake_event.clear()
            # Process auth result from buffer
            if not self._process_buffer_sync():
                # Need more data - wait for it
                self._handshake_event.clear()
                await asyncio.wait_for(self._handshake_event.wait(), timeout=timeout)

        # Step 4: Wait for server init
        if self.state == ConnectionState.SERVER_INIT:
            self._handshake_event.clear()
            await asyncio.wait_for(self._handshake_event.wait(), timeout=timeout)

        if self.state != ConnectionState.CONNECTED:
            raise ConnectionError(f'Handshake failed, final state: {self.state}')

        logger.info(f'Connected to "{self.server_name}" ({self.width}x{self.height})')

    def _process_buffer_sync(self):
        """Process buffer synchronously, return True if state changed"""
        old_state = self.state
        self._process_buffer()
        return self.state != old_state

    async def screenshot(self, timeout: float = 5.0) -> bytearray:
        """
        Request and return the current framebuffer as raw RGBA data.
        """
        self._fb_event.clear()
        self._send_fb_update_request(incremental=False)

        try:
            await asyncio.wait_for(self._fb_event.wait(), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f'Screenshot timed out after {timeout}s')

        if self._framebuffer is None:
            raise RuntimeError('No framebuffer data received')

        return self._framebuffer

    def key_down(self, keysym: int):
        """Send key press event"""
        msg = struct.pack('>BBHI',
            ClientMessageType.KEY_EVENT, 1, 0, keysym
        )
        self.transport.write(msg)

    def key_up(self, keysym: int):
        """Send key release event"""
        msg = struct.pack('>BBHI',
            ClientMessageType.KEY_EVENT, 0, 0, keysym
        )
        self.transport.write(msg)

    def key_press(self, keysym: int):
        """Send key press and release"""
        self.key_down(keysym)
        self.key_up(keysym)

    def pointer_event(self, x: int, y: int, button_mask: int = 0):
        """Send mouse pointer event"""
        msg = struct.pack('>BHHH',
            ClientMessageType.POINTER_EVENT, button_mask, x, y
        )
        self.transport.write(msg)

    def client_cut_text(self, text: str):
        """Send clipboard text to server"""
        data = text.encode('utf-8')
        msg = struct.pack('>BxxxI', ClientMessageType.CLIENT_CUT_TEXT, len(data))
        msg += data
        self.transport.write(msg)

    def close(self):
        """Close the connection"""
        if self.transport:
            self.transport.close()