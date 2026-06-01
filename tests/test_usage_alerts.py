from services.usage_alerts import pending_thresholds, usage_percent


def test_usage_percent() -> None:
    assert usage_percent(80, 100) == 80
    assert usage_percent(0, 0) is None


def test_pending_thresholds_empty_below_reset() -> None:
    assert pending_thresholds(70, set()) == []


def test_pending_thresholds_80_only() -> None:
    assert pending_thresholds(85, set()) == [80]


def test_pending_thresholds_80_and_90() -> None:
    assert pending_thresholds(95, set()) == [80, 90]


def test_pending_thresholds_skips_sent() -> None:
    assert pending_thresholds(95, {80}) == [90]
    assert pending_thresholds(85, {80}) == []
