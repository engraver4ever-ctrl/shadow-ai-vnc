"""
shadow_ai_vnc.protocol - RFB 3.8 protocol constants and data structures

Based on:
- RFB 3.8 specification (https://datatracker.ietf.org/doc/html/rfc6143)
- vncdotool source (github.com/sibson/vncdotool) - reference only
- Architecture notes: memory/active/projects/shadow-ai-vnc/architecture-v2.md

RFB 3.8 is backwards compatible with 3.3 and 3.7:
- 3.3: Server sends single auth type immediately
- 3.7+: Server sends list of auth types, client picks
- 3.8: Adds VeNCrypt, Apple auth, extended key events
"""

from enum import IntEnum
from dataclasses import dataclass
import struct


# ─── Security Types ──────────────────────────────────────────────

class SecurityType(IntEnum):
    """RFB 3.8 security types (RFC 6143 §7.1)"""
    INVALID = 0
    NONE = 1
    VNC_AUTH = 2
    RA2 = 5
    RA2NE = 6
    TIGHT = 16
    ULTRA = 17
    TLS = 18
    VENCRYPT = 19
    SASL = 20
    APPLE_DH = 30
    APPLE_USER_PASS = 31
    MS_LOGON = 0xfffffffa
    APPLE_RA2 = 35


# ─── Client → Server Message Types ───────────────────────────────

class ClientMessageType(IntEnum):
    """C2S message type IDs (RFC 6143 §8)"""
    SET_PIXEL_FORMAT = 0
    SET_ENCODINGS = 2
    FRAMEBUFFER_UPDATE_REQUEST = 3
    KEY_EVENT = 4
    POINTER_EVENT = 5
    CLIENT_CUT_TEXT = 6


# ─── Server → Client Message Types ───────────────────────────────

class ServerMessageType(IntEnum):
    """S2C message type IDs (RFC 6143 §6)"""
    FRAMEBUFFER_UPDATE = 0
    SET_COLOUR_MAP_ENTRIES = 1
    BELL = 2
    SERVER_CUT_TEXT = 3


# ─── Encoding Types ──────────────────────────────────────────────

class Encoding(IntEnum):
    """Framebuffer encoding types (RFC 6143 §7) + extensions"""
    # Standard encodings
    RAW = 0
    COPY_RECT = 1
    RRE = 2
    CORRE = 4
    HEXTILE = 5
    ZLIB = 6
    TIGHT = 7
    ZLIBHEX = 8
    TRLE = 15
    ZRLE = 16
    HITACHI_ZYWRLE = 17
    # Pseudo-encodings (negative values in spec, stored as-is)
    DESKTOP_SIZE_PSEUDO = -223       # -223 as signed i32
    LAST_RECT_PSEUDO = -224
    POINTER_POS_PSEUDO = -225
    TIGHT_PNG_PSEUDO = -260
    QEMU_EXTENDED_KEY_PSEUDO = -258
    QEMU_LED_STATE_PSEUDO = -261
    ULTRA_EXT_PSEUDO = -272


# ─── Mouse Button Masks ──────────────────────────────────────────

class MouseButton(IntEnum):
    """Pointer event button masks (RFC 6143 §8.5)"""
    LEFT = 1
    MIDDLE = 2
    RIGHT = 4
    SCROLL_UP = 8
    SCROLL_DOWN = 16
    SCROLL_LEFT = 32
    SCROLL_RIGHT = 64


# ─── Key Sym Constants ───────────────────────────────────────────

# X11 keysyms for common keys (partial list)
# Full list: https://www.cl.cam.ac.uk/~mgk25/ucs/keysyms.txt
KEYSYM = {
    # Special keys
    'BackSpace': 0xff08, 'Tab': 0xff09, 'Return': 0xff0d,
    'Escape': 0xff1b, 'Delete': 0xffff, 'Home': 0xff50,
    'Left': 0xff51, 'Up': 0xff52, 'Right': 0xff53, 'Down': 0xff54,
    'Page_Up': 0xff55, 'Page_Down': 0xff56, 'End': 0xff57,
    'Insert': 0xff63,
    # Function keys
    'F1': 0xffbe, 'F2': 0xffbf, 'F3': 0xffc0, 'F4': 0xffc1,
    'F5': 0xffc2, 'F6': 0xffc3, 'F7': 0xffc4, 'F8': 0xffc5,
    'F9': 0xffc6, 'F10': 0xffc7, 'F11': 0xffc8, 'F12': 0xffc9,
    # Modifiers
    'Shift_L': 0xffe1, 'Shift_R': 0xffe2,
    'Control_L': 0xffe3, 'Control_R': 0xffe4,
    'Alt_L': 0xffe9, 'Alt_R': 0xffea,
    'Super_L': 0xffeb, 'Super_R': 0xffec,
    'Caps_Lock': 0xffe5, 'Num_Lock': 0xff7f,
    # Keypad
    'KP_0': 0xffb0, 'KP_1': 0xffb1, 'KP_2': 0xffb2, 'KP_3': 0xffb3,
    'KP_4': 0xffb4, 'KP_5': 0xffb5, 'KP_6': 0xffb6, 'KP_7': 0xffb7,
    'KP_8': 0xffb8, 'KP_9': 0xffb9,
    'KP_Enter': 0xff8d, 'KP_Add': 0xffab, 'KP_Subtract': 0xffad,
    'KP_Multiply': 0xffaa, 'KP_Divide': 0xffaf,
    # Space and common
    'space': 0x0020, 'exclam': 0x0021, 'quotedbl': 0x0022,
    'numbersign': 0x0023, 'dollar': 0x0024, 'percent': 0x0025,
    'ampersand': 0x0026, 'apostrophe': 0x0027, 'parenleft': 0x0028,
    'parenright': 0x0029, 'asterisk': 0x002a, 'plus': 0x002b,
    'comma': 0x002c, 'minus': 0x002d, 'period': 0x002e, 'slash': 0x002f,
    'colon': 0x003a, 'semicolon': 0x003b, 'less': 0x003c,
    'equal': 0x003d, 'greater': 0x003e, 'question': 0x003f,
    'at': 0x0040, 'bracketleft': 0x005b, 'backslash': 0x005c,
    'bracketright': 0x005d, 'asciicircum': 0x005e, 'underscore': 0x005f,
    'grave': 0x0060, 'braceleft': 0x007b, 'bar': 0x007c,
    'braceright': 0x007d, 'asciitilde': 0x007e,
}

# Modifier key names for combo parsing (e.g., "ctrl-alt-t")
MODIFIER_KEYS = {
    'ctrl': 'Control_L', 'control': 'Control_L',
    'alt': 'Alt_L', 'option': 'Alt_L',
    'shift': 'Shift_L',
    'super': 'Super_L', 'cmd': 'Super_L', 'win': 'Super_L', 'meta': 'Super_L',
}


# ─── Pixel Format ────────────────────────────────────────────────

@dataclass
class PixelFormat:
    """16-byte pixel format descriptor (RFC 6143 §7.4)"""
    bpp: int = 32
    depth: int = 24
    big_endian: bool = False
    true_colour: bool = True
    red_max: int = 255
    green_max: int = 255
    blue_max: int = 255
    red_shift: int = 16
    green_shift: int = 8
    blue_shift: int = 0

    def pack(self) -> bytes:
        """Serialize to 16 bytes for RFB wire format"""
        return struct.pack(
            '>BBBBHHHBBBxxx',
            self.bpp, self.depth,
            int(self.big_endian), int(self.true_colour),
            self.red_max, self.green_max, self.blue_max,
            self.red_shift, self.green_shift, self.blue_shift
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'PixelFormat':
        """Deserialize from 16 bytes"""
        bpp, depth, big_endian, true_colour, \
        red_max, green_max, blue_max, \
        red_shift, green_shift, blue_shift = struct.unpack(
            '>BBBBHHHBBBxxx', data[:16]
        )
        return cls(
            bpp=bpp, depth=depth,
            big_endian=bool(big_endian),
            true_colour=bool(true_colour),
            red_max=red_max, green_max=green_max, blue_max=blue_max,
            red_shift=red_shift, green_shift=green_shift, blue_shift=blue_shift
        )

    @property
    def bytes_per_pixel(self) -> int:
        return self.bpp // 8

    def __str__(self) -> str:
        return f'PixelFormat({self.bpp}bpp depth={self.depth} R={self.red_max}:{self.red_shift} G={self.green_max}:{self.green_shift} B={self.blue_max}:{self.blue_shift})'


# ─── Default pixel format ────────────────────────────────────────

# Request RGBA from server (matches what PIL expects)
DEFAULT_PIXEL_FORMAT = PixelFormat(
    bpp=32, depth=24,
    big_endian=False, true_colour=True,
    red_max=255, green_max=255, blue_max=255,
    red_shift=16, green_shift=8, blue_shift=0
)