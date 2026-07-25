from bot.handlers.reseller import (
    MAX_SEARCH_QUERY_LEN,
    _filter_emails,
    _normalize_search_query,
)


def test_filter_emails_case_insensitive_substring() -> None:
    emails = ["Alice01", "bob02", "Charlie03"]
    assert _filter_emails(emails, "ali") == ["Alice01"]
    assert _filter_emails(emails, "BOB") == ["bob02"]
    assert _filter_emails(emails, "0") == emails


def test_filter_emails_blank_query_returns_all() -> None:
    emails = ["a", "b", "c"]
    assert _filter_emails(emails, None) == emails
    assert _filter_emails(emails, "") == emails
    assert _filter_emails(emails, "   ") == emails


def test_filter_emails_no_match() -> None:
    assert _filter_emails(["a", "b"], "zzz") == []


def test_normalize_search_query_strips_and_caps_length() -> None:
    assert _normalize_search_query("  hello  ") == "hello"
    assert _normalize_search_query("") == ""
    long_query = "x" * (MAX_SEARCH_QUERY_LEN + 20)
    assert len(_normalize_search_query(long_query)) == MAX_SEARCH_QUERY_LEN


def test_search_callback_data_under_64_bytes() -> None:
    query = "x" * MAX_SEARCH_QUERY_LEN
    assert len("svc:search") < 64
    assert len("svc:search:clear") < 64
    assert len("svc:search:cancel") < 64
    # search results themselves reuse the plain "svc:{email}" callback, unaffected by query length
    assert len(f"svc:{query}") < 64
