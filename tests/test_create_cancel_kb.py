from db.models import ServiceTemplate
from bot.keyboards.common import (
    client_name_kb,
    create_cancel_kb,
    template_picker_kb,
)
from bot.keyboards.labels import CANCEL


def test_create_cancel_kb() -> None:
    kb = create_cancel_kb()
    assert kb.inline_keyboard[0][0].callback_data == "create:cancel"
    assert kb.inline_keyboard[0][0].text == CANCEL


def test_template_picker_has_cancel() -> None:
    tpl = ServiceTemplate(
        id=1,
        name="10GB",
        volume_gb=10.0,
        expiry_days=30,
        sort_order=1,
        is_active=True,
    )
    kb = template_picker_kb([tpl])
    assert kb.inline_keyboard[-1][0].callback_data == "create:cancel"


def test_client_name_kb_has_cancel() -> None:
    kb = client_name_kb()
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[1][0].callback_data == "create:cancel"
