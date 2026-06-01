"""Admin wizard and hub for global service templates."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import _is_admin
from bot.keyboards import labels as btn
from bot.keyboards.common import (
    template_admin_hub_kb,
    template_delete_confirm_kb,
    template_wizard_confirm_kb,
    template_wizard_expiry_kb,
    template_wizard_name_kb,
    template_wizard_volume_kb,
)
from bot.states import AddTemplateStates
from bot.texts import fa as t
from bot.utils.template_labels import expiry_label, suggest_template_name
from db.models import ServiceTemplate
from db.repository import (
    InvalidTemplateError,
    ServiceTemplateRepository,
    normalize_template_name,
)
from db.session import get_session_factory

router = Router()


async def _template_hub_content() -> tuple[str, object]:
    async with get_session_factory()() as session:
        rows = await ServiceTemplateRepository(session).list_all()

    if not rows:
        text = f"{t.TEMPLATE_LIST_EMPTY}\n\n{t.TEMPLATE_HUB_HINT}"
    else:
        lines = [t.TEMPLATE_LIST_HEADER]
        for r in rows:
            lines.append(
                f"• #{r.id} — {r.name} — {r.volume_gb} GB — "
                f"{expiry_label(r.expiry_days)}"
            )
        text = "\n".join(lines)
    return text, template_admin_hub_kb(rows)


async def _send_template_hub(target: Message) -> None:
    text, markup = await _template_hub_content()
    await target.answer(text, reply_markup=markup)  # type: ignore[arg-type]


async def _edit_template_hub(target: Message) -> None:
    text, markup = await _template_hub_content()
    await target.edit_text(text, reply_markup=markup)  # type: ignore[arg-type]


async def _start_add_wizard(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddTemplateStates.volume)
    await message.answer(
        t.TEMPLATE_WIZARD_VOLUME,
        reply_markup=template_wizard_volume_kb(),
    )


async def _go_to_expiry_step(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTemplateStates.expiry)
    await message.answer(
        t.TEMPLATE_WIZARD_EXPIRY,
        reply_markup=template_wizard_expiry_kb(),
    )


async def _go_to_name_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    suggested = suggest_template_name(data["volume_gb"], data["expiry_days"])
    await state.update_data(suggested_name=suggested)
    await state.set_state(AddTemplateStates.name)
    await message.answer(
        t.TEMPLATE_WIZARD_NAME.format(suggested=suggested),
        reply_markup=template_wizard_name_kb(),
    )


async def _go_to_confirm_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    name = data["name"]
    volume_gb = data["volume_gb"]
    days = data["expiry_days"]
    await state.set_state(AddTemplateStates.confirm)
    await message.answer(
        t.TEMPLATE_WIZARD_CONFIRM.format(
            name=name,
            volume_gb=volume_gb,
            expiry_label=expiry_label(days),
        ),
        reply_markup=template_wizard_confirm_kb(),
    )


@router.message(F.text == btn.SERVICE_TEMPLATES)
@router.message(Command("templates"))
@router.message(Command("list_templates"))
async def template_hub(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await _send_template_hub(message)


@router.message(Command("add_template"))
async def add_template_cmd(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await _start_add_wizard(message, state)


@router.callback_query(F.data == "atpl:hub")
async def template_hub_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if callback.message:
        await _edit_template_hub(callback.message)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data == "atpl:add")
async def template_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if callback.message:
        await _start_add_wizard(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.callback_query(F.data.startswith("atpl:del:"))
async def template_delete_prompt(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        template_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        row = await session.get(ServiceTemplate, template_id)

    if row is None:
        await callback.answer(t.TEMPLATE_NOT_FOUND, show_alert=True)
        return

    await callback.message.edit_text(
        t.TEMPLATE_DELETE_CONFIRM.format(
            id=row.id,
            name=row.name,
            volume_gb=row.volume_gb,
            expiry_label=expiry_label(row.expiry_days),
        ),
        reply_markup=template_delete_confirm_kb(row.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("atpl:del_yes:"))
async def template_delete_confirm(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        template_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        deleted = await ServiceTemplateRepository(session).delete(template_id)

    if not deleted:
        await callback.answer(t.TEMPLATE_NOT_FOUND, show_alert=True)
        return

    await callback.answer(t.TEMPLATE_DELETED.format(id=template_id))
    await _edit_template_hub(callback.message)  # type: ignore[arg-type]


@router.callback_query(F.data == "atpl:wiz_cancel")
async def template_wizard_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(t.TEMPLATE_WIZARD_CANCELLED)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("atpl:vol:"))
async def wizard_volume_quick(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    current = await state.get_state()
    if current != AddTemplateStates.volume.state:
        await callback.answer()
        return
    try:
        volume = float(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if volume <= 0:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(volume_gb=volume)
    if callback.message:
        await _go_to_expiry_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddTemplateStates.volume)
async def wizard_volume_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        volume = float((message.text or "").replace(",", "."))
        if volume <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(volume_gb=volume)
    await _go_to_expiry_step(message, state)


@router.callback_query(F.data.startswith("atpl:exp:"))
async def wizard_expiry_quick(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    current = await state.get_state()
    if current != AddTemplateStates.expiry.state:
        await callback.answer()
        return
    try:
        days = int(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    except (ValueError, IndexError):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    if days < 0:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(expiry_days=days)
    if callback.message:
        await _go_to_name_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddTemplateStates.expiry)
async def wizard_expiry_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        days = int((message.text or "").strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer(t.INVALID_INPUT)
        return
    await state.update_data(expiry_days=days)
    await _go_to_name_step(message, state)


@router.callback_query(
    AddTemplateStates.name, F.data == "atpl:use_suggested_name"
)
async def wizard_use_suggested_name(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    suggested = data.get("suggested_name")
    if not suggested:
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return
    await state.update_data(name=suggested)
    if callback.message:
        await _go_to_confirm_step(callback.message, state)  # type: ignore[arg-type]
    await callback.answer()


@router.message(AddTemplateStates.name)
async def wizard_name_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        name = normalize_template_name(message.text or "")
    except InvalidTemplateError as e:
        await message.answer(str(e))
        return
    await state.update_data(name=name)
    await _go_to_confirm_step(message, state)


@router.callback_query(AddTemplateStates.confirm, F.data == "atpl:wiz_save")
async def wizard_save(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else None):
        return
    data = await state.get_data()
    required = ("name", "volume_gb", "expiry_days")
    if not all(k in data for k in required):
        await callback.answer(t.INVALID_INPUT, show_alert=True)
        return

    async with get_session_factory()() as session:
        repo = ServiceTemplateRepository(session)
        try:
            row = await repo.create(
                data["name"],
                data["volume_gb"],
                data["expiry_days"],
            )
        except InvalidTemplateError as e:
            await callback.answer(str(e), show_alert=True)
            return

    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            t.TEMPLATE_ADDED.format(
                id=row.id,
                name=row.name,
                volume_gb=row.volume_gb,
                expiry_label=expiry_label(row.expiry_days),
            )
        )
    await callback.answer()


@router.message(Command("del_template"))
async def del_template_hint(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return
    await message.answer(
        "برای حذف قالب از دکمه «قالب‌های سرویس» استفاده کنید و روی قالب موردنظر بزنید."
    )
