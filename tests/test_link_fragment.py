from xui.link_fragment import (
    apply_fragment_to_vless_link,
    build_panel_link_fragment,
    format_traffic_bytes,
)

GB = 1024**3


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


def test_format_traffic_gb() -> None:
    assert format_traffic_bytes(int(10 * GB)) == "10.00GB"
