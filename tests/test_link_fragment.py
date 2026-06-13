from urllib.parse import unquote

from xui.link_fragment import (
    apply_fragment_to_vless_link,
    apply_panel_fragment_to_vless_link,
    build_panel_link_fragment,
    format_traffic_bytes,
    merge_panel_link_fragment,
)

GB = 1024**3
EMAIL = "vispa-client-f0668410"
TOTAL = int(10 * GB)


def test_build_panel_fragment_matches_panel_style() -> None:
    frag = build_panel_link_fragment("ali-client-ijfgwajgwa", int(10 * GB))
    assert frag == "ali-client-ijfgwajgwa-10.00GB📊"


def test_apply_fragment_encodes_emoji() -> None:
    base = (
        "vless://uuid@host:443?encryption=none&security=reality&type=tcp"
    )
    frag = build_panel_link_fragment("ali-client-ijfgwajgwa", int(10 * GB))
    out = apply_fragment_to_vless_link(base, frag)
    assert out.endswith("%F0%9F%93%8A")
    assert "ali-client-ijfgwajgwa-10.00GB" in out


def test_apply_fragment_skips_if_present() -> None:
    link = "vless://a@b:1?type=tcp#existing"
    out = apply_fragment_to_vless_link(link, "new")
    assert out == link


def test_merge_panel_link_fragment_empty() -> None:
    assert merge_panel_link_fragment("", EMAIL, TOTAL) == build_panel_link_fragment(
        EMAIL, TOTAL
    )


def test_merge_panel_link_fragment_inbound_suffix() -> None:
    merged = merge_panel_link_fragment("-irancel", EMAIL, TOTAL)
    assert merged == f"{EMAIL}-10.00GB📊-irancel"


def test_merge_panel_link_fragment_idempotent_when_email_present() -> None:
    existing = build_panel_link_fragment(EMAIL, TOTAL)
    assert merge_panel_link_fragment(existing, EMAIL, TOTAL) == existing


def test_apply_panel_fragment_merges_existing_inbound_remark() -> None:
    link = "vless://uuid@host:443?type=tcp#-irancel"
    out = apply_panel_fragment_to_vless_link(link, EMAIL, TOTAL)
    fragment = unquote(out.split("#", 1)[1])
    assert EMAIL in fragment
    assert fragment.endswith("-irancel")
    assert "10.00GB" in fragment


def test_format_traffic_gb() -> None:
    assert format_traffic_bytes(int(10 * GB)) == "10.00GB"
