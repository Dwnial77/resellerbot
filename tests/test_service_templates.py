import pytest

from bot.keyboards.common import template_admin_hub_kb, template_picker_kb
from bot.utils.template_labels import suggest_template_name
from db.models import ServiceTemplate
from db.repository import (
    InvalidTemplateError,
    normalize_template_name,
    validate_template_params,
)


def test_normalize_template_name_ok() -> None:
    assert normalize_template_name("10GB/30روز") == "10GB/30روز"
    assert normalize_template_name("  my-tpl  ") == "my-tpl"


def test_normalize_template_name_empty() -> None:
    with pytest.raises(InvalidTemplateError, match="خالی"):
        normalize_template_name("   ")


def test_normalize_template_name_too_long() -> None:
    with pytest.raises(InvalidTemplateError, match="64"):
        normalize_template_name("x" * 65)


def test_validate_template_params_ok() -> None:
    validate_template_params(10.0, 30)
    validate_template_params(0.5, 0)


def test_validate_template_params_volume() -> None:
    with pytest.raises(InvalidTemplateError, match="حجم"):
        validate_template_params(0, 30)
    with pytest.raises(InvalidTemplateError, match="حجم"):
        validate_template_params(-1, 30)


def test_validate_template_params_expiry() -> None:
    with pytest.raises(InvalidTemplateError, match="انقضا"):
        validate_template_params(10, -1)


def test_suggest_template_name() -> None:
    assert suggest_template_name(10, 30) == "10GB/30روز"
    assert suggest_template_name(10, 0) == "10GB/نامحدود"
    assert suggest_template_name(2.5, 7) == "2.5GB/7روز"


def test_template_admin_hub_kb() -> None:
    templates = [
        ServiceTemplate(
            id=1,
            name="10GB/30d",
            volume_gb=10.0,
            expiry_days=30,
            sort_order=1,
            is_active=True,
        ),
    ]
    kb = template_admin_hub_kb(templates)
    assert kb.inline_keyboard[0][0].callback_data == "atpl:del:1"
    assert kb.inline_keyboard[-1][0].callback_data == "atpl:add"


def test_template_picker_kb() -> None:
    templates = [
        ServiceTemplate(
            id=1,
            name="10GB/30d",
            volume_gb=10.0,
            expiry_days=30,
            sort_order=1,
            is_active=True,
        ),
        ServiceTemplate(
            id=2,
            name="50GB/90d",
            volume_gb=50.0,
            expiry_days=90,
            sort_order=2,
            is_active=True,
        ),
    ]
    from bot.keyboards.labels import CANCEL, MANUAL_ENTRY

    kb = template_picker_kb(templates)
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].callback_data == "tpl:2"
    assert kb.inline_keyboard[0][0].text == "50GB/90d"
    assert kb.inline_keyboard[-2][0].callback_data == "create:manual"
    assert kb.inline_keyboard[-2][0].text == MANUAL_ENTRY
    assert kb.inline_keyboard[-1][0].callback_data == "create:cancel"
    assert kb.inline_keyboard[-1][0].text == CANCEL
