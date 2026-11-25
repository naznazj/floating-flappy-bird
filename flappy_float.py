"""Floating Flappy Bird for Windows with Auto-Pilot, Adjustments, Unlimited Score, and Resizing."""

from __future__ import annotations

import math
import random
import time
import tkinter as tk
from dataclasses import dataclass, field


# Default window & playfield dimensions
DEFAULT_WIDTH = 460
DEFAULT_HEIGHT = 580
MIN_WIDTH = 320
MAX_WIDTH = 1920
MIN_HEIGHT = 260
MAX_HEIGHT = 1200

HUD_HEIGHT = 44
PLAY_TOP = HUD_HEIGHT + 6

# Transparent chroma-key color (Windows tkinter -transparentcolor)
TRANSPARENT_KEY = "#010203"

# Default physics constants (units: pixels, seconds)
FIXED_DT = 1.0 / 60.0
DEFAULT_GRAVITY = 1350.0
FLAP_VELOCITY = -410.0
MAX_FALL_SPEED = 560.0

BIRD_X = 115.0
BIRD_RADIUS = 15.0

PIPE_WIDTH = 62.0
DEFAULT_PIPE_GAP = 148.0
DEFAULT_PIPE_SPEED = 165.0
DEFAULT_WIN_SCORE = 20
PIPE_SPACING_PX = 272.0  # horizontal distance between pipes


@dataclass
class Pipe:
    x: float
    gap_y: float
    gap_height: float = DEFAULT_PIPE_GAP
    passed: bool = False

    @property
    def top_bottom(self) -> float:
        return self.gap_y - self.gap_height / 2.0

    @property
    def bottom_top(self) -> float:
        return self.gap_y + self.gap_height / 2.0


@dataclass
class Confetti:
    x: float
    y: float
    vx: float
    vy: float
    color: str
    size: float


@dataclass
class BonusStar:
    x: float
    y: float
    collected: bool = False


@dataclass
class TrailPoint:
    x: float
    y: float
    color: str
    radius: float


def get_evolution_tier(score: int) -> tuple[str, str, str, str]:
    """Return (tier_name, body_color, belly_color, trail_color) for a score."""
    if score >= 50:
        return ("COSMIC", "#C084FC", "#F5D0FE", "#E879F9")
    if score >= 25:
        return ("PHOENIX", "#FB7185", "#FECDD3", "#F97316")
    if score >= 10:
        return ("CYBER", "#38BDF8", "#BAE6FD", "#22D3EE")
    return ("CLASSIC", "#FACC15", "#FEF08A", "#FDE047")


@dataclass
class GameState:
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    bird_y: float = (PLAY_TOP + (DEFAULT_HEIGHT - 14)) / 2.0
    bird_vy: float = 0.0
    pipes: list[Pipe] = field(default_factory=list)
    score: int = 0
    best_score: int = 0

    # Adjustable settings
    auto_pilot: bool = True
    unlimited_score: bool = False
    win_score: int = DEFAULT_WIN_SCORE
    pipe_speed: float = DEFAULT_PIPE_SPEED
    pipe_gap: float = DEFAULT_PIPE_GAP
    gravity: float = DEFAULT_GRAVITY

    game_over: bool = False
    won: bool = False
    endless_after_win: bool = False
    spawn_timer: float = 0.25
    elapsed: float = 0.0
    wing_phase: float = 0.0
    confetti: list[Confetti] = field(default_factory=list)
    stars: list[BonusStar] = field(default_factory=list)
    trail: list[TrailPoint] = field(default_factory=list)
    pipes_spawned: int = 0
    floating_popups: list[tuple[float, float, str, float]] = field(default_factory=list)

    @property
    def play_top(self) -> float:
        return float(PLAY_TOP)

    @property
    def play_bottom(self) -> float:
        return float(self.height - 14)

    def reset(self, keep_settings: bool = True) -> None:
        if keep_settings:
            fresh = GameState(
                width=self.width,
                height=self.height,
                bird_y=(PLAY_TOP + (self.height - 14)) / 2.0,
                auto_pilot=self.auto_pilot,
                unlimited_score=self.unlimited_score,
                win_score=self.win_score,
                pipe_speed=self.pipe_speed,
                pipe_gap=self.pipe_gap,
                gravity=self.gravity,
                best_score=self.best_score,
            )
        else:
            fresh = GameState(best_score=self.best_score)
        self.__dict__.update(fresh.__dict__)


def compute_autopilot_flap(state: GameState) -> bool:
    """Decide whether the bird should flap on this physics tick.

    Uses live `state.gravity`, `state.pipe_speed`, `state.pipe_gap`, and
    playfield bounds so the autopilot adapts to any size or physics setting.
    """
    if state.game_over or (state.won and not state.endless_after_win):
        return False

    next_pipe: Pipe | None = None
    after_pipe: Pipe | None = None
    for i, p in enumerate(state.pipes):
        if p.x + PIPE_WIDTH > BIRD_X - (BIRD_RADIUS - 2.0):
            next_pipe = p
            if i + 1 < len(state.pipes):
                after_pipe = state.pipes[i + 1]
            break

    flap_rise = (FLAP_VELOCITY * FLAP_VELOCITY) / (2.0 * max(state.gravity, 200.0))

    if next_pipe is not None:
        target_y = next_pipe.gap_y + min(10.0, flap_rise * 0.15)
        upper_limit = next_pipe.top_bottom + 6.0
        lower_limit = next_pipe.bottom_top - 6.0
        # When exiting current pipe, pre-align toward the following pipe within safe bounds
        if after_pipe is not None and next_pipe.x + PIPE_WIDTH * 0.6 < BIRD_X:
            safe_min = upper_limit + BIRD_RADIUS + 4.0
            safe_max = lower_limit - BIRD_RADIUS - 4.0
            if safe_min <= safe_max:
                target_y = max(safe_min, min(safe_max, after_pipe.gap_y + min(10.0, flap_rise * 0.15)))
    else:
        target_y = (state.play_top + state.play_bottom) / 2.0
        upper_limit = state.play_top + 12.0
        lower_limit = state.play_bottom - 12.0

    upper_limit = max(upper_limit, state.play_top + 6.0)
    lower_limit = min(lower_limit, state.play_bottom - 6.0)

    predicted_apex_top = (state.bird_y - flap_rise) - BIRD_RADIUS

    dt_guard = 0.06
    projected_bottom = (
        state.bird_y
        + BIRD_RADIUS
        + state.bird_vy * dt_guard
        + 0.5 * state.gravity * dt_guard * dt_guard
    )
    if projected_bottom >= lower_limit:
        return True

    if predicted_apex_top < upper_limit:
        return False

    lookahead_y = state.bird_y + state.bird_vy * 0.045
    if lookahead_y > target_y:
        return True

    return False


def step_physics(state: GameState, dt: float, rng: random.Random | None = None) -> None:
    """Advance the game simulation by `dt` seconds."""
    if rng is None:
        rng = random.Random()

    state.elapsed += dt
    state.wing_phase += dt * (14.0 if state.bird_vy < 0 else 7.0)

    for c in state.confetti:
        c.x += c.vx * dt
        c.y += c.vy * dt
        c.vy += 280.0 * dt
    state.confetti = [c for c in state.confetti if c.y < state.height + 20]

    # Fade & drift trail + popups
    for tp in state.trail:
        tp.x -= state.pipe_speed * dt
        tp.radius = max(0.0, tp.radius - 14.0 * dt)
    state.trail = [tp for tp in state.trail if tp.radius > 1.2 and tp.x > -20]

    state.floating_popups = [
        (px, py - 45.0 * dt, txt, ttl - dt)
        for px, py, txt, ttl in state.floating_popups
        if ttl - dt > 0.0
    ]

    if state.game_over or (state.won and not state.endless_after_win):
        return

    _, _, _, trail_color = get_evolution_tier(state.score)
    if not state.trail or abs(state.trail[-1].x - BIRD_X) > 6.0:
        state.trail.append(TrailPoint(x=BIRD_X - 8.0, y=state.bird_y, color=trail_color, radius=9.0))

    if state.auto_pilot and compute_autopilot_flap(state):
        state.bird_vy = FLAP_VELOCITY

    state.bird_vy = min(state.bird_vy + state.gravity * dt, MAX_FALL_SPEED)
    state.bird_y += state.bird_vy * dt

    if state.bird_y - BIRD_RADIUS < state.play_top:
        state.bird_y = state.play_top + BIRD_RADIUS
        state.bird_vy = 0.0
    if state.bird_y + BIRD_RADIUS >= state.play_bottom:
        state.bird_y = state.play_bottom - BIRD_RADIUS
        state.game_over = True
        state.best_score = max(state.best_score, state.score)
        return

    state.spawn_timer -= dt
    if state.spawn_timer <= 0.0:
        state.spawn_timer = PIPE_SPACING_PX / max(state.pipe_speed, 60.0)
        gap = state.pipe_gap
        min_gap_y = state.play_top + gap / 2.0 + 32.0
        max_gap_y = state.play_bottom - gap / 2.0 - 32.0
        if min_gap_y > max_gap_y:
            gap_y = (state.play_top + state.play_bottom) / 2.0
        else:
            gap_y = rng.uniform(min_gap_y, max_gap_y)
        state.pipes.append(Pipe(x=float(state.width + 10), gap_y=gap_y, gap_height=gap))
        state.pipes_spawned += 1
        if state.pipes_spawned % 3 == 0:
            star_y = gap_y + rng.uniform(-gap * 0.18, gap * 0.18)
            state.stars.append(BonusStar(x=float(state.width + 10 + PIPE_WIDTH / 2.0), y=star_y))

    for star in state.stars:
        star.x -= state.pipe_speed * dt
        if not star.collected:
            dx = BIRD_X - star.x
            dy = state.bird_y - star.y
            if dx * dx + dy * dy <= (BIRD_RADIUS + 14.0) ** 2:
                star.collected = True
                state.score += 3
                state.best_score = max(state.best_score, state.score)
                state.floating_popups.append((star.x, star.y - 12.0, "+3 ★", 0.9))
                if not state.unlimited_score and not state.won and state.score >= state.win_score:
                    state.won = True
                    _spawn_confetti(state, rng)
    state.stars = [s for s in state.stars if not s.collected and s.x > -30.0]

    for pipe in state.pipes:
        pipe.x -= state.pipe_speed * dt

        if not pipe.passed and pipe.x + PIPE_WIDTH < BIRD_X - BIRD_RADIUS:
            pipe.passed = True
            state.score += 1
            state.best_score = max(state.best_score, state.score)
            if not state.unlimited_score and not state.won and state.score >= state.win_score:
                state.won = True
                _spawn_confetti(state, rng)

        if _circle_hits_pipe(BIRD_X, state.bird_y, BIRD_RADIUS - 2.0, pipe):
            state.game_over = True
            state.best_score = max(state.best_score, state.score)
            return

    state.pipes = [p for p in state.pipes if p.x + PIPE_WIDTH > -30.0]


def _circle_hits_pipe(cx: float, cy: float, r: float, pipe: Pipe) -> bool:
    if cx + r <= pipe.x or cx - r >= pipe.x + PIPE_WIDTH:
        return False
    if cy - r < pipe.top_bottom or cy + r > pipe.bottom_top:
        return True
    return False


def _spawn_confetti(state: GameState, rng: random.Random) -> None:
    colors = ["#FFD93D", "#6BCB77", "#4D96FF", "#FF6B6B", "#C77DFF", "#FFFFFF"]
    for _ in range(55):
        state.confetti.append(
            Confetti(
                x=rng.uniform(40, max(60, state.width - 40)),
                y=rng.uniform(state.play_top + 10, state.play_top + 120),
                vx=rng.uniform(-160, 160),
                vy=rng.uniform(-240, -40),
                color=rng.choice(colors),
                size=rng.uniform(5, 9),
            )
        )


class FloatingFlappyApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Floating Flappy Bird")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_KEY)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass

        self.state = GameState()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x0 = max(40, (sw - self.state.width) // 2)
        y0 = max(40, (sh - self.state.height) // 2)
        self.root.geometry(f"{self.state.width}x{self.state.height}+{x0}+{y0}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.state.width,
            height=self.state.height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.rng = random.Random()
        self._last_time = time.perf_counter()
        self._accumulator = 0.0
        self._drag_offset = (0, 0)
        self._dragging = False
        self._resize_mode = ""
        self._resize_start = (0, 0, self.root.winfo_x(), self.root.winfo_y(), self.state.width, self.state.height)
        self._show_bounds = True
        self._show_settings = False
        self._buttons: list[tuple[int, int, int, int, callable]] = []

        # Keyboard bindings
        self.root.bind("<space>", self._on_flap)
        self.root.bind("<Up>", self._on_flap)
        self.root.bind("<KeyPress-a>", lambda _e: self.toggle_autopilot())
        self.root.bind("<KeyPress-A>", lambda _e: self.toggle_autopilot())
        self.root.bind("<KeyPress-u>", lambda _e: self.toggle_unlimited())
        self.root.bind("<KeyPress-U>", lambda _e: self.toggle_unlimited())
        self.root.bind("<KeyPress-s>", lambda _e: self.toggle_settings())
        self.root.bind("<KeyPress-S>", lambda _e: self.toggle_settings())
        self.root.bind("<KeyPress-r>", lambda _e: self.reset_game())
        self.root.bind("<KeyPress-R>", lambda _e: self.reset_game())
        self.root.bind("<KeyPress-b>", lambda _e: self.toggle_bounds())
        self.root.bind("<KeyPress-B>", lambda _e: self.toggle_bounds())
        self.root.bind("<Escape>", lambda _e: self.root.destroy())

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<ButtonPress-3>", lambda _e: self.toggle_autopilot())

        self._tick()

    def _apply_size(self, new_w: int, new_h: int, new_x: int | None = None, new_y: int | None = None) -> None:
        max_w = min(MAX_WIDTH, self.root.winfo_screenwidth())
        max_h = min(MAX_HEIGHT, self.root.winfo_screenheight())
        w = max(MIN_WIDTH, min(max_w, int(new_w)))
        h = max(MIN_HEIGHT, min(max_h, int(new_h)))
        x = self.root.winfo_x() if new_x is None else int(new_x)
        y = self.root.winfo_y() if new_y is None else int(new_y)
        self.state.width = w
        self.state.height = h
        self.state.bird_y = max(
            self.state.play_top + BIRD_RADIUS,
            min(self.state.play_bottom - BIRD_RADIUS, self.state.bird_y),
        )
        self.canvas.config(width=w, height=h)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def toggle_autopilot(self) -> None:
        self.state.auto_pilot = not self.state.auto_pilot

    def toggle_unlimited(self) -> None:
        self.state.unlimited_score = not self.state.unlimited_score
        if self.state.unlimited_score and self.state.won:
            self.state.endless_after_win = True

    def toggle_settings(self) -> None:
        self._show_settings = not self._show_settings

    def toggle_bounds(self) -> None:
        self._show_bounds = not self._show_bounds

    def reset_game(self) -> None:
        self.state.reset(keep_settings=True)

    def reset_defaults(self) -> None:
        self.state.pipe_speed = DEFAULT_PIPE_SPEED
        self.state.pipe_gap = DEFAULT_PIPE_GAP
        self.state.gravity = DEFAULT_GRAVITY
        self.state.win_score = DEFAULT_WIN_SCORE
        self.state.unlimited_score = False
        self.state.auto_pilot = True
        self._apply_size(DEFAULT_WIDTH, DEFAULT_HEIGHT)

    def continue_endless(self) -> None:
        if self.state.won:
            self.state.endless_after_win = True

    def _adjust_win_score(self, delta: int) -> None:
        self.state.win_score = max(5, min(500, self.state.win_score + delta))

    def _adjust_speed(self, delta: float) -> None:
        self.state.pipe_speed = max(90.0, min(320.0, self.state.pipe_speed + delta))

    def _adjust_gap(self, delta: float) -> None:
        self.state.pipe_gap = max(105.0, min(220.0, self.state.pipe_gap + delta))

    def _adjust_gravity(self, delta: float) -> None:
        self.state.gravity = max(850.0, min(1950.0, self.state.gravity + delta))

    def _adjust_window_size(self, dw: int, dh: int) -> None:
        self._apply_size(self.state.width + dw, self.state.height + dh)

    def _get_resize_mode(self, x: int, y: int) -> str:
        w, h = self.state.width, self.state.height
        edge = 10
        corner = 18
        on_l = x <= edge
        on_r = x >= w - edge
        on_t = y <= edge
        on_b = y >= h - edge
        if x <= corner and y <= corner:
            return "nw"
        if x >= w - corner and y <= corner:
            return "ne"
        if x <= corner and y >= h - corner:
            return "sw"
        if x >= w - corner and y >= h - corner:
            return "se"
        if on_l:
            return "w"
        if on_r:
            return "e"
        if on_t:
            return "n"
        if on_b:
            return "s"
        return ""

    def _cursor_for_mode(self, mode: str) -> str:
        return {
            "nw": "size_nw_se",
            "se": "size_nw_se",
            "ne": "size_ne_sw",
            "sw": "size_ne_sw",
            "n": "size_ns",
            "s": "size_ns",
            "e": "size_we",
            "w": "size_we",
        }.get(mode, "")

    def _on_flap(self, _event: tk.Event) -> None:
        if self.state.game_over:
            self.reset_game()
            return
        if self.state.won and not self.state.endless_after_win:
            self.continue_endless()
            return
        if not self.state.auto_pilot:
            self.state.bird_vy = FLAP_VELOCITY

    def _on_mouse_move(self, event: tk.Event) -> None:
        mode = self._get_resize_mode(event.x, event.y)
        self.canvas.config(cursor=self._cursor_for_mode(mode))

    def _on_mouse_down(self, event: tk.Event) -> None:
        x, y = event.x, event.y

        mode = self._get_resize_mode(x, y)
        if mode:
            self._resize_mode = mode
            self._resize_start = (
                event.x_root,
                event.y_root,
                self.root.winfo_x(),
                self.root.winfo_y(),
                self.state.width,
                self.state.height,
            )
            return

        for x1, y1, x2, y2, action in reversed(self._buttons):
            if x1 <= x <= x2 and y1 <= y <= y2:
                action()
                return

        if 0 <= y <= HUD_HEIGHT:
            self._dragging = True
            self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
            return

        if self.state.game_over:
            self.reset_game()
            return

        if not self.state.auto_pilot:
            self.state.bird_vy = FLAP_VELOCITY
        else:
            self._dragging = True
            self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if self._resize_mode:
            mx0, my0, wx0, wy0, sw, sh = self._resize_start
            dx = event.x_root - mx0
            dy = event.y_root - my0
            nw, nh, nx, ny = sw, sh, wx0, wy0

            if "e" in self._resize_mode:
                nw = sw + dx
            if "s" in self._resize_mode:
                nh = sh + dy
            if "w" in self._resize_mode:
                clamped_w = max(MIN_WIDTH, min(self.root.winfo_screenwidth(), sw - dx))
                nx = wx0 + (sw - clamped_w)
                nw = clamped_w
            if "n" in self._resize_mode:
                clamped_h = max(MIN_HEIGHT, min(self.root.winfo_screenheight(), sh - dy))
                ny = wy0 + (sh - clamped_h)
                nh = clamped_h

            self._apply_size(nw, nh, nx, ny)
        elif self._dragging:
            nx = event.x_root - self._drag_offset[0]
            ny = event.y_root - self._drag_offset[1]
            self.root.geometry(f"+{nx}+{ny}")

    def _on_mouse_up(self, _event: tk.Event) -> None:
        self._dragging = False
        self._resize_mode = ""

    def _tick(self) -> None:
        now = time.perf_counter()
        frame_dt = min(now - self._last_time, 0.05)
        self._last_time = now
        self._accumulator += frame_dt

        while self._accumulator >= FIXED_DT:
            step_physics(self.state, FIXED_DT, self.rng)
            self._accumulator -= FIXED_DT

        self._render()
        self.root.after(16, self._tick)

    def _reg_btn(self, x1: int, y1: int, x2: int, y2: int, action: callable) -> None:
        self._buttons.append((x1, y1, x2, y2, action))

    def _render(self) -> None:
        c = self.canvas
        c.delete("all")
        self._buttons.clear()

        w = self.state.width
        pt = self.state.play_top
        pb = self.state.play_bottom

        if self._show_bounds:
            # Solid 4px border around the entire window so all 4 edges are easy to grab with the mouse
            c.create_rectangle(
                2, 2, w - 2, self.state.height - 2,
                outline="#38BDF8", width=4,
            )

        for p in self.state.pipes:
            self._draw_pipe(p)

        # Draw collectible Bonus Stars (★ +3)
        for star in self.state.stars:
            self._draw_star(star.x, star.y)

        # Draw glowing motion trail behind the bird
        for tp in self.state.trail:
            r = tp.radius
            c.create_oval(
                tp.x - r, tp.y - r, tp.x + r, tp.y + r,
                fill=tp.color, outline="",
            )

        if self.state.auto_pilot and not self.state.game_over:
            for p in self.state.pipes:
                if p.x + PIPE_WIDTH > BIRD_X - (BIRD_RADIUS - 2.0):
                    tx = p.x + PIPE_WIDTH / 2.0
                    ty = p.gap_y + 8.0
                    c.create_line(
                        BIRD_X + BIRD_RADIUS, self.state.bird_y, tx, ty,
                        fill="#38BDF8", width=2, dash=(4, 4),
                    )
                    c.create_oval(tx - 5, ty - 5, tx + 5, ty + 5, fill="#38BDF8", outline="#FFFFFF", width=1.5)
                    break

        self._draw_bird()

        for px, py, txt, _ttl in self.state.floating_popups:
            c.create_text(px, py, text=txt, fill="#FACC15", font=("Segoe UI", 12, "bold"))

        for cf in self.state.confetti:
            c.create_rectangle(
                cf.x, cf.y, cf.x + cf.size, cf.y + cf.size,
                fill=cf.color, outline="",
            )

        self._draw_resize_grip(w, pb)
        self._draw_hud()

        if self._show_settings:
            self._draw_settings_panel()
        elif self.state.won and not self.state.endless_after_win:
            self._draw_win_banner()
        elif self.state.game_over:
            self._draw_gameover_banner()

    def _draw_resize_grip(self, w: int, pb: float) -> None:
        c = self.canvas
        c.create_polygon(
            w - 20, pb,
            w - 2, pb,
            w - 2, pb - 18,
            fill="#0F172A", outline="#38BDF8", width=1.5,
        )
        c.create_line(w - 13, pb - 3, w - 5, pb - 11, fill="#7DD3FC", width=1.5)
        c.create_line(w - 8, pb - 3, w - 5, pb - 6, fill="#7DD3FC", width=1.5)

    def _draw_pipe(self, p: Pipe) -> None:
        c = self.canvas
        x1, x2 = p.x, p.x + PIPE_WIDTH
        pt = self.state.play_top
        pb = self.state.play_bottom
        lip_h = 22.0
        lip_pad = 5.0

        if p.top_bottom > pt:
            c.create_rectangle(
                x1, pt, x2, p.top_bottom - lip_h,
                fill="#22C55E", outline="#14532D", width=2,
            )
            c.create_rectangle(
                x1 + 6, pt, x1 + 14, max(pt, p.top_bottom - lip_h),
                fill="#86EFAC", outline="",
            )
            c.create_rectangle(
                x1 - lip_pad, max(pt, p.top_bottom - lip_h), x2 + lip_pad, p.top_bottom,
                fill="#4ADE80", outline="#14532D", width=2,
            )

        if p.bottom_top < pb:
            c.create_rectangle(
                x1, p.bottom_top + lip_h, x2, pb,
                fill="#22C55E", outline="#14532D", width=2,
            )
            c.create_rectangle(
                x1 + 6, min(pb, p.bottom_top + lip_h), x1 + 14, pb,
                fill="#86EFAC", outline="",
            )
            c.create_rectangle(
                x1 - lip_pad, p.bottom_top, x2 + lip_pad, min(pb, p.bottom_top + lip_h),
                fill="#4ADE80", outline="#14532D", width=2,
            )

    def _draw_star(self, sx: float, sy: float) -> None:
        c = self.canvas
        pulse = 1.0 + 0.15 * math.sin(self.state.elapsed * 8.0)
        r_outer = 12.0 * pulse
        r_inner = 5.2 * pulse
        pts: list[float] = []
        for i in range(10):
            angle = -math.pi / 2.0 + i * math.pi / 5.0
            rad = r_outer if i % 2 == 0 else r_inner
            pts.extend([sx + math.cos(angle) * rad, sy + math.sin(angle) * rad])
        c.create_polygon(pts, fill="#FACC15", outline="#FFFFFF", width=1.5)

    def _draw_bird(self) -> None:
        c = self.canvas
        bx, by = BIRD_X, self.state.bird_y
        r = BIRD_RADIUS
        _tier, body_color, belly_color, _trail = get_evolution_tier(self.state.score)

        c.create_oval(
            bx - r, by - r + 1, bx + r, by + r - 1,
            fill=body_color, outline="#713F12", width=2,
        )
        c.create_oval(
            bx - r + 4, by + 1, bx + r - 6, by + r - 3,
            fill=belly_color, outline="",
        )
        wing_dy = math.sin(self.state.wing_phase) * 4.5
        c.create_oval(
            bx - 10, by - 2 + wing_dy, bx + 2, by + 7 + wing_dy,
            fill="#FFFFFF", outline="#713F12", width=1.5,
        )
        c.create_oval(bx + 3, by - 9, bx + 12, by, fill="#FFFFFF", outline="#713F12", width=1.5)
        c.create_oval(bx + 7, by - 6, bx + 11, by - 2, fill="#0F172A", outline="")
        c.create_polygon(
            bx + r - 2, by - 2,
            bx + r + 10, by + 2,
            bx + r - 2, by + 6,
            fill="#F97316", outline="#7C2D12", width=1.5,
        )

    def _draw_hud(self) -> None:
        c = self.canvas
        w = self.state.width
        c.create_rectangle(4, 4, w - 4, HUD_HEIGHT, fill="#0F172A", outline="#334155", width=2)

        if self.state.unlimited_score or self.state.endless_after_win:
            score_txt = f"SCORE {self.state.score} ∞"
        else:
            score_txt = f"SCORE {self.state.score}/{self.state.win_score}"
        c.create_text(64, 24, text=score_txt, fill="#F8FAFC", font=("Segoe UI", 10, "bold"))

        # Auto-Pilot toggle
        ap_bg = "#0284C7" if self.state.auto_pilot else "#334155"
        ap_txt = "AUTO: ON" if self.state.auto_pilot else "AUTO: OFF"
        c.create_rectangle(124, 9, 206, 37, fill=ap_bg, outline="#7DD3FC" if self.state.auto_pilot else "#64748B", width=1.5)
        c.create_text(165, 23, text=ap_txt, fill="#FFFFFF", font=("Segoe UI", 8, "bold"))
        self._reg_btn(124, 9, 206, 37, self.toggle_autopilot)

        # Unlimited Score toggle
        unli_on = self.state.unlimited_score
        unli_bg = "#7C3AED" if unli_on else "#334155"
        unli_txt = "∞ UNLI" if unli_on else "GOAL"
        c.create_rectangle(212, 9, 276, 37, fill=unli_bg, outline="#C4B5FD" if unli_on else "#64748B", width=1.5)
        c.create_text(244, 23, text=unli_txt, fill="#FFFFFF", font=("Segoe UI", 8, "bold"))
        self._reg_btn(212, 9, 276, 37, self.toggle_unlimited)

        # Settings toggle [⚙]
        set_bg = "#0F766E" if self._show_settings else "#1E293B"
        c.create_rectangle(w - 110, 9, w - 80, 37, fill=set_bg, outline="#5EEAD4" if self._show_settings else "#475569", width=1.5)
        c.create_text(w - 95, 23, text="⚙", fill="#E2E8F0", font=("Segoe UI", 11, "bold"))
        self._reg_btn(w - 110, 9, w - 80, 37, self.toggle_settings)

        # Reset [↻]
        c.create_rectangle(w - 74, 9, w - 44, 37, fill="#1E293B", outline="#475569", width=1.5)
        c.create_text(w - 59, 23, text="↻", fill="#E2E8F0", font=("Segoe UI", 12, "bold"))
        self._reg_btn(w - 74, 9, w - 44, 37, self.reset_game)

        # Close [×]
        c.create_rectangle(w - 38, 9, w - 8, 37, fill="#991B1B", outline="#EF4444", width=1.5)
        c.create_text(w - 23, 23, text="×", fill="#FFFFFF", font=("Segoe UI", 12, "bold"))
        self._reg_btn(w - 38, 9, w - 8, 37, self.root.destroy)

    def _draw_settings_panel(self) -> None:
        c = self.canvas
        panel_w = min(376, self.state.width - 28)
        px1 = (self.state.width - panel_w) // 2
        px2 = px1 + panel_w
        py1 = int(self.state.play_top) + 12
        py2 = py1 + 368
        c.create_rectangle(px1, py1, px2, py2, fill="#0F172A", outline="#38BDF8", width=2)
        c.create_text((px1 + px2) // 2, py1 + 20, text="ADJUSTMENTS", fill="#38BDF8", font=("Segoe UI", 11, "bold"))

        rows = [
            ("Autoplay (A)", "ON" if self.state.auto_pilot else "OFF", self.toggle_autopilot, None),
            ("Unli Score (U)", "∞ ON" if self.state.unlimited_score else "OFF", self.toggle_unlimited, None),
            ("Win Goal", "∞" if self.state.unlimited_score else f"{self.state.win_score}", lambda: self._adjust_win_score(-5), lambda: self._adjust_win_score(5)),
            ("Pipe Speed", f"{int(self.state.pipe_speed)}", lambda: self._adjust_speed(-15), lambda: self._adjust_speed(15)),
            ("Gap Size", f"{int(self.state.pipe_gap)}", lambda: self._adjust_gap(-10), lambda: self._adjust_gap(10)),
            ("Gravity", f"{int(self.state.gravity)}", lambda: self._adjust_gravity(-100), lambda: self._adjust_gravity(100)),
            ("Window Size", f"{self.state.width}×{self.state.height}", lambda: self._adjust_window_size(-60, -60), lambda: self._adjust_window_size(60, 60)),
            ("Frame (B)", "SHOW" if self._show_bounds else "HIDE", self.toggle_bounds, None),
        ]

        y = py1 + 48
        for label, val, act_left, act_right in rows:
            c.create_text(px1 + 16, y, anchor="w", text=label, fill="#E2E8F0", font=("Segoe UI", 9, "bold"))
            if act_right is None:
                is_on = val in ("ON", "∞ ON", "SHOW")
                bg = "#0284C7" if is_on else "#334155"
                c.create_rectangle(px2 - 104, y - 12, px2 - 16, y + 12, fill=bg, outline="#64748B", width=1.5)
                c.create_text(px2 - 60, y, text=val, fill="#FFFFFF", font=("Segoe UI", 9, "bold"))
                self._reg_btn(px2 - 104, y - 12, px2 - 16, y + 12, act_left)
            else:
                c.create_rectangle(px2 - 144, y - 12, px2 - 116, y + 12, fill="#1E293B", outline="#475569", width=1.5)
                c.create_text(px2 - 130, y, text="-", fill="#FFFFFF", font=("Segoe UI", 11, "bold"))
                self._reg_btn(px2 - 144, y - 12, px2 - 116, y + 12, act_left)

                c.create_text(px2 - 80, y, text=val, fill="#FACC15", font=("Segoe UI", 9, "bold"))

                c.create_rectangle(px2 - 44, y - 12, px2 - 16, y + 12, fill="#1E293B", outline="#475569", width=1.5)
                c.create_text(px2 - 30, y, text="+", fill="#FFFFFF", font=("Segoe UI", 11, "bold"))
                self._reg_btn(px2 - 44, y - 12, px2 - 16, y + 12, act_right)
            y += 34

        c.create_rectangle(px1 + 20, py2 - 42, (px1 + px2) // 2 - 8, py2 - 12, fill="#334155", outline="#64748B", width=1.5)
        c.create_text((px1 + 20 + (px1 + px2) // 2 - 8) // 2, py2 - 27, text="Defaults", fill="#FFFFFF", font=("Segoe UI", 9, "bold"))
        self._reg_btn(px1 + 20, py2 - 42, (px1 + px2) // 2 - 8, py2 - 12, self.reset_defaults)

        c.create_rectangle((px1 + px2) // 2 + 8, py2 - 42, px2 - 20, py2 - 12, fill="#16A34A", outline="#86EFAC", width=1.5)
        c.create_text(((px1 + px2) // 2 + 8 + px2 - 20) // 2, py2 - 27, text="Done", fill="#FFFFFF", font=("Segoe UI", 9, "bold"))
        self._reg_btn((px1 + px2) // 2 + 8, py2 - 42, px2 - 20, py2 - 12, self.toggle_settings)

    def _draw_win_banner(self) -> None:
        c = self.canvas
        cx, cy = self.state.width // 2, self.state.height // 2
        c.create_rectangle(cx - 150, cy - 82, cx + 150, cy + 78, fill="#0F172A", outline="#FACC15", width=3)
        c.create_text(cx, cy - 46, text="YOU WIN!", fill="#FACC15", font=("Segoe UI", 22, "bold"))
        c.create_text(
            cx, cy - 12,
            text=f"Auto-Pilot cleared {self.state.score} pipes!" if self.state.auto_pilot else f"Cleared {self.state.score} pipes!",
            fill="#E2E8F0", font=("Segoe UI", 10),
        )
        c.create_rectangle(cx - 120, cy + 24, cx - 10, cy + 60, fill="#16A34A", outline="#86EFAC", width=1.5)
        c.create_text(cx - 65, cy + 42, text="Keep Flying", fill="#FFFFFF", font=("Segoe UI", 9, "bold"))
        self._reg_btn(cx - 120, cy + 24, cx - 10, cy + 60, self.continue_endless)

        c.create_rectangle(cx + 10, cy + 24, cx + 120, cy + 60, fill="#0284C7", outline="#7DD3FC", width=1.5)
        c.create_text(cx + 65, cy + 42, text="Play Again", fill="#FFFFFF", font=("Segoe UI", 9, "bold"))
        self._reg_btn(cx + 10, cy + 24, cx + 120, cy + 60, self.reset_game)

    def _draw_gameover_banner(self) -> None:
        c = self.canvas
        cx, cy = self.state.width // 2, self.state.height // 2
        c.create_rectangle(cx - 135, cy - 58, cx + 135, cy + 56, fill="#0F172A", outline="#EF4444", width=3)
        c.create_text(cx, cy - 26, text="CRASHED!", fill="#F87171", font=("Segoe UI", 18, "bold"))
        c.create_text(
            cx, cy + 4,
            text=f"Score: {self.state.score}   Best: {self.state.best_score}",
            fill="#E2E8F0", font=("Segoe UI", 10, "bold"),
        )
        c.create_text(cx, cy + 32, text="Click or press Space / R to retry", fill="#94A3B8", font=("Segoe UI", 9))

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    FloatingFlappyApp().run()
