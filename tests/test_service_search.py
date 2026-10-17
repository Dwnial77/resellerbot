from bot.handlers.reseller import (
    MAX_SEARCH_QUERY_LEN,
    _filter_records,
    _normalize_search_query,
)
from db.models import ClientRecord


def _records(*emails: str) -> list[ClientRecord]:
    return [
        ClientRecord(
            id=i + 1,
            reseller_tg_id=100,
            panel_id=1,
            email=email,
            inbound_ids="[1]",
            allocated_bytes=0,
            expiry_time=0,
        )
        for i, email in enumerate(emails)
    ]


def _emails(records: list[ClientRecord]) -> list[str]:
    return [r.email for r in records]


def test_filter_records_case_insensitive_substring() -> None:
    records = _records("Alice01", "bob02", "Charlie03")
    assert _emails(_filter_records(records, "ali")) == ["Alice01"]
    assert _emails(_filter_records(records, "BOB")) == ["bob02"]
    assert _filter_records(records, "0") == records


def test_filter_records_blank_query_returns_all() -> None:
    records = _records("a", "b", "c")
    assert _filter_records(records, None) == records
    assert _filter_records(records, "") == records
    assert _filter_records(records, "   ") == records


def test_filter_records_no_match() -> None:
    assert _filter_records(_records("a", "b"), "zzz") == []


def test_normalize_search_query_strips_and_caps_length() -> None:
    assert _normalize_search_query("  hello  ") == "hello"
    assert _normalize_search_query("") == ""
    long_query = "x" * (MAX_SEARCH_QUERY_LEN + 20)
    assert len(_normalize_search_query(long_query)) == MAX_SEARCH_QUERY_LEN


def test_search_callback_data_under_64_bytes() -> None:
    assert len("svc:search") < 64
    assert len("svc:search:clear") < 64
    assert len("svc:search:cancel") < 64
