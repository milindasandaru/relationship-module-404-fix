#!/usr/bin/env python3
"""
Relationship-themed terminal animation 🎔

Features
- Hearts raining across the screen (small/medium/large: ♡ ♥ ❤️ � �💕 💘)
- Intermittent funny status messages (e.g., "Compiling feelings...", "Deploying emotions...")
- Smooth looping effect using ANSI control codes
- Twinkling hearts (subtle bright/faint pulse)
- Slow start: show messages first, then gently ramp up heart rain
- Safe exit with Ctrl+C
- Optional colors (works on Windows via colorama if available)

Run
    python relationship_animation.py

Tip
- If colors/emojis look odd on Windows, try Windows Terminal or VS Code terminal.
- You can install colorama for better ANSI handling on old consoles:  pip install colorama
"""
from __future__ import annotations
import os
import random
import shutil
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple
import math

# Try to enable ANSI colors on Windows automatically
try:
    import colorama  # type: ignore
    try:
        # Just fix console if possible (newer versions)
        colorama.just_fix_windows_console()
    except Exception:
        colorama.init()  # older versions
except Exception:
    colorama = None  # type: ignore

# ANSI helpers
CSI = "\x1b["
RESET = f"{CSI}0m"
HIDE_CURSOR = f"{CSI}?25l"
SHOW_CURSOR = f"{CSI}?25h"
ALT_SCREEN_ON = f"{CSI}?1049h"
ALT_SCREEN_OFF = f"{CSI}?1049l"
BOLD = "\x1b[1m"
FAINT = "\x1b[2m"

# Color palette (soft pinks/reds/magentas)
# Pink-forward color palette (256-color friendly)
PINKS = [
    "\x1b[38;5;198m",  # deep pink
    "\x1b[38;5;199m",  # hot pink
    "\x1b[38;5;200m",  # pink
    "\x1b[38;5;205m",  # light pink
    "\x1b[38;5;206m",  # orchid-ish
    "\x1b[38;5;213m",  # orchid light
    "\x1b[38;5;219m",  # very light pink
]

# Heart glyph pools (use provided hearts instead of procedural)
# Small/outline/dainty
HEARTS_SMALL = ["♡", "❥", "ღ"]
# Medium/filled
HEARTS_MED = ["♥" ]#, "❤", "❣"]
# Large emoji hearts (pink variants)
HEARTS_LARGE = ["💖", "💗", "💕", "💞", "💓", "💝", "💟"]

# Procedural heart functions are kept for potential future use but aren't required
# when using the glyph pools above.

def heart_mask(width: int, height: int) -> List[List[float]]:
    """Return a supersampled coverage mask (0..1) for a heart of given size.
    Coverage improves shape fidelity at very small sizes.
    """
    mask: List[List[float]] = []
    # Terminal cell aspect correction (wider horizontally for balance)
    # Slightly different for tiny hearts
    x_scale = 1.18 if width <= 9 else 1.12
    y_scale = 1.0
    # Shrink the heart slightly within the cell grid to leave a margin
    # so curves are more visible and not clipped at edges
    shrink = 0.90 if width <= 7 else 0.95
    # Small threshold relax for tiny hearts
    base_threshold = 0.01 if width <= 7 else 0.0

    # Supersampling grid size (performance-friendly)
    ss = 4 if width <= 9 else 3  # higher for small-to-medium hearts to improve edges
    inv = 1.0 / ss

    for row in range(height):
        line: List[float] = []
        for col in range(width):
            inside_count = 0
            for sr in range(ss):
                for sc in range(ss):
                    # Center subsamples within the cell
                    fr = (row + (sr + 0.5) * inv) / max(1.0, height - 1.0)
                    fc = (col + (sc + 0.5) * inv) / max(1.0, width - 1.0)
                    y = 1.0 - 2.0 * fr
                    x = -1.0 + 2.0 * fc
                    x *= (x_scale * shrink)
                    y *= (y_scale * shrink)
                    v = (x * x + y * y - 1.0)
                    inside = (v * v * v - x * x * (y * y * y)) <= base_threshold
                    if inside:
                        inside_count += 1
            coverage = inside_count / float(ss * ss)
            line.append(coverage)
        mask.append(line)
    return mask

def mask_to_sprite(mask: List[List[float]], style: str = "filled") -> List[str]:
    h = len(mask)
    w = len(mask[0]) if h else 0
    # Characters for drawing (smaller visual footprint for clearer tiny hearts)
    fill_char = "•"     # small bullet for fill
    mid_char = "·"      # middle dot for soft edges
    outline_char = "·"  # outline uses dot as well

    rows: List[str] = []
    # Helper to decide char from coverage
    def char_from_coverage(cov: float, mode: str) -> str:
        if mode == "outline":
            # Consider boundary band
            return outline_char if 0.25 <= cov <= 0.75 else (" " if cov < 0.25 else " ")
        # filled
        if cov >= 0.66:
            return fill_char
        elif cov >= 0.3:
            return mid_char
        else:
            return " "

    for r in range(h):
        line_chars: List[str] = []
        for c in range(w):
            cov = mask[r][c]
            line_chars.append(char_from_coverage(cov, style))
        rows.append("".join(line_chars).rstrip())  # trim trailing spaces per row
    # Remove empty rows at top/bottom to tighten sprite
    while rows and rows[0].strip() == "":
        rows.pop(0)
    while rows and rows[-1].strip() == "":
        rows.pop()
    # Normalize width by padding to the max width among rows
    maxw = max((len(r) for r in rows), default=0)
    rows = [r + " " * (maxw - len(r)) for r in rows]
    return rows

def make_heart_sprite(size: str, style: str) -> List[str]:
    # Choose base sizes per category (larger for better shape recognition)
    if size == "small":
        w, h = 9, 8
    elif size == "medium":
        w, h = 13, 11
    else:  # large
        w, h = 17, 15
    return mask_to_sprite(heart_mask(w, h), style)
MESSAGES = [
    "Compiling feelings...",
    "Deploying emotions...",
    "FlirtingAPI initializing...",
    "Authenticating chemistry...",
    "Encrypting heartbeats...",
    "Loading love language pack...",
    "Spinning up butterflies...",
    "Warming up smile engine...",
    "Negotiating date protocol...",
]

@dataclass
class Heart:
    x: int
    y: float
    color: str
    speed: float
    size: str  # 'small' | 'medium' | 'large'
    style: str  # 'filled' | 'outline'
    sprite: List[str]
    w: int
    h: int
    twinkle_phase: int  # 0 normal, 1 bright, 2 faint
    twinkle_next: float

    def step(self):
        self.y += self.speed


def hearts_overlap(h1: Heart, h2: Heart) -> bool:
    """Check if two hearts overlap (bounding box collision)."""
    # h1 bounds
    h1_left = int(h1.x) - h1.w // 2
    h1_right = h1_left + h1.w
    h1_top = int(h1.y)
    h1_bottom = h1_top + h1.h
    # h2 bounds
    h2_left = int(h2.x) - h2.w // 2
    h2_right = h2_left + h2.w
    h2_top = int(h2.y)
    h2_bottom = h2_top + h2.h
    # Check overlap
    return not (h1_right < h2_left or h1_left > h2_right or 
                h1_bottom < h2_top or h1_top > h2_bottom)


def get_size() -> Tuple[int, int]:
    size = shutil.get_terminal_size(fallback=(80, 24))
    # Reserve 2 lines for status/message
    return max(20, size.columns), max(10, size.lines)


def center_text(text: str, width: int) -> str:
    if len(text) >= width:
        return text[:width]
    pad = (width - len(text)) // 2
    return " " * pad + text


def draw_frame(hearts: List[Heart], msg: str | None) -> None:
    width, height = get_size()
    # Build a buffer of spaces
    buffer: List[List[str]] = [list(" " * width) for _ in range(height)]

    # Reserve top two lines for HUD
    hud_line = 0
    msg_line = 1

    # Place hearts into the buffer (clip to screen)
    for h in hearts:
        top = int(h.y)
        if top >= height:
            continue
        left = int(h.x) - h.w // 2
        # Twinkle style
        ansi_style = ""
        if h.twinkle_phase == 1:
            ansi_style = BOLD
        elif h.twinkle_phase == 2:
            ansi_style = FAINT

        for r in range(h.h):
            screen_r = top + r
            if screen_r < 2 or screen_r >= height:
                continue
            row_str = h.sprite[r]
            for c in range(h.w):
                ch = row_str[c]
                if ch == " ":
                    continue
                screen_c = left + c
                if 0 <= screen_c < width:
                    buffer[screen_r][screen_c] = f"{ansi_style}{h.color}{ch}{RESET}"

    # HUD top line
    title = "Relationship Module: Rain of Hearts"
    hud_text = f"\x1b[96m{title}{RESET}  |  Press Ctrl+C to exit"
    hud_text = hud_text if len(title) + 22 < width else "Press Ctrl+C to exit"
    hud_text = hud_text[:width]
    for i, ch in enumerate(hud_text):
        buffer[hud_line][i] = ch

    # Message line
    if msg:
        msg_colored = f"\x1b[95m{msg}{RESET}"
        centered = center_text(msg_colored, width)
        # Copy centered message into buffer
        for i, ch in enumerate(centered[:width]):
            buffer[msg_line][i] = ch

    # Blit to screen in one go
    out_lines: List[str] = ["".join(row) for row in buffer]
    sys.stdout.write(f"{CSI}H{CSI}2J")  # move cursor home + clear screen
    sys.stdout.write("\n".join(out_lines))
    sys.stdout.flush()


def main():
    random.seed()
    # Animation parameters (will ramp up after intro)
    target_spawn_chance_per_col = 0.03   # lower density for larger hearts
    spawn_chance_per_col = 0.0           # start at zero, ramp up
    ramp_duration = 10.0                 # seconds to reach target spawn chance

    # speed range (slower overall, feels calmer)
    base_min_speed, base_max_speed = 0.06, 0.35  # slower overall for gentle fall
    fps = 14
    frame_time = 1.0 / fps

    hearts: List[Heart] = []
    next_msg_time = 0.0
    current_msg: str | None = None
    msg_duration = 2.4

    # Enter alternate screen + hide cursor for a clean animation
    sys.stdout.write(ALT_SCREEN_ON + HIDE_CURSOR)
    sys.stdout.flush()
    try:
        # 1) Intro: show fun messages first with a tiny loading animation
        intro_start = time.perf_counter()
        intro_total = 7.0  # seconds
        msg_index = 0
        last = time.perf_counter()
        while True:
            now = time.perf_counter()
            if now - intro_start >= intro_total:
                break
            # dot loader
            dots = "." * int(((now - intro_start) * 3) % 4)
            intro_msg = MESSAGES[msg_index % len(MESSAGES)] + dots
            msg_index += 1 if (now - last) > 0.6 else 0
            last = now
            draw_frame([], intro_msg)
            time.sleep(frame_time)

        # 2) Main loop: slowly start falling hearts with twinkling
        anim_start = time.perf_counter()
        last = anim_start
        while True:
            now = time.perf_counter()
            # Maintain a steady-ish frame rate
            dt = max(0.0, now - last)
            last = now

            width, height = get_size()

            # Step hearts
            for h in hearts:
                # Use speed scaled by frame-time feel (not exact physics)
                h.y += h.speed
                # Twinkle: toggle style occasionally
                if now >= h.twinkle_next:
                    h.twinkle_phase = random.choice([0, 1, 2])
                    h.twinkle_next = now + random.uniform(0.15, 0.6)

            # Cull hearts off-screen
            hearts = [h for h in hearts if h.y < height]

            # Ramp up spawn chance smoothly from 0 to target over ramp_duration
            elapsed = now - anim_start
            if ramp_duration > 0:
                spawn_chance_per_col = min(target_spawn_chance_per_col,
                                           target_spawn_chance_per_col * (elapsed / ramp_duration))
            else:
                spawn_chance_per_col = target_spawn_chance_per_col

            # Spawn new hearts along the top row with some randomness (small + medium only)
            for col in range(width):
                if random.random() < spawn_chance_per_col:
                    # pick size and style
                    size_choice = random.choices(
                        population=["small", "medium"],
                        weights=[6, 4],  # favor small to reduce clutter
                        k=1,
                    )[0]
                    style_choice = random.choices(
                        population=["filled", "outline"],
                        weights=[6, 4],
                        k=1,
                    )[0]

                    # choose heart glyph from the provided pools
                    if size_choice == "small":
                        pool = HEARTS_SMALL if style_choice == "outline" else HEARTS_MED
                        ch = random.choice(pool)
                    else:  # medium
                        ch = random.choice(HEARTS_MED)

                    sprite = [ch]
                    hgt = 1
                    wid = len(ch)

                    # speeds by size
                    if size_choice == "small":
                        speed = random.uniform(base_min_speed, base_min_speed + 0.08)
                    else:  # medium
                        speed = random.uniform(base_min_speed + 0.06, base_min_speed + 0.22)

                    new_heart = Heart(
                        x=col,
                        y=2.0,  # start just below HUD
                        color=random.choice(PINKS),
                        speed=speed,
                        size=size_choice,
                        style=style_choice,
                        sprite=sprite,
                        w=wid,
                        h=hgt,
                        twinkle_phase=random.choice([0, 1, 2]),
                        twinkle_next=now + random.uniform(0.1, 0.7),
                    )

                    # Check for collision with existing hearts
                    collision = False
                    for existing in hearts:
                        if hearts_overlap(new_heart, existing):
                            collision = True
                            break

                    # Only add if no collision
                    if not collision:
                        hearts.append(new_heart)

            # Rotate message occasionally
            t = time.perf_counter()
            if t >= next_msg_time:
                current_msg = random.choice(MESSAGES)
                # Space next message slightly randomly
                next_msg_time = t + msg_duration + random.uniform(0.8, 2.2)

            draw_frame(hearts, current_msg)

            # Sleep for frame pacing
            sleep_left = frame_time - (time.perf_counter() - now)
            if sleep_left > 0:
                time.sleep(sleep_left)
    except KeyboardInterrupt:
        # Graceful exit
        sys.stdout.write(f"\n{CSI}2K\r\x1b[92mExiting love loop... See you next heartbeat! 💚{RESET}\n")
    finally:
        # Restore cursor and screen
        sys.stdout.write(SHOW_CURSOR + ALT_SCREEN_OFF)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
