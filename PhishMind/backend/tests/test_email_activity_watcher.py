from app.watchers.email_activity_watcher import EmailActivityWatcher


class FakeClock:
    """Lets tests move time forward deterministically without real sleeps."""

    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _make_watcher(is_open_sequence, grace_seconds=30.0):
    """is_open_sequence: list of bools popped in order, one per tick()."""
    calls = {"opened": 0, "closed": 0}
    sequence = list(is_open_sequence)

    def is_email_open():
        return sequence.pop(0)

    clock = FakeClock()
    watcher = EmailActivityWatcher(
        on_email_open=lambda: calls.__setitem__("opened", calls["opened"] + 1),
        on_email_closed=lambda: calls.__setitem__("closed", calls["closed"] + 1),
        is_email_open=is_email_open,
        grace_seconds=grace_seconds,
        clock_fn=clock,
        sleep_fn=lambda _s: None,
    )
    return watcher, calls, clock


def test_opens_once_when_email_window_appears():
    watcher, calls, clock = _make_watcher([True, True, True])
    watcher.tick()
    watcher.tick()
    watcher.tick()
    assert calls["opened"] == 1
    assert calls["closed"] == 0
    assert watcher.scanning_active is True


def test_does_not_close_within_grace_period():
    watcher, calls, clock = _make_watcher([True, False, False], grace_seconds=30.0)
    watcher.tick()  # opens
    clock.advance(10)
    watcher.tick()  # closed, but only 10s elapsed < 30s grace
    clock.advance(10)
    watcher.tick()  # closed, 20s elapsed < 30s grace
    assert calls["opened"] == 1
    assert calls["closed"] == 0
    assert watcher.scanning_active is True


def test_closes_after_grace_period_expires():
    watcher, calls, clock = _make_watcher([True, False, False], grace_seconds=30.0)
    watcher.tick()  # opens at t=0
    clock.advance(15)
    watcher.tick()  # still within grace
    clock.advance(20)  # total 35s since last seen open
    watcher.tick()  # grace expired -> should close
    assert calls["opened"] == 1
    assert calls["closed"] == 1
    assert watcher.scanning_active is False


def test_reopening_before_grace_expires_cancels_close():
    watcher, calls, clock = _make_watcher([True, False, True, False], grace_seconds=30.0)
    watcher.tick()  # opens at t=0
    clock.advance(20)
    watcher.tick()  # closed but within grace (20s < 30s)
    clock.advance(5)
    watcher.tick()  # reopens at t=25, resets last_seen_open_at
    clock.advance(20)  # only 20s since the reopen
    watcher.tick()  # closed again, but within grace relative to the reopen
    assert calls["opened"] == 1  # never re-fired since it never actually closed
    assert calls["closed"] == 0
    assert watcher.scanning_active is True


def test_detector_exception_is_treated_as_closed_not_a_crash():
    def flaky_detector():
        raise RuntimeError("window enumeration failed")

    calls = {"opened": 0, "closed": 0}
    clock = FakeClock()
    watcher = EmailActivityWatcher(
        on_email_open=lambda: calls.__setitem__("opened", calls["opened"] + 1),
        on_email_closed=lambda: calls.__setitem__("closed", calls["closed"] + 1),
        is_email_open=flaky_detector,
        clock_fn=clock,
        sleep_fn=lambda _s: None,
    )
    watcher.tick()  # should not raise
    assert calls["opened"] == 0
    assert watcher.scanning_active is False


def test_callback_exception_does_not_break_the_watcher():
    def boom():
        raise ValueError("callback exploded")

    sequence = [True]
    clock = FakeClock()
    watcher = EmailActivityWatcher(
        on_email_open=boom,
        on_email_closed=lambda: None,
        is_email_open=lambda: sequence.pop(0),
        clock_fn=clock,
        sleep_fn=lambda _s: None,
    )
    watcher.tick()  # on_email_open raises internally but tick() must not propagate it
    assert watcher.scanning_active is True  # state still updates even though the callback failed
