"""Headless verification tests for Floating Flappy Bird autopilot, adjustments, and unlimited score."""

import random
import unittest

from flappy_float import (
    BIRD_X,
    BonusStar,
    DEFAULT_WIN_SCORE,
    FIXED_DT,
    GameState,
    get_evolution_tier,
    step_physics,
)


class TestAutopilot(unittest.TestCase):
    def test_autopilot_wins_consistently_across_seeds(self) -> None:
        for seed in range(10):
            state = GameState(auto_pilot=True, win_score=DEFAULT_WIN_SCORE)
            rng = random.Random(seed)
            for _ in range(60 * 60):
                step_physics(state, FIXED_DT, rng)
                if state.won or state.game_over:
                    break
            self.assertFalse(state.game_over, f"Autopilot crashed on seed {seed} at score {state.score}")
            self.assertTrue(state.won, f"Autopilot did not reach win_score on seed {seed}")
            self.assertGreaterEqual(state.score, DEFAULT_WIN_SCORE)

    def test_unlimited_score_mode_never_stops_at_win(self) -> None:
        state = GameState(auto_pilot=True, unlimited_score=True, win_score=5)
        rng = random.Random(42)
        for _ in range(60 * 60):
            step_physics(state, FIXED_DT, rng)
            if state.game_over:
                break
        self.assertFalse(state.game_over, f"Autopilot crashed at score {state.score}")
        self.assertFalse(state.won, "Unlimited score mode should not trigger win stop")
        self.assertGreaterEqual(state.score, 30)

    def test_autopilot_adapts_to_adjusted_speed_gap_and_gravity(self) -> None:
        state = GameState(
            auto_pilot=True,
            unlimited_score=True,
            pipe_speed=240.0,
            pipe_gap=120.0,
            gravity=1650.0,
        )
        rng = random.Random(7)
        for _ in range(60 * 30):
            step_physics(state, FIXED_DT, rng)
            if state.game_over:
                break
        self.assertFalse(state.game_over, f"Autopilot crashed with adjusted settings at score {state.score}")
        self.assertGreaterEqual(state.score, 20)

    def test_autopilot_works_when_resized(self) -> None:
        state = GameState(width=700, height=760, auto_pilot=True, win_score=15)
        rng = random.Random(12)
        for _ in range(60 * 60):
            step_physics(state, FIXED_DT, rng)
            if state.won or state.game_over:
                break
        self.assertFalse(state.game_over, f"Autopilot crashed on resized playfield at score {state.score}")
        self.assertTrue(state.won)
        self.assertGreaterEqual(state.score, 15)

    def test_evolution_tiers_and_bonus_star_collection(self) -> None:
        self.assertEqual(get_evolution_tier(0)[0], "CLASSIC")
        self.assertEqual(get_evolution_tier(10)[0], "CYBER")
        self.assertEqual(get_evolution_tier(25)[0], "PHOENIX")
        self.assertEqual(get_evolution_tier(50)[0], "COSMIC")

        state = GameState(auto_pilot=False, unlimited_score=True)
        state.stars.append(BonusStar(x=BIRD_X + 2.0, y=state.bird_y))
        step_physics(state, FIXED_DT, random.Random(1))
        self.assertEqual(state.score, 3)
        self.assertEqual(len(state.stars), 0)


if __name__ == "__main__":
    unittest.main()
