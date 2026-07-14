"""
XIOPATH Phantom Infrastructure — Human Behavioral Simulator
=============================================================
Generates human-like interaction patterns for browser automation.
Each phantom gets a unique "behavioral DNA" to avoid cross-account
fingerprint correlation through behavioral biometrics.

Educational purpose only.
"""

import random
import math
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BehavioralProfile:
    """
    A unique behavioral fingerprint for a phantom identity.
    Generated deterministically from the phantom_id so the same phantom
    always behaves the same way (consistency matters for anti-detection).
    """
    phantom_id: str

    # Typing characteristics
    typing_mean_ms: float = 0.0        # Mean keystroke interval (ms)
    typing_stddev_ms: float = 0.0      # Std deviation of keystroke interval
    typing_error_rate: float = 0.0     # Probability of making a typo and correcting it
    typing_pause_rate: float = 0.0     # Probability of pausing mid-word (thinking)
    typing_pause_min_ms: float = 0.0   # Minimum thinking pause
    typing_pause_max_ms: float = 0.0   # Maximum thinking pause

    # Mouse characteristics
    mouse_speed: float = 0.0           # Base pixels per step
    mouse_curve_strength: float = 0.0  # How curved the Bézier paths are (0-1)
    mouse_overshoot_rate: float = 0.0  # Probability of overshooting the target
    mouse_jitter: float = 0.0          # Random micro-movement amplitude (pixels)

    # Scroll characteristics
    scroll_speed: float = 0.0          # Pixels per scroll event
    scroll_pause_rate: float = 0.0     # Probability of pausing while scrolling
    scroll_direction_variance: float = 0.0  # Occasional scroll-back probability

    # General interaction
    click_delay_min_ms: float = 0.0    # Minimum delay before clicking a found element
    click_delay_max_ms: float = 0.0    # Maximum delay before clicking
    field_focus_delay_ms: float = 0.0  # Delay after focusing a form field before typing
    tab_switch_rate: float = 0.0       # Probability of tabbing between fields vs clicking

    def __post_init__(self):
        """Generate deterministic behavioral parameters from phantom_id."""
        if self.typing_mean_ms == 0.0:
            self._generate_from_seed()

    def _generate_from_seed(self):
        """Use phantom_id as seed for reproducible behavioral DNA."""
        seed = int(hashlib.sha256(self.phantom_id.encode()).hexdigest(), 16)
        rng = random.Random(seed)

        # Typing: 80-250ms mean, 20-60ms stddev
        self.typing_mean_ms = rng.uniform(80, 250)
        self.typing_stddev_ms = rng.uniform(20, 60)
        self.typing_error_rate = rng.uniform(0.01, 0.05)
        self.typing_pause_rate = rng.uniform(0.02, 0.08)
        self.typing_pause_min_ms = rng.uniform(300, 800)
        self.typing_pause_max_ms = rng.uniform(1200, 3000)

        # Mouse: varied speeds and curvatures
        self.mouse_speed = rng.uniform(2.0, 8.0)
        self.mouse_curve_strength = rng.uniform(0.1, 0.6)
        self.mouse_overshoot_rate = rng.uniform(0.05, 0.15)
        self.mouse_jitter = rng.uniform(0.5, 3.0)

        # Scroll
        self.scroll_speed = rng.uniform(60, 200)
        self.scroll_pause_rate = rng.uniform(0.1, 0.3)
        self.scroll_direction_variance = rng.uniform(0.02, 0.08)

        # Interaction timing
        self.click_delay_min_ms = rng.uniform(100, 400)
        self.click_delay_max_ms = rng.uniform(500, 1500)
        self.field_focus_delay_ms = rng.uniform(200, 800)
        self.tab_switch_rate = rng.uniform(0.1, 0.4)


class HumanTyper:
    """
    Simulates human-like typing with realistic timing, occasional typos,
    and natural pauses. Each instance uses a BehavioralProfile for consistency.
    """

    def __init__(self, profile: BehavioralProfile):
        self.profile = profile
        self._rng = random.Random(
            int(hashlib.sha256(profile.phantom_id.encode()).hexdigest(), 16) + 1
        )

    def generate_keystrokes(self, text: str) -> list[dict]:
        """
        Generate a sequence of keystroke events with human-like timing.
        
        Args:
            text: The text to type
        
        Returns:
            List of dicts: [{"char": "H", "delay_ms": 120, "action": "press"}, ...]
            Actions: "press" (normal), "press_wrong" (typo), "backspace" (correct typo)
        """
        keystrokes = []
        p = self.profile

        for i, char in enumerate(text):
            # Thinking pause (between words or randomly)
            if char == " " or self._rng.random() < p.typing_pause_rate:
                if self._rng.random() < 0.3:  # Not every space gets a pause
                    pause_ms = self._rng.uniform(p.typing_pause_min_ms, p.typing_pause_max_ms)
                    keystrokes.append({"char": "", "delay_ms": pause_ms, "action": "pause"})

            # Occasional typo + correction
            if self._rng.random() < p.typing_error_rate and char.isalpha():
                # Type wrong key
                wrong_char = self._nearby_key(char)
                wrong_delay = max(30, self._rng.gauss(p.typing_mean_ms * 0.7, p.typing_stddev_ms))
                keystrokes.append({"char": wrong_char, "delay_ms": wrong_delay, "action": "press_wrong"})

                # Pause (notice the mistake)
                notice_delay = self._rng.uniform(100, 500)
                keystrokes.append({"char": "", "delay_ms": notice_delay, "action": "pause"})

                # Backspace
                keystrokes.append({"char": "", "delay_ms": self._rng.uniform(50, 150), "action": "backspace"})

            # Type the correct key
            delay = max(30, self._rng.gauss(p.typing_mean_ms, p.typing_stddev_ms))

            # Shift key adds slight delay for uppercase
            if char.isupper() or char in '!@#$%^&*()_+{}|:"<>?':
                delay += self._rng.uniform(20, 60)

            keystrokes.append({"char": char, "delay_ms": delay, "action": "press"})

        return keystrokes

    def _nearby_key(self, char: str) -> str:
        """Return a key near the given key on a QWERTY keyboard (simulates mispress)."""
        keyboard_neighbors = {
            'q': 'wa', 'w': 'qes', 'e': 'wrd', 'r': 'eft', 't': 'rgy',
            'y': 'thu', 'u': 'yji', 'i': 'uko', 'o': 'ilp', 'p': 'ok',
            'a': 'qsw', 's': 'awd', 'd': 'sef', 'f': 'drg', 'g': 'fth',
            'h': 'gyj', 'j': 'huk', 'k': 'jil', 'l': 'kop',
            'z': 'asx', 'x': 'zsc', 'c': 'xdv', 'v': 'cfb', 'b': 'vgn',
            'n': 'bhm', 'm': 'njk',
        }
        neighbors = keyboard_neighbors.get(char.lower(), char.lower())
        result = self._rng.choice(neighbors)
        return result.upper() if char.isupper() else result

    def calculate_total_time_ms(self, keystrokes: list[dict]) -> float:
        """Calculate total typing time for a keystroke sequence."""
        return sum(k["delay_ms"] for k in keystrokes)


class HumanMouse:
    """
    Simulates human-like mouse movement using Bézier curves with
    natural acceleration/deceleration, jitter, and occasional overshoots.
    """

    def __init__(self, profile: BehavioralProfile):
        self.profile = profile
        self._rng = random.Random(
            int(hashlib.sha256(profile.phantom_id.encode()).hexdigest(), 16) + 2
        )

    def generate_path(self, start_x: float, start_y: float,
                      end_x: float, end_y: float,
                      viewport_width: int = 1920,
                      viewport_height: int = 1080) -> list[dict]:
        """
        Generate a human-like mouse movement path from start to end.
        Uses cubic Bézier curves with natural speed variation.
        
        Returns:
            List of dicts: [{"x": 100, "y": 200, "delay_ms": 16}, ...]
        """
        p = self.profile
        distance = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)

        if distance < 1:
            return [{"x": end_x, "y": end_y, "delay_ms": 0}]

        # Generate Bézier control points
        # Control points deviate from the straight line to create a natural curve
        mid_x = (start_x + end_x) / 2
        mid_y = (start_y + end_y) / 2
        curve_offset = distance * p.mouse_curve_strength

        cp1_x = mid_x + self._rng.uniform(-curve_offset, curve_offset)
        cp1_y = mid_y + self._rng.uniform(-curve_offset, curve_offset)
        cp2_x = mid_x + self._rng.uniform(-curve_offset * 0.5, curve_offset * 0.5)
        cp2_y = mid_y + self._rng.uniform(-curve_offset * 0.5, curve_offset * 0.5)

        # Clamp control points to viewport
        cp1_x = max(0, min(viewport_width, cp1_x))
        cp1_y = max(0, min(viewport_height, cp1_y))
        cp2_x = max(0, min(viewport_width, cp2_x))
        cp2_y = max(0, min(viewport_height, cp2_y))

        # Calculate number of steps based on distance and speed
        num_steps = max(10, int(distance / p.mouse_speed))
        points = []

        for i in range(num_steps + 1):
            t = i / num_steps

            # Ease-in-out timing (slow start, fast middle, slow end)
            t_eased = self._ease_in_out(t)

            # Cubic Bézier interpolation
            x = (1 - t_eased) ** 3 * start_x + \
                3 * (1 - t_eased) ** 2 * t_eased * cp1_x + \
                3 * (1 - t_eased) * t_eased ** 2 * cp2_x + \
                t_eased ** 3 * end_x

            y = (1 - t_eased) ** 3 * start_y + \
                3 * (1 - t_eased) ** 2 * t_eased * cp1_y + \
                3 * (1 - t_eased) * t_eased ** 2 * cp2_y + \
                t_eased ** 3 * end_y

            # Add micro-jitter (human hands aren't perfectly steady)
            if 0 < i < num_steps:  # Don't jitter start/end
                x += self._rng.gauss(0, p.mouse_jitter)
                y += self._rng.gauss(0, p.mouse_jitter)

            # Frame delay (16ms ≈ 60fps, with variation)
            delay = self._rng.uniform(12, 22)

            points.append({
                "x": round(x, 1),
                "y": round(y, 1),
                "delay_ms": round(delay, 1)
            })

        # Handle overshoot
        if self._rng.random() < p.mouse_overshoot_rate:
            overshoot_dist = self._rng.uniform(5, 20)
            direction = math.atan2(end_y - start_y, end_x - start_x)
            overshoot_x = end_x + overshoot_dist * math.cos(direction)
            overshoot_y = end_y + overshoot_dist * math.sin(direction)

            points.append({"x": round(overshoot_x, 1), "y": round(overshoot_y, 1), "delay_ms": 20})
            # Correct back
            correction_path = self._linear_move(overshoot_x, overshoot_y, end_x, end_y, steps=5)
            points.extend(correction_path)

        return points

    def generate_click_sequence(self, x: float, y: float) -> list[dict]:
        """
        Generate a realistic click event with pre-click hover and post-click delay.
        
        Returns:
            List of events: [{"type": "move", ...}, {"type": "hover_pause"}, {"type": "click"}, ...]
        """
        p = self.profile

        events = []

        # Pre-click hover pause (human looks at element before clicking)
        hover_delay = self._rng.uniform(p.click_delay_min_ms, p.click_delay_max_ms)
        events.append({"type": "hover_pause", "delay_ms": hover_delay, "x": x, "y": y})

        # Click (mousedown + small delay + mouseup)
        hold_time = self._rng.uniform(50, 150)
        events.append({"type": "mousedown", "x": x, "y": y, "delay_ms": 0})
        events.append({"type": "mouseup", "x": x, "y": y, "delay_ms": hold_time})

        # Post-click pause (human waits to see result)
        post_delay = self._rng.uniform(200, 800)
        events.append({"type": "post_click_pause", "delay_ms": post_delay})

        return events

    def _ease_in_out(self, t: float) -> float:
        """Smooth ease-in-out curve (slow-fast-slow)."""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - (-2 * t + 2) ** 3 / 2

    def _linear_move(self, sx: float, sy: float, ex: float, ey: float,
                     steps: int = 5) -> list[dict]:
        """Simple linear interpolation (for overshoot correction)."""
        points = []
        for i in range(1, steps + 1):
            t = i / steps
            x = sx + (ex - sx) * t
            y = sy + (ey - sy) * t
            points.append({"x": round(x, 1), "y": round(y, 1), "delay_ms": 18})
        return points


class HumanScroller:
    """
    Simulates human-like scrolling with natural speed variation,
    pauses for reading, and occasional scroll-backs.
    """

    def __init__(self, profile: BehavioralProfile):
        self.profile = profile
        self._rng = random.Random(
            int(hashlib.sha256(profile.phantom_id.encode()).hexdigest(), 16) + 3
        )

    def generate_scroll_sequence(self, total_pixels: int,
                                  direction: str = "down") -> list[dict]:
        """
        Generate a human-like scroll sequence.
        
        Args:
            total_pixels: Total distance to scroll
            direction: "down" or "up"
        
        Returns:
            List of scroll events: [{"delta_y": 120, "delay_ms": 80}, ...]
        """
        p = self.profile
        events = []
        scrolled = 0
        multiplier = 1 if direction == "down" else -1

        while scrolled < total_pixels:
            # Normal scroll step
            step = self._rng.gauss(p.scroll_speed, p.scroll_speed * 0.3)
            step = max(40, min(400, step))  # Clamp

            # Reading pause
            if self._rng.random() < p.scroll_pause_rate:
                pause = self._rng.uniform(500, 3000)
                events.append({"delta_y": 0, "delay_ms": pause, "action": "reading_pause"})

            # Occasional scroll-back
            if self._rng.random() < p.scroll_direction_variance and scrolled > 100:
                back_amount = self._rng.uniform(50, 150)
                events.append({
                    "delta_y": round(-multiplier * back_amount),
                    "delay_ms": self._rng.uniform(30, 80),
                    "action": "scroll_back"
                })
                scrolled -= back_amount * 0.3  # Partial credit for scroll-back

            # Main scroll event
            delay = self._rng.uniform(30, 120)
            events.append({
                "delta_y": round(multiplier * step),
                "delay_ms": round(delay),
                "action": "scroll"
            })
            scrolled += step

        return events


class HumanInteraction:
    """
    High-level human interaction simulator that combines typing, mouse,
    and scrolling behaviors for common web automation tasks.
    """

    def __init__(self, phantom_id: str):
        """
        Initialize with a phantom ID. The behavioral profile is generated
        deterministically from the ID for consistency across sessions.
        """
        self.profile = BehavioralProfile(phantom_id=phantom_id)
        self.typer = HumanTyper(self.profile)
        self.mouse = HumanMouse(self.profile)
        self.scroller = HumanScroller(self.profile)

    def plan_form_fill(self, fields: list[dict]) -> list[dict]:
        """
        Plan a complete form-filling interaction.
        
        Args:
            fields: List of dicts [{"selector": "#email", "value": "user@gmail.com", "x": 500, "y": 300}, ...]
        
        Returns:
            Complete interaction plan with mouse movements, clicks, typing, and delays
        """
        plan = []
        current_x, current_y = 0, 0
        p = self.profile

        for i, f in enumerate(fields):
            target_x = f.get("x", 500)
            target_y = f.get("y", 300 + i * 60)

            # Decide: click or tab to next field
            use_tab = (i > 0 and self._rng().random() < p.tab_switch_rate)

            if use_tab:
                plan.append({
                    "action": "key_press",
                    "key": "Tab",
                    "delay_ms": self._rng().uniform(100, 300)
                })
            else:
                # Mouse movement to field
                mouse_path = self.mouse.generate_path(current_x, current_y, target_x, target_y)
                plan.append({"action": "mouse_move", "path": mouse_path})

                # Click on field
                click_events = self.mouse.generate_click_sequence(target_x, target_y)
                plan.append({"action": "click", "events": click_events})

                current_x, current_y = target_x, target_y

            # Pause after focusing field
            plan.append({
                "action": "focus_pause",
                "delay_ms": self._rng().uniform(p.field_focus_delay_ms * 0.5, p.field_focus_delay_ms * 1.5)
            })

            # Type the value
            keystrokes = self.typer.generate_keystrokes(f["value"])
            plan.append({
                "action": "type",
                "selector": f["selector"],
                "keystrokes": keystrokes,
                "total_ms": self.typer.calculate_total_time_ms(keystrokes)
            })

        return plan

    def plan_page_read(self, page_height: int, viewport_height: int = 1080) -> list[dict]:
        """
        Simulate reading a page — scroll down with natural pauses.
        Used during profile aging to create organic browsing patterns.
        """
        total_scroll = max(0, page_height - viewport_height)
        if total_scroll <= 0:
            return [{"action": "reading_pause", "delay_ms": random.uniform(2000, 5000)}]

        scroll_events = self.scroller.generate_scroll_sequence(total_scroll)
        return [{"action": "scroll_sequence", "events": scroll_events}]

    def _rng(self) -> random.Random:
        """Get the profile's seeded RNG."""
        return random.Random(
            int(hashlib.sha256(self.profile.phantom_id.encode()).hexdigest(), 16) + 99
        )
