from xui.client import XuiError, _is_client_not_found


def test_is_client_not_found():
    assert _is_client_not_found(XuiError("record not found"))
    assert _is_client_not_found(XuiError("Record Not Found"))
    assert _is_client_not_found(XuiError("client not found"))
    assert not _is_client_not_found(XuiError("forbidden"))
