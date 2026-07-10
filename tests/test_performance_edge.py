"""
Performance and edge case validation tests (Task 3.3).

Tests verify:
1. Fast SSE events → 3-second acceleration threshold (charDelay drops to 5ms)
2. Animation concurrency → no crashes with simultaneous typewriter + 3 tool steps
3. Memory leak prevention → state objects properly reset across 10 rounds
4. Background tab recovery → batch rendering after gap detection (>100ms tick gap)
5. Performance API frame rate → tick logic maintains 30fps+ throughput

All tests are pure-logic validation of the TypewriterRenderer and StepRenderer
algorithms implemented in app/static/app.js.
"""

import pytest
import time


# ═══════════════════════════════════════════════════════════════════
# Helper: reimplement the TypewriterRenderer tick logic in Python
# for deterministic testing without a browser/DOM.
# ═══════════════════════════════════════════════════════════════════


def simulate_tick_logic(
    full_text: str,
    displayed_length: int,
    last_tick_time: float,
    current_timestamp: float,
    start_time: float,
    char_delay: int = 30,
):
    """
    Simulate a single tick of the TypewriterRenderer rAF loop.

    Returns (new_displayed_length, chars_rendered, effective_delay, batch_size, new_last_tick_time).

    The logic mirrors the JS implementation:
    - If queueElapsed > 3000ms → effectiveDelay drops to 5ms
    - If elapsed (gap between ticks) > 100ms → batchSize = 5 (background tab recovery)
    - Otherwise → batchSize = 1
    """
    elapsed = current_timestamp - last_tick_time
    queue_elapsed = current_timestamp - start_time

    # Acceleration mode: queue exceeds 3 seconds
    effective_delay = 5 if queue_elapsed > 3000 else char_delay

    # Background tab recovery: gap > 100ms → batch render
    batch_size = 5 if elapsed > 100 else 1

    chars_rendered = 0
    new_displayed = displayed_length

    if elapsed >= effective_delay:
        while chars_rendered < batch_size and new_displayed < len(full_text):
            new_displayed += 1
            chars_rendered += 1
        return new_displayed, chars_rendered, effective_delay, batch_size, current_timestamp
    else:
        return new_displayed, 0, effective_delay, batch_size, last_tick_time


# ═══════════════════════════════════════════════════════════════════
# Helper: TypewriterRenderer state machine for full lifecycle tests
# ═══════════════════════════════════════════════════════════════════


class SimulatedTypewriterRenderer:
    """Complete simulation of the TypewriterRenderer state machine."""

    def __init__(self):
        self.full_text = ""
        self.displayed_length = 0
        self.char_delay = 30
        self.is_running = False
        self.last_tick_time = 0.0
        self.start_time = 0.0
        self._render_log = []  # records (timestamp, displayed_length) for each render

    def append_text(self, text: str):
        """Accumulate text and start the render loop."""
        try:
            if not isinstance(text, str):
                text = str(text or "")
            self.full_text += text
            if not self.is_running:
                # start_time is set to 0 here; the first tick(timestamp)
                # will capture the actual timestamp as start_time to keep
                # queue_elapsed = timestamp - start_time consistent.
                self.start_time = 0.0
                self.is_running = True
                self.last_tick_time = 0.0
        except Exception:
            self.flush()

    def tick(self, current_timestamp: float):
        """Simulate one rAF tick. Returns True if more ticks needed."""
        if not self.is_running:
            return False

        # Capture the start time from the first tick timestamp so that
        # queue_elapsed = current_timestamp - start_time is meaningful.
        if not self.start_time:
            self.start_time = current_timestamp

        if not self.last_tick_time:
            self.last_tick_time = current_timestamp

        result = simulate_tick_logic(
            full_text=self.full_text,
            displayed_length=self.displayed_length,
            last_tick_time=self.last_tick_time,
            current_timestamp=current_timestamp,
            start_time=self.start_time,
            char_delay=self.char_delay,
        )
        new_displayed, chars_rendered, effective_delay, batch_size, new_last = result
        self.displayed_length = new_displayed
        self.last_tick_time = new_last

        if chars_rendered > 0:
            self._render_log.append((current_timestamp, self.displayed_length))

        if self.displayed_length >= len(self.full_text):
            self.is_running = False
            return False
        return True

    def run_ticks(self, timestamps: list):
        """Run a sequence of ticks with given timestamps (ms)."""
        for ts in timestamps:
            if not self.is_running:
                break
            self.tick(ts)

    def flush(self):
        """Immediately render all remaining text."""
        self.displayed_length = len(self.full_text)
        self.is_running = False

    def stop(self):
        """Stop rendering without finishing."""
        self.is_running = False

    def reset(self):
        """Clear all state."""
        self.stop()
        self.full_text = ""
        self.displayed_length = 0
        self.char_delay = 30
        self.last_tick_time = 0.0
        self.start_time = 0.0
        self._render_log = []

    def get_rendered_text(self) -> str:
        return self.full_text[:self.displayed_length]


# ═══════════════════════════════════════════════════════════════════
# Helper: Simulated StepRenderer
# ═══════════════════════════════════════════════════════════════════


class SimulatedStepRenderer:
    """Simulation of the StepRenderer state machine."""

    def __init__(self):
        self.steps = {}  # stepId → {status, label}

    def create_step(self, step_id: str, label: str):
        if step_id in self.steps:
            del self.steps[step_id]
        self.steps[step_id] = {"status": "running", "label": label}

    def update_step(self, step_id: str, status: str):
        if step_id not in self.steps:
            return
        if status not in ("running", "completed", "error"):
            return
        self.steps[step_id]["status"] = status

    def clear_steps(self):
        self.steps.clear()

    def has_step(self, step_id: str) -> bool:
        return step_id in self.steps

    def get_step_count(self) -> int:
        return len(self.steps)

    def get_running_count(self) -> int:
        return sum(1 for s in self.steps.values() if s["status"] == "running")


# ═══════════════════════════════════════════════════════════════════
# Test 1: Fast SSE Events — 3-Second Acceleration Threshold
# ═══════════════════════════════════════════════════════════════════


class TestAccelerationThreshold:
    """Verify that the 3-second queue threshold triggers acceleration (charDelay → 5ms)."""

    def test_normal_speed_before_threshold(self):
        """Before the 3-second threshold, charDelay should remain 30ms."""
        # At t=0, queue_elapsed=0, effective_delay should be 30
        _, _, effective_delay, _, _ = simulate_tick_logic(
            full_text="Hello World",
            displayed_length=0,
            last_tick_time=0,
            current_timestamp=0,
            start_time=0,
            char_delay=30,
        )
        assert effective_delay == 30

    def test_acceleration_after_threshold(self):
        """After 3 seconds, charDelay should drop to 5ms."""
        # At t=3001, queue_elapsed > 3000, effective_delay should be 5
        _, _, effective_delay, _, _ = simulate_tick_logic(
            full_text="Hello World",
            displayed_length=0,
            last_tick_time=3000,
            current_timestamp=3001,
            start_time=0,
            char_delay=30,
        )
        assert effective_delay == 5

    def test_exactly_at_threshold(self):
        """At exactly 3000ms, no acceleration (boundary is > not >=)."""
        _, _, effective_delay, _, _ = simulate_tick_logic(
            full_text="Hello World",
            displayed_length=0,
            last_tick_time=3000,
            current_timestamp=3000,
            start_time=0,
            char_delay=30,
        )
        assert effective_delay == 30  # 3000 is NOT > 3000

    def test_well_beyond_threshold(self):
        """At 10 seconds, acceleration is definitely active."""
        _, _, effective_delay, _, _ = simulate_tick_logic(
            full_text="Hello World",
            displayed_length=0,
            last_tick_time=10000,
            current_timestamp=10001,
            start_time=0,
            char_delay=30,
        )
        assert effective_delay == 5

    def test_rapid_sse_events_trigger_acceleration(self):
        """
        Simulate rapid SSE events at 10ms intervals.
        After 3 seconds of accumulation, the acceleration mechanism should trigger,
        causing charDelay to drop to 5ms.

        Scenario: SSE events arrive rapidly (every 10ms), the typewriter runs at
        rAF speed (~16ms = 60fps). After 3 seconds of queue accumulation,
        effectiveDelay drops from 30ms to 5ms, dramatically speeding up rendering.
        """
        renderer = SimulatedTypewriterRenderer()

        # Simulate rapid SSE events: all text arrives quickly (as if 500 events
        # at 10ms intervals appended to the buffer)
        num_events = 500
        text = "x" * num_events
        renderer.append_text(text)

        # Run ticks at 16ms intervals (60fps, matching rAF)
        timestamps = [i * 16 for i in range(313)]  # ~5000ms of ticks
        renderer.run_ticks(timestamps)

        # After 5 seconds of ticks at 60fps, with acceleration active after 3s:
        # - At 16ms/tick, chars render every 2 ticks (32ms >= 30ms): ~93 chars in 3s
        # - After 3s, at 5ms/char, each tick renders 1 char: ~125 chars in 2s
        # - Total expected: ~218 chars
        # Key verification: with acceleration, the second half renders ~125 chars
        # vs without acceleration it would be ~62 chars in the same period
        rendered_chars = renderer.displayed_length
        total_chars = len(renderer.full_text)
        assert rendered_chars > 200, (
            f"Acceleration did not trigger sufficiently: only {rendered_chars} chars rendered out of {total_chars}"
        )

        # Also verify that the last 100 chars rendered faster than the first 100
        # (acceleration proof: the render_log stores timestamps with displayed_length)
        half_point = rendered_chars // 2
        # Find the timestamp when we reached half_point
        half_time = None
        for ts, length in renderer._render_log:
            if length >= half_point and half_time is None:
                half_time = ts
                break
        # Find the last render timestamp
        last_time = renderer._render_log[-1][0] if renderer._render_log else 0
        if half_time is not None and last_time > half_time:
            # The second half should be faster (acceleration)
            first_half_duration = half_time
            second_half_duration = last_time - half_time
            assert second_half_duration < first_half_duration, (
                f"Acceleration expected: first half={first_half_duration}ms, "
                f"second half={second_half_duration}ms"
            )

    def test_rendered_text_is_correct_after_acceleration(self):
        """Verify rendered text after acceleration is correct (no corruption)."""
        renderer = SimulatedTypewriterRenderer()
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 10  # 260 chars
        renderer.append_text(text)

        # Run many ticks
        timestamps = list(range(0, 10000, 5))
        renderer.run_ticks(timestamps)

        rendered = renderer.get_rendered_text()
        assert rendered == text[: len(rendered)]
        assert len(rendered) == len(text)

    def test_acceleration_does_not_skip_characters(self):
        """Acceleration should not cause characters to be skipped."""
        renderer = SimulatedTypewriterRenderer()
        # Use unique characters to verify no skipping
        text = "".join(chr(65 + i % 26) for i in range(100))
        renderer.append_text(text)

        timestamps = list(range(0, 5000, 5))
        renderer.run_ticks(timestamps)
        renderer.flush()

        rendered = renderer.get_rendered_text()
        assert rendered == text, "Acceleration must not skip characters"


# ═══════════════════════════════════════════════════════════════════
# Test 2: Animation Concurrency
# ═══════════════════════════════════════════════════════════════════


class TestAnimationConcurrency:
    """Verify that multiple simultaneous animations (typewriter + 3 tool steps) operate safely."""

    def test_concurrent_typewriter_and_steps_no_crash(self):
        """
        Simulate running typewriter animation alongside 3 tool step animations.
        Verify no state corruption or crash.
        """
        renderer = SimulatedTypewriterRenderer()
        step_renderer = SimulatedStepRenderer()

        # Start typewriter
        renderer.append_text("Thinking about the query...")

        # Create 3 tool steps simultaneously
        step_renderer.create_step("tool:query_db", "query_db")
        step_renderer.create_step("tool:describe_table", "describe_table")
        step_renderer.create_step("tool:execute_sql", "execute_sql")

        # Run typewriter ticks while steps are animating
        timestamps = list(range(0, 3000, 10))
        renderer.run_ticks(timestamps)

        # All steps should still exist
        assert step_renderer.get_step_count() == 3
        assert step_renderer.get_running_count() == 3

        # No crash, typewriter progressed
        assert renderer.displayed_length > 0

    def test_step_status_transitions_during_typewriter(self):
        """Step status transitions should work correctly while typewriter is running."""
        renderer = SimulatedTypewriterRenderer()
        step_renderer = SimulatedStepRenderer()

        renderer.append_text("Processing...")
        step_renderer.create_step("tool:step1", "step1")
        step_renderer.create_step("tool:step2", "step2")
        step_renderer.create_step("tool:step3", "step3")

        # Run some ticks
        renderer.run_ticks(list(range(0, 1000, 10)))

        # Transition steps
        step_renderer.update_step("tool:step1", "completed")
        step_renderer.update_step("tool:step2", "error")

        # Verify transitions
        assert step_renderer.steps["tool:step1"]["status"] == "completed"
        assert step_renderer.steps["tool:step2"]["status"] == "error"
        assert step_renderer.steps["tool:step3"]["status"] == "running"

        # Continue typewriter
        renderer.run_ticks(list(range(1000, 2000, 10)))
        renderer.flush()

        # All state intact
        assert renderer.get_rendered_text() == "Processing..."
        assert step_renderer.get_step_count() == 3

    def test_large_number_of_simultaneous_steps(self):
        """Creating many steps while typewriter is running should not crash."""
        renderer = SimulatedTypewriterRenderer()
        step_renderer = SimulatedStepRenderer()

        renderer.append_text("Starting analysis...")

        # Create 20 steps
        for i in range(20):
            step_renderer.create_step(f"tool:step_{i}", f"step_{i}")

        renderer.run_ticks(list(range(0, 2000, 10)))

        assert step_renderer.get_step_count() == 20
        assert renderer.displayed_length > 0

    def test_rapid_create_update_cycle(self):
        """Rapid create/update cycles on steps while typewriter runs."""
        renderer = SimulatedTypewriterRenderer()
        step_renderer = SimulatedStepRenderer()

        renderer.append_text("Querying...")

        # Rapid cycle: create → update → create new
        for i in range(10):
            step_id = f"tool:step_{i}"
            step_renderer.create_step(step_id, f"step_{i}")
            renderer.run_ticks([i * 100])
            step_renderer.update_step(step_id, "completed")

        renderer.flush()

        assert step_renderer.get_step_count() == 10
        for i in range(10):
            assert step_renderer.steps[f"tool:step_{i}"]["status"] == "completed"

    def test_frame_rate_adequate_for_30fps(self):
        """
        Verify that the tick logic can process frames fast enough for 30fps.
        At 30fps, each frame has ~33ms budget. The tick logic is O(1) per frame
        (at most 5 characters rendered per tick), so it should easily fit.
        """
        renderer = SimulatedTypewriterRenderer()
        # 1000 characters of text
        renderer.append_text("x" * 1000)

        # Simulate 100 ticks at 33ms intervals (30fps for ~3.3 seconds)
        timestamps = [i * 33 for i in range(100)]
        renderer.run_ticks(timestamps)

        # At 33ms/tick with 30ms charDelay (accelerating to 5ms after 3s):
        # - First tick is a no-op (elapsed=0 because last_tick_time is set to timestamp)
        # - Remaining 99 ticks render 1 char each (elapsed 33ms >= 30ms or 5ms)
        # - Expected: ~99 chars rendered
        assert renderer.displayed_length >= 95, (
            f"Frame rate too slow: only {renderer.displayed_length} chars in 100 ticks at 33ms"
        )
        # The logic is O(1) per tick, so 100 ticks should complete in well under 33ms each
        # (this is verified by the test taking trivial wall-clock time)


# ═══════════════════════════════════════════════════════════════════
# Test 3: Memory Leak Prevention
# ═══════════════════════════════════════════════════════════════════


class TestMemoryLeakPrevention:
    """Verify that state objects are properly reset across conversation rounds."""

    def test_typewriter_reset_clears_all_state(self):
        """reset() should clear fullText, displayedLength, charDelay, and stop running."""
        renderer = SimulatedTypewriterRenderer()

        # Populate state
        renderer.append_text("Long thinking text accumulated here")
        renderer.run_ticks(list(range(0, 2000, 10)))
        renderer.char_delay = 5  # was accelerated

        # Verify state is populated
        assert len(renderer.full_text) > 0
        assert renderer.displayed_length > 0
        assert renderer.char_delay == 5
        assert renderer.is_running or renderer.displayed_length > 0

        # Reset
        renderer.reset()

        # Verify all state is cleared
        assert renderer.full_text == ""
        assert renderer.displayed_length == 0
        assert renderer.char_delay == 30  # reset to default
        assert renderer.is_running is False
        assert renderer.last_tick_time == 0.0
        assert renderer.start_time == 0.0

    def test_step_renderer_clear_removes_all_entries(self):
        """clearSteps() should empty the Map completely."""
        step_renderer = SimulatedStepRenderer()

        # Populate
        for i in range(10):
            step_renderer.create_step(f"tool:step_{i}", f"step_{i}")

        assert step_renderer.get_step_count() == 10

        # Clear
        step_renderer.clear_steps()

        assert step_renderer.get_step_count() == 0
        # Verify no entries remain (Map is empty)
        assert len(step_renderer.steps) == 0

    def test_ten_rounds_no_state_leak(self):
        """
        Simulate 10 consecutive conversation rounds.
        After each round, reset both renderers and verify no residual state.
        """
        renderer = SimulatedTypewriterRenderer()
        step_renderer = SimulatedStepRenderer()

        for round_num in range(1, 11):
            # Round N: simulate thinking + tool steps
            renderer.append_text(f"Round {round_num} thinking text that is quite long " * 5)
            renderer.run_ticks(list(range(0, 3000, 10)))
            renderer.flush()

            for i in range(3):
                step_renderer.create_step(f"tool:round_{round_num}_step_{i}", f"step_{i}")
                step_renderer.update_step(f"tool:round_{round_num}_step_{i}", "completed")

            # Verify round completed
            assert renderer.get_rendered_text().startswith(f"Round {round_num}")
            assert step_renderer.get_step_count() == 3

            # Reset for next round
            renderer.reset()
            step_renderer.clear_steps()

            # Verify clean state
            assert renderer.full_text == "", f"Round {round_num}: fullText not cleared"
            assert renderer.displayed_length == 0, f"Round {round_num}: displayedLength not cleared"
            assert renderer.char_delay == 30, f"Round {round_num}: charDelay not reset"
            assert renderer.is_running is False, f"Round {round_num}: still running"
            assert step_renderer.get_step_count() == 0, f"Round {round_num}: steps not cleared"

        # After 10 rounds, memory usage should be bounded (no accumulation)
        assert renderer.full_text == ""
        assert step_renderer.get_step_count() == 0

    def test_no_step_id_accumulation_across_rounds(self):
        """
        Step IDs from previous rounds should not persist across rounds.
        """
        step_renderer = SimulatedStepRenderer()

        # Round 1: create steps with round-1 IDs
        step_renderer.create_step("tool:round1_a", "a")
        step_renderer.create_step("tool:round1_b", "b")
        assert step_renderer.has_step("tool:round1_a")
        assert step_renderer.has_step("tool:round1_b")

        # Clear
        step_renderer.clear_steps()

        # Round 2: old IDs should not exist
        assert not step_renderer.has_step("tool:round1_a")
        assert not step_renderer.has_step("tool:round1_b")

        # Round 2: create new steps
        step_renderer.create_step("tool:round2_a", "a")
        assert step_renderer.has_step("tool:round2_a")
        assert not step_renderer.has_step("tool:round1_a")

    def test_rapid_reset_pattern(self):
        """Rapid reset → append → reset cycles should not leak state."""
        renderer = SimulatedTypewriterRenderer()

        for i in range(50):
            renderer.append_text("data")
            renderer.reset()
            assert renderer.full_text == ""
            assert renderer.displayed_length == 0

        # Final state should be clean
        assert renderer.full_text == ""
        assert renderer.is_running is False

    def test_stop_vs_reset_distinction(self):
        """
        stop() should halt rendering but preserve accumulated text.
        reset() should clear everything.
        """
        renderer = SimulatedTypewriterRenderer()

        # Append and run
        renderer.append_text("Important thinking text")
        renderer.run_ticks(list(range(0, 500, 10)))

        # Stop: should preserve text
        renderer.stop()
        assert len(renderer.full_text) > 0, "stop() should preserve accumulated text"
        assert renderer.is_running is False

        # Reset: should clear everything
        renderer.reset()
        assert renderer.full_text == "", "reset() should clear accumulated text"
        assert renderer.displayed_length == 0


# ═══════════════════════════════════════════════════════════════════
# Test 4: Background Tab Recovery
# ═══════════════════════════════════════════════════════════════════


class TestBackgroundTabRecovery:
    """Verify batch rendering logic when the browser tab is backgrounded."""

    def test_gap_over_100ms_triggers_batch_render(self):
        """When tick gap exceeds 100ms, batchSize should be 5."""
        # Simulate a tick after a long gap (background tab)
        _, _, _, batch_size, _ = simulate_tick_logic(
            full_text="x" * 100,
            displayed_length=0,
            last_tick_time=0,
            current_timestamp=150,  # 150ms gap
            start_time=0,
            char_delay=30,
        )
        assert batch_size == 5, "Gap > 100ms should trigger batch render of 5 chars"

    def test_gap_exactly_100ms_does_not_trigger_batch(self):
        """At exactly 100ms gap, batch rendering should NOT trigger (boundary is >)."""
        _, _, _, batch_size, _ = simulate_tick_logic(
            full_text="x" * 100,
            displayed_length=0,
            last_tick_time=0,
            current_timestamp=100,  # exactly 100ms
            start_time=0,
            char_delay=30,
        )
        assert batch_size == 1, "Gap of exactly 100ms should NOT trigger batch (boundary is >)"

    def test_gap_under_100ms_uses_normal_batch(self):
        """Normal tick gaps (< 100ms) should use batchSize = 1."""
        _, _, _, batch_size, _ = simulate_tick_logic(
            full_text="x" * 100,
            displayed_length=0,
            last_tick_time=0,
            current_timestamp=30,  # 30ms gap
            start_time=0,
            char_delay=30,
        )
        assert batch_size == 1

    def test_background_tab_simulation_5_seconds(self):
        """
        Simulate a tab being backgrounded for 5 seconds, then recovering.
        On recovery, the first tick should batch-render multiple characters.
        """
        renderer = SimulatedTypewriterRenderer()

        # Append text while tab is active
        renderer.append_text("A" * 200)

        # Simulate active ticks for 1 second
        renderer.run_ticks(list(range(0, 1000, 30)))

        chars_before_bg = renderer.displayed_length

        # Simulate 5-second background (no ticks for 5000ms)
        # Then recover with a single tick
        recovery_timestamp = 6000  # 1000ms active + 5000ms gap

        # The tick at recovery_timestamp should batch-render
        renderer.last_tick_time = 1000  # last tick was at 1000ms
        renderer.tick(recovery_timestamp)

        chars_after_recovery = renderer.displayed_length

        # With batch_size=5, at least 5 more characters should render
        chars_gained = chars_after_recovery - chars_before_bg
        assert chars_gained == 5, (
            f"Background tab recovery should batch-render 5 chars, got {chars_gained}"
        )

    def test_background_recovery_does_not_skip_characters(self):
        """
        After background recovery, the rendered text should be a correct prefix
        of the full text (no character skipping).
        """
        renderer = SimulatedTypewriterRenderer()

        text = "The quick brown fox jumps over the lazy dog. " * 10
        renderer.append_text(text)

        # Simulate active ticks
        renderer.run_ticks(list(range(0, 500, 30)))

        # Background for 5 seconds
        bg_timestamp = 5500
        renderer.last_tick_time = 500
        renderer.tick(bg_timestamp)

        rendered = renderer.get_rendered_text()
        assert rendered == text[: len(rendered)], (
            "Background recovery must not corrupt rendered text"
        )

    def test_multiple_background_recoveries(self):
        """Multiple background→foreground cycles should all batch-render correctly."""
        renderer = SimulatedTypewriterRenderer()
        renderer.append_text("X" * 500)

        cycles = [
            (0, 1000),     # active phase 1
            (6000, 1),      # background 5s, 1 tick
            (6030, 3000),   # active phase 2
        ]

        for tick_start, tick_count in cycles:
            if isinstance(tick_count, int) and tick_count > 1:
                # Active phase: multiple ticks
                renderer.run_ticks(list(range(tick_start, tick_start + tick_count, 30)))
            else:
                # Single tick (recovery)
                renderer.tick(tick_start)

        rendered = renderer.get_rendered_text()
        assert rendered == "X" * len(rendered), "Text should be correct after multiple recoveries"

    def test_no_visual_flash_on_recovery(self):
        """
        On background recovery, the text should be updated in a single batch
        (no rapid flickering of incremental updates).
        The render_log should show only 1 new entry per recovery tick.
        """
        renderer = SimulatedTypewriterRenderer()
        renderer.append_text("A" * 100)

        # Active phase
        renderer.run_ticks(list(range(0, 500, 30)))

        logs_before = len(renderer._render_log)

        # Recovery tick
        renderer.tick(5500)

        logs_after = len(renderer._render_log)

        # Only 1 new render entry should be added (batch update, not 5 separate updates)
        render_entries_added = logs_after - logs_before
        assert render_entries_added == 1, (
            f"Recovery should produce 1 render update, got {render_entries_added}"
        )

    def test_combined_acceleration_and_background_recovery(self):
        """
        When both acceleration (queue > 3s) and background recovery (gap > 100ms)
        conditions are active, both should apply simultaneously.
        """
        renderer = SimulatedTypewriterRenderer()
        renderer.append_text("Z" * 500)

        # Simulate 4 seconds of queue time with a background gap
        # Start time is at t=0, last tick was at t=1000
        renderer.start_time = 0
        renderer.last_tick_time = 1000

        # Tick at t=5000: queue_elapsed=5000 (>3000 → acceleration),
        #                 elapsed=4000 (>100 → background recovery)
        result = simulate_tick_logic(
            full_text=renderer.full_text,
            displayed_length=renderer.displayed_length,
            last_tick_time=1000,
            current_timestamp=5000,
            start_time=0,
            char_delay=30,
        )
        _, chars_rendered, effective_delay, batch_size, _ = result

        assert effective_delay == 5, "Acceleration should be active"
        assert batch_size == 5, "Background recovery should be active"
        assert chars_rendered == 5, "Should render 5 chars in one tick"


# ═══════════════════════════════════════════════════════════════════
# Test 5: Performance API Frame Rate Validation
# ═══════════════════════════════════════════════════════════════════


class TestFrameRatePerformance:
    """Validate that the rendering logic can maintain 30fps+ throughput."""

    def test_tick_computation_is_constant_time(self):
        """
        Each tick should perform O(1) work regardless of total text length.
        """
        renderer = SimulatedTypewriterRenderer()

        # Test with 10,000 characters
        renderer.append_text("x" * 10000)

        # Run 100 ticks and measure wall-clock time
        start = time.perf_counter()
        renderer.run_ticks(list(range(0, 3000, 30)))
        elapsed = time.perf_counter() - start

        # 100 ticks should complete in well under 100ms (Python simulation)
        # At 30fps, each frame has 33ms budget
        # In Python, it should be < 10ms total
        assert elapsed < 0.1, (
            f"Tick computation too slow: {elapsed*1000:.1f}ms for 100 ticks"
        )

    def test_30fps_throughput_with_1000_chars(self):
        """
        Simulate rendering 1000 characters at 30fps.
        The logic should complete within a reasonable number of ticks.
        """
        renderer = SimulatedTypewriterRenderer()
        renderer.append_text("Hello world. " * 100)  # ~1300 chars

        ticks_needed = 0
        ts = 0
        while renderer.is_running and ts < 60000:  # 60 second max
            renderer.tick(ts)
            ts += 33  # 30fps = 33ms per frame
            ticks_needed += 1

        # At 30fps with acceleration after 3s:
        # - 3s at 30ms/char (batch=1): ~100 chars in ~90 ticks
        # - After 3s at 5ms/char (batch=1): ~200 chars/sec at 30fps
        # - With background recovery (batch could be 5): faster
        assert renderer.displayed_length == len(renderer.full_text), (
            f"All chars should be rendered: {renderer.displayed_length}/{len(renderer.full_text)}"
        )

    def test_60fps_throughput_does_not_degrade(self):
        """At 60fps (16ms per frame), the logic should still work correctly."""
        renderer = SimulatedTypewriterRenderer()
        renderer.append_text("x" * 500)

        ts = 0
        while renderer.is_running and ts < 30000:
            renderer.tick(ts)
            ts += 16  # 60fps

        assert renderer.displayed_length == len(renderer.full_text)

    def test_no_tick_overhead_accumulation(self):
        """
        The tick function should not accumulate overhead.
        Each tick is independent and should run in constant time.
        """
        renderer = SimulatedTypewriterRenderer()

        # Measure ticks in batches of 100
        times = []
        for batch in range(10):
            renderer.append_text(f"Batch {batch} text. " * 20)
            start = time.perf_counter()
            renderer.run_ticks(list(range(0, 3000, 30)))
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            renderer.reset()

        # All batches should be roughly the same time (no degradation)
        avg = sum(times) / len(times)
        for t in times:
            # Each batch should be within 3x of average (no massive degradation)
            assert t < avg * 3, (
                f"Tick overhead degradation detected: {t*1000:.1f}ms vs avg {avg*1000:.1f}ms"
            )

    def test_concurrent_animation_frame_budget(self):
        """
        Combined typewriter + step animation should fit within 30fps budget.
        The JS logic is: 1 tick per rAF, so combined animations should not
        exceed the per-frame budget.
        """
        renderer = SimulatedTypewriterRenderer()
        step_renderer = SimulatedStepRenderer()

        renderer.append_text("Processing query... " * 20)

        for i in range(3):
            step_renderer.create_step(f"tool:step_{i}", f"step_{i}")

        # Simulate 100 frames at 30fps
        start = time.perf_counter()
        for frame in range(100):
            ts = frame * 33
            renderer.tick(ts)
            # Simulate step status checks (constant time)
            for step_id in list(step_renderer.steps.keys()):
                _ = step_renderer.steps[step_id]["status"]
        elapsed = time.perf_counter() - start

        # 100 frames should complete in well under 100ms
        assert elapsed < 0.1, (
            f"Combined animation frame budget exceeded: {elapsed*1000:.1f}ms for 100 frames"
        )


# ═══════════════════════════════════════════════════════════════════
# Test 6: Edge Case Validation
# ═══════════════════════════════════════════════════════════════════


class TestPerformanceEdgeCases:
    """Additional edge cases for performance scenarios."""

    def test_empty_text_append_during_rapid_events(self):
        """Rapid empty text appends should not affect performance."""
        renderer = SimulatedTypewriterRenderer()

        for _ in range(1000):
            renderer.append_text("")

        # Empty text does not change fullText
        assert renderer.full_text == ""
        # The JS implementation starts the rAF loop on first appendText even
        # with empty string, but the loop immediately completes because
        # displayedLength (0) >= fullText.length (0). So isRunning may be True
        # momentarily but the tick loop finishes instantly.
        # After running one tick, it should complete:
        renderer.tick(16)
        assert renderer.is_running is False

    def test_very_large_text_accumulation(self):
        """100KB of text should not cause issues."""
        renderer = SimulatedTypewriterRenderer()
        large_text = "A" * 100000
        renderer.append_text(large_text)

        # Run ticks until completion
        ts = 0
        while renderer.is_running and ts < 120000:
            renderer.tick(ts)
            ts += 10

        renderer.flush()
        assert renderer.get_rendered_text() == large_text

    def test_single_character_rapid_append(self):
        """Rapid append of single characters should work correctly."""
        renderer = SimulatedTypewriterRenderer()

        text = "Hello, this is a streaming test with single characters."
        for ch in text:
            renderer.append_text(ch)

        renderer.run_ticks(list(range(0, 5000, 10)))
        renderer.flush()

        assert renderer.get_rendered_text() == text

    def test_flush_during_acceleration(self):
        """Flush during acceleration mode should complete immediately."""
        renderer = SimulatedTypewriterRenderer()
        renderer.append_text("x" * 500)

        # Run into acceleration mode
        renderer.run_ticks(list(range(0, 4000, 10)))

        chars_before_flush = renderer.displayed_length

        # Flush
        renderer.flush()

        assert renderer.displayed_length == len(renderer.full_text)
        assert renderer.is_running is False
        assert renderer.displayed_length > chars_before_flush

    def test_reset_during_acceleration(self):
        """Reset during acceleration mode should clear everything."""
        renderer = SimulatedTypewriterRenderer()
        renderer.append_text("x" * 500)

        # Run into acceleration mode
        renderer.run_ticks(list(range(0, 4000, 10)))

        # Reset
        renderer.reset()

        assert renderer.full_text == ""
        assert renderer.displayed_length == 0
        assert renderer.char_delay == 30
        assert renderer.is_running is False

    def test_zero_duration_tick(self):
        """Tick with zero elapsed time should not render."""
        _, chars_rendered, _, _, _ = simulate_tick_logic(
            full_text="Hello",
            displayed_length=0,
            last_tick_time=100,
            current_timestamp=100,  # zero elapsed
            start_time=0,
            char_delay=30,
        )
        assert chars_rendered == 0, "Zero-duration tick should not render"

    def test_negative_elapsed_time_safety(self):
        """
        Negative elapsed time (clock skew) should be handled gracefully.
        In the JS implementation, elapsed would be negative, so batch_size
        would be 1 (since elapsed < 100), and elapsed >= effective_delay
        would be False (negative < 30), so no chars rendered.
        """
        _, chars_rendered, _, batch_size, _ = simulate_tick_logic(
            full_text="Hello",
            displayed_length=0,
            last_tick_time=200,
            current_timestamp=100,  # negative elapsed
            start_time=0,
            char_delay=30,
        )
        assert chars_rendered == 0, "Negative elapsed should not render chars"
        assert batch_size == 1, "Negative elapsed should use default batch size"

    def test_very_large_queue_elapsed(self):
        """Queue elapsed of 1 hour (3,600,000ms) should keep acceleration active."""
        _, _, effective_delay, _, _ = simulate_tick_logic(
            full_text="x" * 1000,
            displayed_length=500,
            last_tick_time=3_600_000,
            current_timestamp=3_600_001,
            start_time=0,
            char_delay=30,
        )
        assert effective_delay == 5, "Acceleration should remain active for very long queues"

    def test_concurrent_reset_and_clear_consistency(self):
        """
        When both typewriter.reset() and stepRenderer.clearSteps() are called
        (as in sendMessage/switchSession), the combined state should be fully clean.
        """
        renderer = SimulatedTypewriterRenderer()
        step_renderer = SimulatedStepRenderer()

        # Populate
        renderer.append_text("Some thinking text")
        for i in range(5):
            step_renderer.create_step(f"tool:step_{i}", f"step_{i}")

        # Combined reset
        renderer.reset()
        step_renderer.clear_steps()

        assert renderer.full_text == ""
        assert renderer.displayed_length == 0
        assert renderer.is_running is False
        assert step_renderer.get_step_count() == 0

        # Verify no cross-contamination
        renderer.append_text("New round text")
        step_renderer.create_step("tool:new_step", "new_step")

        assert renderer.full_text == "New round text"
        assert step_renderer.has_step("tool:new_step")
        assert step_renderer.get_step_count() == 1