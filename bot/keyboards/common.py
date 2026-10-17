from datetime import datetime

from aiogram.enums import ButtonStyle
from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.keyboards import labels as L
from bot.utils.format_delivery import config_display_label
from bot.utils.format_traffic import (
    EXPIRY_EXPIRED,
    EXPIRY_SOON,
    service_status,
)
from bot.utils.report_format import format_report_button_label, usage_percent_int
from bot.utils.fa_text import RLM, fa_days, fa_digits, fa_gb, fa_toman, rtl
from db.models import (
    ClientRecord,
    GuestSalesConfig,
    Panel,
    Plan,
    Reseller,
    ServiceTemplate,
)
from services.client_volume import MIN_CLIENT_VOLUME_GB
from xui.client import VlessConfig

_TELEGRAM_CALLBACK_MAX = 64
SERVICES_PAGE_SIZE = 8


def reseller_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=L.CREATE_SERVICE),
                KeyboardButton(text=L.MY_SERVICES),
            ],
            [KeyboardButton(text=L.ACCOUNT_STATUS)],
        ],
        resize_keyboard=True,
    )


def guest_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=L.BUY_ACCOUNT, style=ButtonStyle.SUCCESS),
                KeyboardButton(text=L.MY_ACCOUNTS, style=ButtonStyle.PRIMARY),
            ],
            [KeyboardButton(text=L.MY_ORDERS), KeyboardButton(text=L.SUPPORT)],
        ],
        resize_keyboard=True,
    )


def admin_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=L.LIST_RESELLERS),
                KeyboardButton(text=L.SERVICE_TEMPLATES),
            ],
            [
                KeyboardButton(text=L.PANELS),
                KeyboardButton(text=L.SET_PANEL_RESELLER),
            ],
            [
                KeyboardButton(text=L.BOT_UPDATE),
                KeyboardButton(text=L.BACKUP),
            ],
            [
                KeyboardButton(text=L.BROADCAST),
            ],
            [
                KeyboardButton(text=L.GUEST_PLANS),
                KeyboardButton(text=L.GUEST_SALES_SETTINGS),
            ],
            [
                KeyboardButton(text=L.PREVIEW_GUEST_MODE),
            ],
            [
                KeyboardButton(text=L.ADMIN_HELP),
            ],
        ],
        resize_keyboard=True,
    )


def bot_update_menu_kb(*, github_enabled: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if github_enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📥 آپدیت از GitHub",
                    callback_data="upd:github",
                ),
                InlineKeyboardButton(
                    text="📎 آپلود ZIP",
                    callback_data="upd:manual",
                ),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📎 آپلود ZIP",
                    callback_data="upd:manual",
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=L.CANCEL, callback_data="upd:cancel_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_update_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ اعمال و ری‌استارت",
                    callback_data="upd:apply",
                ),
                InlineKeyboardButton(
                    text=L.CANCEL,
                    callback_data="upd:cancel",
                ),
            ],
        ]
    )


def backup_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💾 ساخت بک‌آپ الان",
                    callback_data="bkp:create",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📂 لیست بک‌آپ‌های محلی",
                    callback_data="bkp:list",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="♻️ بازیابی از فایل",
                    callback_data="bkp:restore",
                ),
            ],
            [
                InlineKeyboardButton(text=L.CANCEL, callback_data="bkp:cancel_menu"),
            ],
        ]
    )


def backup_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ اعمال و ری‌استارت",
                    callback_data="bkp:apply",
                ),
                InlineKeyboardButton(
                    text=L.CANCEL,
                    callback_data="bkp:cancel",
                ),
            ],
        ]
    )


def backup_list_kb(entries: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, label in entries:
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"bkp:dl:{index}",
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=L.BACK, callback_data="bkp:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=L.CONFIRM, callback_data="bc_confirm"),
                InlineKeyboardButton(text=L.CANCEL, callback_data="bc_cancel"),
            ],
        ]
    )


def panel_admin_hub_kb(panels: list[Panel]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in panels:
        label = L.panel_hub_row_label(p.id, p.name, is_active=p.is_active)
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"pnl:view:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.ADD_PANEL, callback_data="pnl:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_view_kb(panel_id: int, *, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.EDIT_PANEL,
                    callback_data=f"pnl:edit:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.active_toggle_label(is_active=is_active),
                    callback_data=f"pnl:toggle:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.LIST_INBOUNDS,
                    callback_data=f"pnl:inbounds:{panel_id}",
                ),
                InlineKeyboardButton(
                    text=L.BULK_INBOUNDS,
                    callback_data=f"pnl:bulk:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.INBOUND_HEALTH,
                    callback_data=f"pnl:health:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.DELETE_PANEL,
                    callback_data=f"pnl:del:{panel_id}",
                ),
            ],
            [InlineKeyboardButton(text=L.BACK, callback_data="pnl:hub")],
        ]
    )


def panel_bulk_inbounds_kb(
    panel_id: int,
    inbounds: list[dict],
    coverage: dict[int, tuple[int, int]],
    orphan_ids: list[int] | None = None,
) -> InlineKeyboardMarkup:
    """One row per inbound, showing how many resellers already hold it.

    Orphans — ids still referenced by reseller rows but no longer on the panel —
    are listed too. They are the whole reason this screen exists: without them
    an admin cannot clear a reference to a deleted inbound, which is what makes
    service creation fail with the panel's "record not found".
    """
    rows: list[list[InlineKeyboardButton]] = []
    for ib in inbounds[:25]:
        try:
            ib_id = int(ib.get("id", ib.get("inboundId", 0)))
        except (TypeError, ValueError):
            continue
        if not ib_id:
            continue
        have, total = coverage.get(ib_id, (0, 0))
        protocol = ib.get("protocol", "")
        port = ib.get("port", "")
        # Pure ASCII label: no Persian words mixed with the counters.
        label = f"#{ib_id} {protocol}:{port} — {have}/{total}"
        if len(label) > 40:
            label = label[:37] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"pnl:bulk:pick:{panel_id}:{ib_id}",
                )
            ]
        )
    for ib_id in (orphan_ids or [])[:10]:
        have, total = coverage.get(ib_id, (0, 0))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⚠️ #{ib_id} — {have}/{total}",
                    callback_data=f"pnl:bulk:pick:{panel_id}:{ib_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=L.BACK, callback_data=f"pnl:view:{panel_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_bulk_confirm_kb(
    panel_id: int, inbound_id: int, *, enable: bool
) -> InlineKeyboardMarkup:
    action = "on" if enable else "off"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.BULK_ADD_ALL if enable else L.BULK_REMOVE_ALL,
                    callback_data=f"pnl:bulk:go:{panel_id}:{inbound_id}:{action}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.CANCEL, callback_data=f"pnl:bulk:{panel_id}"
                ),
            ],
        ]
    )


def panel_edit_menu_kb(panel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.EDIT_PANEL_NAME,
                    callback_data=f"pnl:pev:name:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_PANEL_URL,
                    callback_data=f"pnl:pev:url:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_PANEL_TOKEN,
                    callback_data=f"pnl:pev:token:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_PANEL_SUB,
                    callback_data=f"pnl:pev:sub:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.BACK, callback_data=f"pnl:view:{panel_id}"
                ),
            ],
        ]
    )


def panel_edit_sub_kb(panel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.CLEAR_SUB_URL,
                    callback_data=f"pnl:sub_clear:{panel_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.CANCEL, callback_data=f"pnl:edit:{panel_id}"
                ),
            ],
        ]
    )


def panel_delete_confirm_kb(panel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE,
                    callback_data=f"pnl:del_yes:{panel_id}",
                ),
                InlineKeyboardButton(
                    text=L.NO, callback_data=f"pnl:view:{panel_id}"
                ),
            ],
        ]
    )


def panel_wizard_skip_sub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.SKIP_PUBLIC_SUB, callback_data="pnl:wiz_skip_sub"
                )
            ],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="pnl:wiz_cancel")],
        ]
    )


def panel_wizard_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.REGISTER_PANEL, callback_data="pnl:wiz_save"
                ),
                InlineKeyboardButton(text=L.CANCEL, callback_data="pnl:wiz_cancel"),
            ],
        ]
    )


def set_panel_reseller_kb(
    resellers: list[Reseller], panel_names: dict[int, str]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in resellers[:20]:
        name = r.display_name or str(r.telegram_id)
        p_name = panel_names.get(r.panel_id, f"#{r.panel_id}")
        label = f"{name} — پنل {p_name}"
        if len(label) > 40:
            label = label[:37] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rpnl:res:{r.telegram_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.CANCEL, callback_data="rpnl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_panel_pick_panel_kb(panels: list[Panel]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in panels:
        label = f"#{p.id} {p.name}"
        if len(label) > 35:
            label = label[:32] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rpnl:pan:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.CANCEL, callback_data="rpnl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_panel_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=L.CONFIRM, callback_data="rpnl:save"),
                InlineKeyboardButton(text=L.CANCEL, callback_data="rpnl:cancel"),
            ],
        ]
    )


def reseller_admin_hub_kb(
    resellers: list[Reseller],
    panel_names: dict[int, str],
    stats: dict[int, object],
) -> InlineKeyboardMarkup:
    """Reseller list, carrying the usage figures the report hub used to show.

    Labels stay pure ASCII (name is validated `[a-zA-Z0-9_-]+`), so packing the
    service count and usage percent here is bidi-safe in a way the old Persian
    summary lines were not.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for r in resellers[:20]:
        name = r.display_name or str(r.telegram_id)
        st = stats.get(r.telegram_id)
        client_count = st.client_count if st is not None else 0
        percent = (
            usage_percent_int(st.used_bytes, st.quota_bytes)
            if st is not None
            else None
        )
        label = format_report_button_label(
            name,
            is_active=r.is_active,
            client_count=client_count,
            percent=percent,
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rsl:view:{r.telegram_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.ADD_RESELLER, callback_data="rsl:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_view_kb(
    telegram_id: int, *, is_active: bool, can_change_panel: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=L.REFRESH,
                callback_data=f"rsl:refresh:{telegram_id}",
            ),
            InlineKeyboardButton(
                text=L.active_toggle_label(is_active=is_active),
                callback_data=f"rsl:toggle:{telegram_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=L.MANAGE_PANELS,
                callback_data=f"rsl:panels:{telegram_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=L.EDIT_RESELLER,
                callback_data=f"rsl:edit:{telegram_id}",
            ),
        ],
    ]
    if can_change_panel:
        rows.append(
            [
                InlineKeyboardButton(
                    text=L.CHANGE_PANEL,
                    callback_data=f"rsl:set_panel:{telegram_id}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=L.DELETE_RESELLER,
                callback_data=f"rsl:del:{telegram_id}",
            ),
        ],
    )
    rows.append([InlineKeyboardButton(text=L.BACK, callback_data="rsl:hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_delete_confirm_kb(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE_FULL,
                    callback_data=f"rsl:del_yes:{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=L.NO, callback_data=f"rsl:view:{telegram_id}"
                ),
            ],
        ]
    )


def reseller_wizard_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.NO_DISPLAY_NAME, callback_data="rsl:name_skip"
                )
            ],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="rsl:wiz_cancel")],
        ]
    )


def reseller_wizard_pick_panel_kb(panels: list[Panel]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in panels:
        label = f"#{p.id} {p.name}"
        if len(label) > 35:
            label = label[:32] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rsl:pan:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=L.CANCEL, callback_data="rsl:wiz_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_wizard_quota_kb() -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100)
    row = [
        InlineKeyboardButton(text=f"{v} GB", callback_data=f"rsl:quota:{v}")
        for v in volumes
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text=L.CANCEL, callback_data="rsl:wiz_cancel")],
        ]
    )


def _inbound_toggle_rows(
    inbounds: list[dict],
    selected: set[int],
    *,
    toggle_prefix: str,
    done_callback: str,
    cancel_callback: str,
    done_label: str = L.CONTINUE,
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for ib in inbounds[:25]:
        ib_id = int(ib.get("id", ib.get("inboundId", ib.get("inbound_id", 0))))
        if not ib_id:
            continue
        mark = "✓ " if ib_id in selected else ""
        protocol = ib.get("protocol", "")
        port = ib.get("port", "")
        label = f"{mark}#{ib_id} {protocol}:{port}".strip()
        if len(label) > 40:
            label = label[:37] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label or f"{mark}#{ib_id}",
                    callback_data=f"{toggle_prefix}{ib_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text=done_label, callback_data=done_callback),
            InlineKeyboardButton(text=L.CANCEL, callback_data=cancel_callback),
        ]
    )
    return rows


def reseller_wizard_inbounds_kb(
    inbounds: list[dict],
    selected: set[int],
    *,
    toggle_prefix: str = "rsl:ib:t:",
    done_callback: str = "rsl:ib:done",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=_inbound_toggle_rows(
            inbounds,
            selected,
            toggle_prefix=toggle_prefix,
            done_callback=done_callback,
            cancel_callback="rsl:wiz_cancel",
            done_label=L.CONTINUE,
        )
    )


def reseller_panel_list_kb(
    telegram_id: int,
    assignments: list,
    panel_labels: dict[int, str],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for a in assignments:
        name = panel_labels.get(a.panel_id, f"#{a.panel_id}")
        if len(name) > 28:
            name = name[:25] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=name,
                    callback_data=f"rsl:pview:{telegram_id}:{a.panel_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=L.ADD_PANEL_ASSIGNMENT,
                callback_data=f"rsl:padd:{telegram_id}",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text=L.BACK, callback_data=f"rsl:view:{telegram_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_panel_assignment_kb(
    telegram_id: int,
    panel_id: int,
    *,
    is_default: bool,
    can_remove: bool,
    assignment_is_active: bool = True,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=L.EDIT_RESELLER,
                callback_data=f"rsl:pedit:{telegram_id}:{panel_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=L.panel_create_toggle_label(allowed=assignment_is_active),
                callback_data=f"rsl:ptoggle:{telegram_id}:{panel_id}",
            ),
        ],
    ]
    if not is_default:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⭐ پنل پیش‌فرض",
                    callback_data=f"rsl:pdefault:{telegram_id}:{panel_id}",
                ),
            ]
        )
    if can_remove:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 حذف تخصیص",
                    callback_data=f"rsl:premove:{telegram_id}:{panel_id}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=L.BACK, callback_data=f"rsl:panels:{telegram_id}"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_panel_edit_menu_kb(
    telegram_id: int, panel_id: int
) -> InlineKeyboardMarkup:
    tid, pid = telegram_id, panel_id
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.EDIT_QUOTA,
                    callback_data=f"rsl:pev:quota:{tid}:{pid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_ADD_QUOTA,
                    callback_data=f"rsl:pev:addq:{tid}:{pid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.RESET_QUOTA_USAGE,
                    callback_data=f"rsl:pev:resetu:{tid}:{pid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.BACK,
                    callback_data=f"rsl:pview:{tid}:{pid}",
                ),
            ],
        ]
    )


def reseller_panel_add_pick_kb(
    panels: list[Panel], telegram_id: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in panels:
        label = f"#{p.id} {p.name}"
        if len(label) > 35:
            label = label[:32] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"rsl:padd_pan:{p.id}:{telegram_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=L.CANCEL, callback_data=f"rsl:panels:{telegram_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_panel_remove_confirm_kb(
    telegram_id: int, panel_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE,
                    callback_data=f"rsl:premove_yes:{telegram_id}:{panel_id}",
                ),
                InlineKeyboardButton(
                    text=L.NO,
                    callback_data=f"rsl:pview:{telegram_id}:{panel_id}",
                ),
            ],
        ]
    )


def create_pick_panel_kb(
    panels: list[tuple[int, str, float]]
) -> InlineKeyboardMarkup:
    """panels: (panel_id, name, remaining_gb)"""
    rows: list[list[InlineKeyboardButton]] = []
    for panel_id, name, remaining_gb in panels:
        label = f"{name} — {remaining_gb:.1f} GB"
        if len(label) > 40:
            label = label[:37] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"create:panel:{panel_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=L.CANCEL, callback_data="create:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_edit_menu_kb(telegram_id: int) -> InlineKeyboardMarkup:
    tid = telegram_id
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.EDIT_QUOTA,
                    callback_data=f"rsl:ev:quota:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_ADD_QUOTA,
                    callback_data=f"rsl:ev:addq:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_SUBTRACT_QUOTA,
                    callback_data=f"rsl:ev:subq:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.RESET_QUOTA_USAGE,
                    callback_data=f"rsl:ev:resetu:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_MAX_CLIENTS,
                    callback_data=f"rsl:ev:maxc:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_DISPLAY_NAME,
                    callback_data=f"rsl:ev:name:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_ALLOWED_INBOUNDS,
                    callback_data=f"rsl:ev:allow:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_ATTACH_INBOUNDS,
                    callback_data=f"rsl:ev:attach:{tid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.BACK, callback_data=f"rsl:view:{tid}"
                ),
            ],
        ]
    )


def reseller_edit_quota_kb(telegram_id: int) -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100)
    row = [
        InlineKeyboardButton(
            text=f"{v} GB", callback_data=f"rsl:eq:{v}:{telegram_id}"
        )
        for v in volumes
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [
                InlineKeyboardButton(
                    text=L.CANCEL,
                    callback_data=f"rsl:edit_cancel:{telegram_id}",
                ),
            ],
        ]
    )


def reseller_edit_add_quota_kb(telegram_id: int) -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100, 500)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for v in volumes:
        row.append(
            InlineKeyboardButton(
                text=f"+{v} GB", callback_data=f"rsl:eaq:{v}:{telegram_id}"
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text=L.CANCEL,
                callback_data=f"rsl:edit_cancel:{telegram_id}",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_edit_subtract_quota_kb(telegram_id: int) -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100, 500)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for v in volumes:
        row.append(
            InlineKeyboardButton(
                text=f"-{v} GB", callback_data=f"rsl:esq:{v}:{telegram_id}"
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text=L.CANCEL,
                callback_data=f"rsl:edit_cancel:{telegram_id}",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_reset_quota_confirm_kb(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_RESET,
                    callback_data=f"rsl:resetu:yes:{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=L.NO,
                    callback_data=f"rsl:resetu:no:{telegram_id}",
                ),
            ],
        ]
    )


def reseller_edit_max_clients_kb(telegram_id: int) -> InlineKeyboardMarkup:
    counts = (1, 5, 10, 20, 50)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for n in counts:
        row.append(
            InlineKeyboardButton(
                text=str(n), callback_data=f"rsl:emc:set:{n}:{telegram_id}"
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text=L.UNLIMITED_MAX_CLIENTS,
                callback_data=f"rsl:emc:clear:{telegram_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=L.CANCEL,
                callback_data=f"rsl:edit_cancel:{telegram_id}",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_edit_inbounds_kb(
    inbounds: list[dict], selected: set[int], telegram_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=_inbound_toggle_rows(
            inbounds,
            selected,
            toggle_prefix="rsl:eib:t:",
            done_callback="rsl:eib:done",
            cancel_callback=f"rsl:edit_cancel:{telegram_id}",
            done_label=L.SAVE,
        )
    )


def reseller_edit_attach_inbounds_kb(
    inbound_ids: list[int], selected: set[int], telegram_id: int
) -> InlineKeyboardMarkup:
    inbounds = [{"id": i, "protocol": "", "port": ""} for i in inbound_ids]
    return reseller_edit_inbounds_kb(inbounds, selected, telegram_id)


def reseller_wizard_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.REGISTER_RESELLER, callback_data="rsl:wiz_save"
                ),
                InlineKeyboardButton(text=L.CANCEL, callback_data="rsl:wiz_cancel"),
            ],
        ]
    )


def template_admin_hub_kb(templates: list[ServiceTemplate]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for tpl in templates:
        label = tpl.name if len(tpl.name) <= 28 else tpl.name[:25] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 {label}",
                    callback_data=f"atpl:del:{tpl.id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=L.ADD_TEMPLATE, callback_data="atpl:add")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def template_delete_confirm_kb(template_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE_TEMPLATE,
                    callback_data=f"atpl:del_yes:{template_id}",
                ),
                InlineKeyboardButton(text=L.NO, callback_data="atpl:hub"),
            ],
        ]
    )


def template_wizard_volume_kb() -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50, 100)
    row = [
        InlineKeyboardButton(text=f"{v} GB", callback_data=f"atpl:vol:{v}")
        for v in volumes
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text=L.CANCEL, callback_data="atpl:wiz_cancel")],
        ]
    )


def template_wizard_expiry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="7 روز", callback_data="atpl:exp:7"),
                InlineKeyboardButton(text="30 روز", callback_data="atpl:exp:30"),
                InlineKeyboardButton(text="90 روز", callback_data="atpl:exp:90"),
            ],
            [
                InlineKeyboardButton(text="180 روز", callback_data="atpl:exp:180"),
                InlineKeyboardButton(text="365 روز", callback_data="atpl:exp:365"),
            ],
            [InlineKeyboardButton(text=L.UNLIMITED_EXPIRY, callback_data="atpl:exp:0")],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="atpl:wiz_cancel")],
        ]
    )


def template_wizard_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.USE_SUGGESTED_NAME,
                    callback_data="atpl:use_suggested_name",
                )
            ],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="atpl:wiz_cancel")],
        ]
    )


def template_wizard_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.REGISTER_TEMPLATE, callback_data="atpl:wiz_save"
                ),
                InlineKeyboardButton(text=L.CANCEL, callback_data="atpl:wiz_cancel"),
            ],
        ]
    )


def plan_admin_hub_kb(plans: list[Plan]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in plans:
        label = p.name if len(p.name) <= 24 else p.name[:21] + "..."
        status = "🟢" if p.is_active else "🔴"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {label}",
                    callback_data=f"aplan:view:{p.id}",
                ),
            ]
        )
    rows.append([InlineKeyboardButton(text=L.ADD_PLAN, callback_data="aplan:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_detail_kb(plan: Plan) -> InlineKeyboardMarkup:
    pid = plan.id
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=L.PLAN_EDIT_NAME, callback_data=f"aplan:edit:name:{pid}"),
                InlineKeyboardButton(text=L.PLAN_EDIT_PRICE, callback_data=f"aplan:edit:price:{pid}"),
            ],
            [
                InlineKeyboardButton(text=L.PLAN_EDIT_VOLUME, callback_data=f"aplan:edit:volume:{pid}"),
                InlineKeyboardButton(text=L.PLAN_EDIT_DAYS, callback_data=f"aplan:edit:days:{pid}"),
            ],
            [
                InlineKeyboardButton(text=L.PLAN_MOVE_UP, callback_data=f"aplan:move:up:{pid}"),
                InlineKeyboardButton(text=L.PLAN_MOVE_DOWN, callback_data=f"aplan:move:down:{pid}"),
            ],
            [
                InlineKeyboardButton(
                    text=L.active_toggle_label(is_active=plan.is_active),
                    callback_data=f"aplan:toggle:{pid}",
                ),
                InlineKeyboardButton(text=L.DELETE, callback_data=f"aplan:del:{pid}"),
            ],
            [InlineKeyboardButton(text=L.BACK, callback_data="aplan:hub")],
        ]
    )


def plan_edit_cancel_kb(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=L.CANCEL, callback_data=f"aplan:view:{plan_id}")]
        ]
    )


def plan_delete_confirm_kb(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE,
                    callback_data=f"aplan:del_yes:{plan_id}",
                ),
                InlineKeyboardButton(text=L.NO, callback_data="aplan:hub"),
            ],
        ]
    )


def plan_wizard_volume_kb() -> InlineKeyboardMarkup:
    volumes = (20, 30, 50, 100, 200)
    row = [
        InlineKeyboardButton(text=f"{v} GB", callback_data=f"aplan:vol:{v}")
        for v in volumes
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text=L.CANCEL, callback_data="aplan:wiz_cancel")],
        ]
    )


def plan_wizard_expiry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="7 روز", callback_data="aplan:exp:7"),
                InlineKeyboardButton(text="30 روز", callback_data="aplan:exp:30"),
                InlineKeyboardButton(text="90 روز", callback_data="aplan:exp:90"),
            ],
            [
                InlineKeyboardButton(text="180 روز", callback_data="aplan:exp:180"),
                InlineKeyboardButton(text="365 روز", callback_data="aplan:exp:365"),
            ],
            [InlineKeyboardButton(text=L.UNLIMITED_EXPIRY, callback_data="aplan:exp:0")],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="aplan:wiz_cancel")],
        ]
    )


def plan_wizard_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.USE_SUGGESTED_NAME,
                    callback_data="aplan:use_suggested_name",
                )
            ],
            [InlineKeyboardButton(text=L.CANCEL, callback_data="aplan:wiz_cancel")],
        ]
    )


def plan_wizard_price_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=L.CANCEL, callback_data="aplan:wiz_cancel")],
        ]
    )


def plan_wizard_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.REGISTER_PLAN, callback_data="aplan:wiz_save"
                ),
                InlineKeyboardButton(text=L.CANCEL, callback_data="aplan:wiz_cancel"),
            ],
        ]
    )


def guest_plan_button_label(plan: Plan) -> str:
    # RTL-safe: Persian digits/units and a leading RLM (see bot/utils/fa_text.py).
    name = plan.name if len(plan.name) <= 20 else plan.name[:19] + "…"
    # The name may be Latin or a flag (bidi class L); the RLM after it keeps it
    # from merging with the number that follows.
    return rtl(
        f"{name}{RLM} | {fa_gb(plan.volume_gb)} | {fa_days(plan.expiry_days)}"
        f" | {fa_toman(plan.price_toman)} تومان"
    )


def guest_plan_picker_kb(
    plans: list[Plan], *, renew_record_id: int | None = None
) -> InlineKeyboardMarkup:
    """Plan buttons for a new purchase, or for renewing renew_record_id."""
    eligible = [p for p in plans if p.volume_gb >= MIN_CLIENT_VOLUME_GB]
    rows: list[list[InlineKeyboardButton]] = []
    for p in eligible:
        cb = (
            f"gplan:{p.id}"
            if renew_record_id is None
            else f"grenew:{renew_record_id}:{p.id}"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=guest_plan_button_label(p),
                    callback_data=cb,
                    style=ButtonStyle.SUCCESS,
                )
            ]
        )
    if renew_record_id is not None:
        rows.append(
            [InlineKeyboardButton(text=L.BACK, callback_data=f"gacc:v:{renew_record_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def guest_payment_kb(card_number: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    card = (card_number or "").strip()
    if card:
        rows.append(
            [
                InlineKeyboardButton(
                    text=L.GUEST_COPY_CARD,
                    copy_text=CopyTextButton(text=card.replace(" ", "").replace("-", "")),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=L.GUEST_CANCEL_PAYMENT,
                callback_data="gpay:cancel",
                style=ButtonStyle.DANGER,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def guest_my_accounts_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.MY_ACCOUNTS,
                    callback_data="gacc:list",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        ]
    )


def _guest_account_label(record: ClientRecord) -> str:
    expiry_ms = int(record.expiry_time or 0)
    if expiry_ms <= 0:
        expiry = "نامحدود"
    else:
        expiry = fa_digits(datetime.fromtimestamp(expiry_ms / 1000).strftime("%Y/%m/%d"))
    return rtl(f"🔹 اکانت {fa_digits(record.id)} | انقضا: {expiry}")


def guest_accounts_list_kb(records: list[ClientRecord]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_guest_account_label(r), callback_data=f"gacc:v:{r.id}"
            )
        ]
        for r in records
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def guest_account_detail_kb(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.GUEST_LINK_QR,
                    callback_data=f"gacc:link:{record_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=L.GUEST_RENEW,
                    callback_data=f"gacc:renew:{record_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [InlineKeyboardButton(text=L.BACK, callback_data="gacc:back")],
        ]
    )


def guest_order_review_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.GUEST_APPROVE_ORDER,
                    callback_data=f"gorder:approve:{order_id}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text=L.GUEST_REJECT_ORDER,
                    callback_data=f"gorder:reject:{order_id}",
                    style=ButtonStyle.DANGER,
                ),
            ]
        ]
    )


def guest_config_hub_kb(config: GuestSalesConfig) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.CHANGE_GUEST_PANEL, callback_data="gcfg:pick_panel"
                )
            ],
            [
                InlineKeyboardButton(
                    text=L.CHANGE_CARD_NUMBER, callback_data="gcfg:card_number"
                ),
                InlineKeyboardButton(
                    text=L.CHANGE_CARD_HOLDER, callback_data="gcfg:card_holder"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.guest_sales_toggle_label(is_enabled=config.is_enabled),
                    callback_data="gcfg:toggle",
                )
            ],
        ]
    )


def guest_config_pick_panel_kb(panels: list[Panel]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in panels:
        label = f"#{p.id} {p.name}"
        if len(label) > 35:
            label = label[:32] + "..."
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"gcfg:pan:{p.id}")]
        )
    rows.append([InlineKeyboardButton(text=L.CANCEL, callback_data="gcfg:wiz_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def guest_config_inbounds_kb(
    inbounds: list[dict], selected: set[int]
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=_inbound_toggle_rows(
            inbounds,
            selected,
            toggle_prefix="gcfg:ib:t:",
            done_callback="gcfg:ib:done",
            cancel_callback="gcfg:wiz_cancel",
            done_label=L.CONTINUE,
        )
    )


def create_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=L.CANCEL, callback_data="create:cancel")],
        ]
    )


def service_search_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=L.CANCEL, callback_data="svc:search:cancel")],
        ]
    )


def template_picker_kb(templates: list[ServiceTemplate]) -> InlineKeyboardMarkup:
    eligible = [tpl for tpl in templates if tpl.volume_gb >= MIN_CLIENT_VOLUME_GB]
    rows = [
        [InlineKeyboardButton(text=tpl.name, callback_data=f"tpl:{tpl.id}")]
        for tpl in eligible
    ]
    rows.append(
        [InlineKeyboardButton(text=L.MANUAL_ENTRY, callback_data="create:manual")]
    )
    rows.append(
        [InlineKeyboardButton(text=L.CANCEL, callback_data="create:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renew_source_kb(templates: list[ServiceTemplate]) -> InlineKeyboardMarkup:
    """Template picker for renewal — `rtpl:` so it never collides with create's `tpl:`."""
    eligible = [tpl for tpl in templates if tpl.volume_gb >= MIN_CLIENT_VOLUME_GB]
    rows = [
        [InlineKeyboardButton(text=tpl.name, callback_data=f"rtpl:{tpl.id}")]
        for tpl in eligible
    ]
    rows.append([InlineKeyboardButton(text=L.RENEW_MANUAL, callback_data="rman")])
    rows.append([InlineKeyboardButton(text=L.CANCEL, callback_data="rcnl")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renew_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=L.CONFIRM, callback_data="rcfm"),
                InlineKeyboardButton(text=L.CANCEL, callback_data="rcnl"),
            ],
        ]
    )


def renew_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=L.CANCEL, callback_data="rcnl")],
        ]
    )


def client_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.RANDOM_NAME, callback_data="create:auto_name"
                )
            ],
            [
                InlineKeyboardButton(
                    text=L.CANCEL, callback_data="create:cancel"
                )
            ],
        ]
    )


def confirm_create_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=L.CONFIRM, callback_data="create:confirm"),
                InlineKeyboardButton(text=L.CANCEL, callback_data="create:cancel"),
            ]
        ]
    )


_EXPIRY_ICONS = {EXPIRY_EXPIRED: "❌ ", EXPIRY_SOON: "⚠️ "}


def service_button_label(
    record: ClientRecord, usage: dict[int, tuple[int, int]] | None = None
) -> str:
    """Icon + email only.

    The icon reflects whichever runs out first, time or volume — a service can
    burn through its traffic weeks before its expiry date.

    Never put digits here: Telegram's bidi renderer reorders numeric runs on an
    RTL line, which is what garbled the plan listings before (commit 0d9632d).
    Counts belong in the multi-line message above the list.
    """
    used, total = (usage or {}).get(record.id, (None, 0))
    status = service_status(int(record.expiry_time or 0), used, total)
    icon = _EXPIRY_ICONS.get(status, "")
    email = record.email
    short = email if len(email) <= 28 else email[:25] + "..."
    return f"{icon}{short}"


def service_list_kb(
    records: list[ClientRecord],
    *,
    page: int = 0,
    query: str | None = None,
    usage: dict[int, tuple[int, int]] | None = None,
) -> InlineKeyboardMarkup:
    total = len(records)
    total_pages = max(1, (total + SERVICES_PAGE_SIZE - 1) // SERVICES_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * SERVICES_PAGE_SIZE
    chunk = records[start : start + SERVICES_PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for record in chunk:
        rows.append(
            [
                InlineKeyboardButton(
                    text=service_button_label(record, usage),
                    callback_data=f"svc:{record.id}",
                )
            ]
        )

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text=L.PREV_PAGE, callback_data=f"svc:pg:{page - 1}"
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=f"svc:pg:{page}",
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text=L.NEXT_PAGE, callback_data=f"svc:pg:{page + 1}"
                )
            )
        rows.append(nav)

    if query:
        rows.append(
            [
                InlineKeyboardButton(text=L.SEARCH, callback_data="svc:search"),
                InlineKeyboardButton(
                    text=L.CLEAR_SEARCH, callback_data="svc:search:clear"
                ),
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text=L.SEARCH, callback_data="svc:search")]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def expiry_mode_kb(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.ADD_DAYS, callback_data=f"exp_add:{record_id}"
                ),
                InlineKeyboardButton(
                    text=L.NEW_DATE, callback_data=f"exp_date:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.UNLIMITED_EXPIRY, callback_data=f"exp_unlim:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.CANCEL, callback_data=f"exp_cancel:{record_id}"
                ),
            ],
        ]
    )


def add_traffic_volume_kb(record_id: int) -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50)
    rows = [
        [
            InlineKeyboardButton(
                text=f"+{v} GB", callback_data=f"traf_vol:{v}"
            )
            for v in volumes[:2]
        ],
        [
            InlineKeyboardButton(
                text=f"+{v} GB", callback_data=f"traf_vol:{v}"
            )
            for v in volumes[2:]
        ],
        [
            InlineKeyboardButton(
                text=L.MANUAL_ENTRY, callback_data="traf_custom"
            ),
        ],
        [
            InlineKeyboardButton(
                text=L.CANCEL, callback_data=f"traf_cancel:{record_id}"
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_traffic_confirm_kb(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.CONFIRM, callback_data="traf_confirm"
                ),
                InlineKeyboardButton(
                    text=L.CANCEL, callback_data=f"traf_cancel:{record_id}"
                ),
            ],
        ]
    )


def reduce_traffic_volume_kb(record_id: int) -> InlineKeyboardMarkup:
    volumes = (5, 10, 20, 50)
    rows = [
        [
            InlineKeyboardButton(
                text=f"-{v} GB", callback_data=f"trafd_vol:{v}"
            )
            for v in volumes[:2]
        ],
        [
            InlineKeyboardButton(
                text=f"-{v} GB", callback_data=f"trafd_vol:{v}"
            )
            for v in volumes[2:]
        ],
        [
            InlineKeyboardButton(
                text=L.MANUAL_ENTRY, callback_data="trafd_custom"
            ),
        ],
        [
            InlineKeyboardButton(
                text=L.CANCEL, callback_data=f"trafd_cancel:{record_id}"
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reduce_traffic_confirm_kb(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.CONFIRM, callback_data="trafd_confirm"
                ),
                InlineKeyboardButton(
                    text=L.CANCEL, callback_data=f"trafd_cancel:{record_id}"
                ),
            ],
        ]
    )


def delete_confirm_kb(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_DELETE_SERVICE,
                    callback_data=f"del_confirm:{record_id}",
                ),
                InlineKeyboardButton(
                    text=L.NO, callback_data=f"del_cancel:{record_id}"
                ),
            ],
        ]
    )


def service_edit_kb(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.ADD_TRAFFIC, callback_data=f"traf:{record_id}"
                ),
                InlineKeyboardButton(
                    text=L.REDUCE_TRAFFIC, callback_data=f"trafd:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.CHANGE_EXPIRY, callback_data=f"exp:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_NAME, callback_data=f"edit_name:{record_id}"
                ),
                InlineKeyboardButton(
                    text=L.EDIT_SUB_LINK, callback_data=f"edit_sub:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_LIMIT_IP, callback_data=f"edit_limit:{record_id}"
                ),
                InlineKeyboardButton(
                    text=L.EDIT_COMMENT, callback_data=f"edit_comment:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.BACK, callback_data=f"edit_back:{record_id}"
                )
            ],
        ]
    )


def sub_regen_confirm_kb(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.YES_REGEN_SUB, callback_data=f"sub_confirm:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.NO, callback_data=f"edit_back_menu:{record_id}"
                ),
            ],
        ]
    )


def _qr_button_label(email: str, cfg: VlessConfig, index: int) -> str:
    label = config_display_label(email, cfg.remark)
    if len(label) > 24:
        label = label[:21] + "..."
    return f"📲 QR {label}"


def _guest_qr_callback_data(email: str, index: int) -> str:
    data = f"gqr:{email}:{index}"
    if len(data) > _TELEGRAM_CALLBACK_MAX:
        raise ValueError("callback_data too long for QR button")
    return data


def guest_vless_qr_kb(email: str, configs: list[VlessConfig]) -> InlineKeyboardMarkup:
    rows = []
    for i, cfg in enumerate(configs):
        try:
            cb = _guest_qr_callback_data(email, i)
        except ValueError:
            continue
        rows.append(
            [InlineKeyboardButton(text=_qr_button_label(email, cfg, i), callback_data=cb)]
        )
    rows.append(guest_my_accounts_kb().inline_keyboard[0])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_detail_kb(record_id: int, *, enabled: bool = True) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.LINK_AND_QR, callback_data=f"linkqr:{record_id}"
                ),
                InlineKeyboardButton(
                    text=L.TRAFFIC, callback_data=f"traffic:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.RENEW_SERVICE, callback_data=f"renew:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.EDIT_SERVICE, callback_data=f"edit:{record_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=L.active_toggle_label(is_active=enabled),
                    callback_data=(
                        f"disable:{record_id}" if enabled else f"enable:{record_id}"
                    ),
                )
            ],
            [InlineKeyboardButton(text=L.DELETE, callback_data=f"del:{record_id}")],
            [InlineKeyboardButton(text=L.BACK, callback_data="svc:back")],
        ]
    )
