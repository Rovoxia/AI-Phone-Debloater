"""Pure-Python QR Code generator (ISO/IEC 18004), standard library only.

No pip dependencies, no Pillow, no qrcode library.

Public API:
    generate_qr_matrix(data, ec_level='M') -> List[List[bool]]
    generate_android_qr_payload(service_name, password) -> str
    render_terminal_double_half_block(matrix, quiet_zone=2, invert=False) -> str
    render_terminal_ascii(matrix, quiet_zone=2, invert=False) -> str
    render_qr_for_terminal(payload, ec_level='M', quiet_zone=2) -> str
    verify_qr_generator() -> bool

Matrix cells: True = dark/black module, False = light/white module.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = [
    "generate_android_qr_payload",
    "generate_qr_matrix",
    "render_qr_for_terminal",
    "render_terminal_ascii",
    "render_terminal_double_half_block",
    "verify_qr_generator",
]

# ---------------------------------------------------------------------------
# Galois Field GF(2^8), reduction polynomial 0x11D (285), primitive element 2
# ---------------------------------------------------------------------------

_EXP = [0] * 512
_LOG = [0] * 256

_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_div(a: int, b: int) -> int:
    if a == 0:
        return 0
    if b == 0:
        raise ZeroDivisionError("gf_div by zero")
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def gf_pow(a: int, n: int) -> int:
    if a == 0:
        return 0
    return _EXP[(_LOG[a] * n) % 255]


# ---------------------------------------------------------------------------
# Reed-Solomon error correction
# ---------------------------------------------------------------------------

def _poly_mul(p: list[int], q: list[int]) -> list[int]:
    r = [0] * (len(p) + len(q) - 1)
    for i in range(len(p)):
        pi = p[i]
        if pi == 0:
            continue
        for j in range(len(q)):
            r[i + j] ^= gf_mul(pi, q[j])
    return r


def rs_generator_poly(ec_size: int) -> list[int]:
    gen = [1]
    for i in range(ec_size):
        gen = _poly_mul(gen, [1, gf_pow(2, i)])
    return gen


def rs_encode(data: list[int], ec_size: int) -> list[int]:
    gen = rs_generator_poly(ec_size)
    msg = list(data) + [0] * ec_size
    for i in range(len(data)):
        coef = msg[i]
        if coef == 0:
            continue
        for j in range(1, len(gen)):
            msg[i + j] ^= gf_mul(gen[j], coef)
    return msg[len(data):]


# ---------------------------------------------------------------------------
# ISO/IEC 18004 error-correction table, Versions 1..10.
#   (ec_codewords_per_block, [(num_blocks, data_codewords_per_block), ...])
# ---------------------------------------------------------------------------

_EC_TABLE = {
    1: {
        "L": (7, [(1, 19)]),
        "M": (10, [(1, 16)]),
        "Q": (13, [(1, 13)]),
        "H": (17, [(1, 9)]),
    },
    2: {
        "L": (10, [(1, 34)]),
        "M": (16, [(1, 28)]),
        "Q": (22, [(1, 22)]),
        "H": (28, [(1, 16)]),
    },
    3: {
        "L": (15, [(1, 55)]),
        "M": (26, [(1, 44)]),
        "Q": (18, [(2, 17)]),
        "H": (22, [(2, 13)]),
    },
    4: {
        "L": (20, [(1, 80)]),
        "M": (18, [(2, 32)]),
        "Q": (26, [(2, 24)]),
        "H": (16, [(4, 9)]),
    },
    5: {
        "L": (26, [(1, 108)]),
        "M": (24, [(2, 43)]),
        "Q": (18, [(2, 15), (2, 16)]),
        "H": (22, [(2, 11), (2, 12)]),
    },
    6: {
        "L": (18, [(2, 68)]),
        "M": (16, [(4, 27)]),
        "Q": (24, [(4, 19)]),
        "H": (28, [(4, 15)]),
    },
    7: {
        "L": (20, [(2, 78)]),
        "M": (18, [(4, 31)]),
        "Q": (18, [(2, 14), (4, 15)]),
        "H": (26, [(4, 13), (1, 14)]),
    },
    8: {
        "L": (24, [(2, 97)]),
        "M": (22, [(2, 38), (2, 39)]),
        "Q": (22, [(4, 18), (2, 19)]),
        "H": (26, [(4, 14), (2, 15)]),
    },
    9: {
        "L": (30, [(2, 116)]),
        "M": (22, [(3, 36), (2, 37)]),
        "Q": (20, [(4, 16), (4, 17)]),
        "H": (24, [(4, 12), (4, 13)]),
    },
    10: {
        "L": (18, [(2, 68), (2, 69)]),
        "M": (26, [(4, 43), (1, 44)]),
        "Q": (24, [(6, 19), (2, 20)]),
        "H": (28, [(6, 15), (2, 16)]),
    },
}

_ALIGNMENT_CENTERS = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 28, 46],
    10: [6, 32, 50],
}

# 7x7 finder pattern (1 = dark)
_FINDER = [
    [1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1],
]

# 8 penalty mask functions (mask True => invert the data module)
_MASKS = [
    lambda r, c: (r + c) % 2 == 0,                    # 0
    lambda r, c: r % 2 == 0,                          # 1
    lambda r, c: c % 3 == 0,                          # 2
    lambda r, c: (r + c) % 3 == 0,                    # 3
    lambda r, c: ((r // 2) + (c // 3)) % 2 == 0,      # 4
    lambda r, c: (((r * c) % 2) + ((r * c) % 3)) == 0,  # 5
    lambda r, c: ((((r * c) % 2) + ((r * c) % 3)) % 2) == 0,  # 6
    lambda r, c: ((((r * c) % 3) + ((r + c) % 2)) % 2) == 0,  # 7
]


# ---------------------------------------------------------------------------
# Version selection
# ---------------------------------------------------------------------------

def _total_data_codewords(version: int, ec_level: str) -> int:
    _, groups = _EC_TABLE[version][ec_level]
    return sum(num * dpb for num, dpb in groups)


def _select_version(data_bytes: bytes, ec_level: str) -> int:
    for version in range(1, 11):
        total_data = _total_data_codewords(version, ec_level)
        count_bits = 8 if version <= 9 else 16
        total_bits = 4 + count_bits + len(data_bytes) * 8
        # Reserve up to 4 bits for the terminator, then pad to byte boundary.
        needed_codewords = (total_bits + 4 + 7) // 8
        if needed_codewords <= total_data:
            return version
    return 10


# ---------------------------------------------------------------------------
# Remainder bits per version (ISO/IEC 18004 Table 1)
# ---------------------------------------------------------------------------

_REMAINDER_BITS = {
    1: 0,
    2: 7,
    3: 7,
    4: 7,
    5: 7,
    6: 7,
    7: 0,
    8: 0,
    9: 0,
    10: 0,
}


# ---------------------------------------------------------------------------
# Bit stream -> data codewords
# ---------------------------------------------------------------------------

def _data_codewords(data_bytes: bytes, version: int, total_data_codewords: int) -> list[int]:
    count_bits = 8 if version <= 9 else 16
    bit_stream: list[int] = []
    # Mode indicator: Byte mode = 0100
    bit_stream.extend((0, 1, 0, 0))
    # Character count
    count = len(data_bytes)
    for i in range(count_bits - 1, -1, -1):
        bit_stream.append((count >> i) & 1)
    # Data bytes, MSB first
    for b in data_bytes:
        for i in range(7, -1, -1):
            bit_stream.append((b >> i) & 1)
    # Terminator (up to four zero bits)
    capacity_bits = total_data_codewords * 8
    avail = capacity_bits - len(bit_stream)
    bit_stream.extend([0] * min(4, max(avail, 0)))
    # Pad to byte boundary
    while len(bit_stream) % 8:
        bit_stream.append(0)
    # Pad bytes 0xEC, 0x11 alternating
    pad = 0xEC
    while len(bit_stream) < capacity_bits:
        for i in range(7, -1, -1):
            bit_stream.append((pad >> i) & 1)
        pad = 0x11 if pad == 0xEC else 0xEC
    # Pack into codewords
    codewords: list[int] = []
    for i in range(0, len(bit_stream), 8):
        cw = 0
        for b in bit_stream[i:i + 8]:
            cw = (cw << 1) | b
        codewords.append(cw)
    return codewords


# ---------------------------------------------------------------------------
# Block interleaving + Reed-Solomon EC
# ---------------------------------------------------------------------------

def _interleaved_codewords(
    codewords: list[int], ec_level: str, version: int
) -> list[int]:
    ec_per_block, groups = _EC_TABLE[version][ec_level]
    blocks: list[tuple[list[int], list[int]]] = []
    idx = 0
    for num_blocks, dpb in groups:
        for _ in range(num_blocks):
            block = codewords[idx:idx + dpb]
            idx += dpb
            blocks.append((block, rs_encode(block, ec_per_block)))
    result: list[int] = []
    # Interleave data codewords (round-robin across blocks)
    max_data = max(len(b[0]) for b in blocks)
    for i in range(max_data):
        for block, _ec in blocks:
            if i < len(block):
                result.append(block[i])
    # Interleave EC codewords
    for i in range(ec_per_block):
        for _block, ec in blocks:
            result.append(ec[i])
    return result


# ---------------------------------------------------------------------------
# Function pattern placement
# ---------------------------------------------------------------------------

def _place_finders(matrix: list[list[bool]], function: list[list[bool]], size: int) -> None:
    positions = [(0, 0), (0, size - 7), (size - 7, 0)]
    for r0, c0 in positions:
        for dr in range(7):
            for dc in range(7):
                matrix[r0 + dr][c0 + dc] = bool(_FINDER[dr][dc])
                function[r0 + dr][c0 + dc] = True
        # Separator: 1-module wide white border surrounding each 7x7 finder pattern
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                if 0 <= dr < 7 and 0 <= dc < 7:
                    continue
                r = r0 + dr
                c = c0 + dc
                if 0 <= r < size and 0 <= c < size:
                    matrix[r][c] = False
                    function[r][c] = True


def _place_alignment(
    matrix: list[list[bool]], function: list[list[bool]], version: int, size: int
) -> None:
    centers = _ALIGNMENT_CENTERS[version]
    pattern = [
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 1, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 1],
    ]
    for r_center in centers:
        for c_center in centers:
            # Skip the 3 corners where finder patterns are located
            if (
                (r_center == centers[0] and c_center == centers[0])
                or (r_center == centers[0] and c_center == centers[-1])
                or (r_center == centers[-1] and c_center == centers[0])
            ):
                continue
            for dr in range(5):
                for dc in range(5):
                    r = r_center - 2 + dr
                    c = c_center - 2 + dc
                    if 0 <= r < size and 0 <= c < size:
                        matrix[r][c] = bool(pattern[dr][dc])
                        function[r][c] = True


def _place_timing(matrix: list[list[bool]], function: list[list[bool]], size: int) -> None:
    for i in range(8, size - 7):
        val = bool((i - 8) % 2 == 0)
        matrix[6][i] = val
        function[6][i] = True
        matrix[i][6] = val
        function[i][6] = True


def _place_dark(matrix: list[list[bool]], function: list[list[bool]], version: int, size: int) -> None:
    r = 4 * version + 9
    c = 8
    if 0 <= r < size and 0 <= c < size:
        matrix[r][c] = True
        function[r][c] = True


def _mark_format_areas(function: list[list[bool]], size: int) -> None:
    for i in range(9):
        if i < size:
            function[8][i] = True
            function[i][8] = True
    for i in range(8):
        if size - 1 - i >= 0:
            function[8][size - 1 - i] = True
            function[size - 1 - i][8] = True


# ---------------------------------------------------------------------------
# Format information (15 bits, BCH(15,5) with generator 0x537, mask 0x5412)
# ---------------------------------------------------------------------------

_LEVEL_CODE = {"L": 1, "M": 0, "Q": 3, "H": 2}


def _bch_format(level_code: int, mask: int) -> int:
    msg = (level_code << 3) | mask  # 5 bits
    gen = 0x537
    msg <<= 10
    for i in range(14, 9, -1):
        if (msg >> i) & 1:
            msg ^= gen << (i - 10)
    code = ((level_code << 3) | mask) << 10 | (msg & 0x3FF)
    return code ^ 0x5412


def _place_format_info(
    matrix: list[list[bool]],
    version: int,
    mask: int,
    ec_level: str,
    size: int,
) -> None:
    code = _bch_format(_LEVEL_CODE[ec_level], mask)
    # Top-left copy: Bit 14 (MSB) at (8, 0) down to Bit 0 (LSB) at (0, 8)
    coords_tl = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    for i, (r, c) in enumerate(coords_tl):
        bit_idx = 14 - i
        if r < size and c < size:
            matrix[r][c] = bool((code >> bit_idx) & 1)

    # Redundant copies: bottom-left (bits 0-6) and top-right (bits 7-14)
    coords_copy = [
        (size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8),
        (size - 5, 8), (size - 6, 8), (size - 7, 8),
        (8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5),
        (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1),
    ]
    for bit_idx, (r, c) in enumerate(coords_copy):
        if r < size and c < size:
            matrix[r][c] = bool((code >> bit_idx) & 1)


# ---------------------------------------------------------------------------
# Data placement (zigzag, two columns at a time)
# ---------------------------------------------------------------------------

def _data_coords(size: int) -> list[tuple[int, int]]:
    coords: list[tuple[int, int]] = []
    col = size - 1
    up = True
    while col > 0:
        if col == 6:  # timing pattern column
            col -= 1
            continue
        rows = range(size - 1, -1, -1) if up else range(size)
        for r in rows:
            for c in (col, col - 1):
                if 0 <= c < size:
                    coords.append((r, c))
        col -= 2
        up = not up
    return coords


def _fill_data(
    matrix: list[list[bool]],
    function: list[list[bool]],
    bit_stream: list[int],
    mask: int,
    size: int,
) -> None:
    maskf = _MASKS[mask]
    idx = 0
    n = len(bit_stream)
    for (r, c) in _data_coords(size):
        if function[r][c]:
            continue
        if idx >= n:
            break
        matrix[r][c] = bool((bit_stream[idx] ^ (1 if maskf(r, c) else 0)) & 1)
        idx += 1


# ---------------------------------------------------------------------------
# Mask penalty evaluation (N1-N4)
# ---------------------------------------------------------------------------

def _n1_run_penalty(seq: list[bool]) -> int:
    p = 0
    i = 0
    n = len(seq)
    while i < n:
        j = i
        while j < n and seq[j] == seq[i]:
            j += 1
        length = j - i
        if length >= 5:
            p += 3 + (length - 5)
        i = j
    return p


def _count_n3(seq: list[bool]) -> int:
    n = len(seq)
    cnt = 0
    for i in range(n - 6):
        if (
            seq[i]
            and not seq[i + 1]
            and seq[i + 2]
            and seq[i + 3]
            and seq[i + 4]
            and not seq[i + 5]
            and seq[i + 6]
        ) and (i == 0 or not seq[i - 1]) and (i + 7 >= n or not seq[i + 7]):
            cnt += 1
    return cnt


def _penalty(matrix: list[list[bool]], size: int) -> int:
    p = 0
    # N1: runs of 5+ identical modules in rows and columns
    for r in range(size):
        p += _n1_run_penalty(matrix[r])
    for c in range(size):
        p += _n1_run_penalty([matrix[r][c] for r in range(size)])
    # N2: 2x2 blocks of identical color
    for r in range(size - 1):
        for c in range(size - 1):
            v = matrix[r][c]
            if matrix[r][c + 1] == v and matrix[r + 1][c] == v and matrix[r + 1][c + 1] == v:
                p += 3
    # N3: finder-like pattern 1:1:3:1:1 (dark:light:dark:dark:dark:light:dark)
    for r in range(size):
        p += 40 * _count_n3(matrix[r])
    for c in range(size):
        p += 40 * _count_n3([matrix[r][c] for r in range(size)])
    # N4: deviation of dark-module proportion from 50%
    dark = sum(1 for r in range(size) for c in range(size) if matrix[r][c])
    total = size * size
    if total:
        pct = dark * 100.0 / total
        p += int(abs(pct - 50.0) // 5) * 10
    return p


# ---------------------------------------------------------------------------
# Public: matrix generation
# ---------------------------------------------------------------------------

def generate_qr_matrix(data: str, ec_level: str = "M") -> list[list[bool]]:
    """Generate a QR code matrix for *data*.

    Returns a square 2D list of bools (True = dark module). Auto-selects the
    smallest Version 1..10 that fits *data* at *ec_level* (L/M/Q/H, default M).
    """
    ec_level = ec_level.upper()
    if ec_level not in _LEVEL_CODE:
        ec_level = "M"
    data_bytes = data.encode("utf-8")
    version = _select_version(data_bytes, ec_level)
    size = 17 + 4 * version
    _ec_per_block, groups = _EC_TABLE[version][ec_level]
    total_data = sum(num * dpb for num, dpb in groups)

    codewords = _data_codewords(data_bytes, version, total_data)
    interleaved = _interleaved_codewords(codewords, ec_level, version)
    bit_stream: list[int] = []
    for cw in interleaved:
        for i in range(7, -1, -1):
            bit_stream.append((cw >> i) & 1)

    rem_bits = _REMAINDER_BITS.get(version, 0)
    if rem_bits:
        bit_stream.extend([0] * rem_bits)

    matrix = [[False] * size for _ in range(size)]
    function = [[False] * size for _ in range(size)]

    _place_finders(matrix, function, size)
    _place_alignment(matrix, function, version, size)
    _place_timing(matrix, function, size)
    _place_dark(matrix, function, version, size)
    _mark_format_areas(function, size)

    # Pick the mask with the lowest penalty.
    best_mask = 0
    best_penalty = None
    for mask in range(8):
        # Reset data modules for a fresh evaluation.
        for r in range(size):
            for c in range(size):
                if not function[r][c]:
                    matrix[r][c] = False
        _fill_data(matrix, function, bit_stream, mask, size)
        pen = _penalty(matrix, size)
        if best_penalty is None or pen < best_penalty:
            best_penalty = pen
            best_mask = mask

    for r in range(size):
        for c in range(size):
            if not function[r][c]:
                matrix[r][c] = False
    _fill_data(matrix, function, bit_stream, best_mask, size)
    _place_format_info(matrix, version, best_mask, ec_level, size)
    return matrix


# ---------------------------------------------------------------------------
# Android Wireless Debugging payload
# ---------------------------------------------------------------------------

def generate_android_qr_payload(service_name: str, password: str) -> str:
    """Return the ADB wireless-debugging Wi-Fi QR payload."""
    return f"WIFI:T:ADB;S:{service_name};P:{password};;"


# ---------------------------------------------------------------------------
# Terminal renderers
# ---------------------------------------------------------------------------

def _pad_quiet_zone(
    matrix: list[list[bool]], quiet_zone: int
) -> list[list[bool]]:
    if quiet_zone <= 0:
        return matrix
    size = len(matrix)
    padded = [[False] * (size + 2 * quiet_zone) for _ in range(size + 2 * quiet_zone)]
    for r in range(size):
        for c in range(size):
            padded[r + quiet_zone][c + quiet_zone] = matrix[r][c]
    return padded


def render_terminal_double_half_block(
    matrix: list[list[bool]], quiet_zone: int = 4, invert: bool = False
) -> str:
    """Render a QR matrix using Unicode half-blocks (two matrix rows per line).

    Dark module = black (background on a dark terminal), light module = white.
    Set ``invert=True`` for light-background terminals.
    """
    padded = _pad_quiet_zone(matrix, quiet_zone)
    rows = len(padded)
    cols = len(padded[0]) if rows else 0
    out: list[str] = []
    for r in range(0, rows, 2):
        line_chars: list[str] = []
        upper = padded[r]
        lower = padded[r + 1] if r + 1 < rows else [False] * cols
        for c in range(cols):
            ud = upper[c]
            ld = lower[c]
            if invert:
                ud = not ud
                ld = not ld
            if not ud and not ld:
                line_chars.append("█")   # both light -> full block (white)
            elif ud and ld:
                line_chars.append(" ")        # both dark -> space (background)
            elif ud and not ld:
                line_chars.append("▄")   # upper dark, lower light
            else:  # not ud and ld
                line_chars.append("▀")   # upper light, lower dark
        out.append("".join(line_chars))
    return "\n".join(out)


def render_terminal_ascii(
    matrix: list[list[bool]], quiet_zone: int = 4, invert: bool = False
) -> str:
    """Fallback ASCII renderer (two chars per module, one matrix row per line)."""
    padded = _pad_quiet_zone(matrix, quiet_zone)
    dark_ch = "  " if invert else "##"
    light_ch = "##" if invert else "  "
    out: list[str] = []
    for row in padded:
        out.append("".join(dark_ch if cell else light_ch for cell in row))
    return "\n".join(out)


def render_qr_for_terminal(
    payload: str, ec_level: str = "M", quiet_zone: int = 4
) -> str:
    """Generate a QR matrix for *payload* and render it for the terminal."""
    matrix = generate_qr_matrix(payload, ec_level)
    return render_terminal_double_half_block(matrix, quiet_zone=quiet_zone)


# ---------------------------------------------------------------------------
# Self-test / verification
# ---------------------------------------------------------------------------

def verify_qr_generator() -> bool:
    """Verify the QR generator against the required invariants."""
    ok = True

    # Android payload
    if generate_android_qr_payload("test", "123456") != "WIFI:T:ADB;S:test;P:123456;;":
        ok = False

    # Matrix generation for various lengths (10, 50, 100 bytes)
    for n in (10, 50, 100):
        try:
            m = generate_qr_matrix("A" * n, "M")
            if not m or not m[0] or len(m) != len(m[0]):
                ok = False
        except (OSError, RuntimeError) as exc:
            logger.debug(f"QR matrix generation failed for size {n}: {exc}")
            ok = False

    # WIFI payload (the example from the spec: ~44 chars)
    wifi = "WIFI:T:ADB;S:studio-rovoxia-1234;P:847291;;"
    try:
        m = generate_qr_matrix(wifi, "M")
        if not m or not m[0]:
            ok = False
    except (OSError, RuntimeError) as exc:
        logger.debug(f"QR matrix generation failed for wifi: {exc}")
        ok = False

    # Terminal renderer output is non-empty with expected line count
    m = generate_qr_matrix("hello", "M")
    s = render_terminal_double_half_block(m, quiet_zone=2)
    lines = s.splitlines()
    padded_rows = len(m) + 4  # quiet_zone=2 top + 2 bottom
    expected_lines = (padded_rows + 1) // 2
    if not s or len(lines) != expected_lines:
        ok = False

    a = render_terminal_ascii(m, quiet_zone=2)
    if not a or not a.splitlines():
        ok = False

    r = render_qr_for_terminal("hello", "M", 2)
    if not r or not r.splitlines():
        ok = False

    return ok


if __name__ == "__main__":
    print("verify_qr_generator():", verify_qr_generator())
    payload = generate_android_qr_payload("studio-rovoxia-1234", "847291")
    print(payload)
    print(render_qr_for_terminal(payload, "M", 2))
