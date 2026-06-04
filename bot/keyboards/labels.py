"""Single source of truth for reply/inline button labels (with emoji)."""

# Reply keyboard — admin
LIST_RESELLERS = "📋 لیست ریسلرها"
REPORTS = "📈 گزارش‌گیری"
SERVICE_TEMPLATES = "📐 قالب‌های سرویس"
SET_PANEL_RESELLER = "🔄 تغییر پنل ریسلر"
PANELS = "🖥 پنل‌ها"
ADMIN_HELP = "❓ راهنمای ادمین"
BOT_UPDATE = "⬆️ آپدیت ربات"

# Reply keyboard — reseller
CREATE_SERVICE = "✨ ساخت سرویس"
MY_SERVICES = "📱 سرویس‌های من"
ACCOUNT_STATUS = "👤 وضعیت حساب"

# Common actions
BACK = "◀️ بازگشت"
REFRESH = "🔄 بروزرسانی"
CANCEL = "❌ لغو"
CONFIRM = "✅ تأیید"
YES_DELETE = "✅ بله، حذف"
YES_DELETE_FULL = "✅ بله، حذف کامل"
YES_DELETE_TEMPLATE = "✅ بله، حذف شود"
YES_DELETE_SERVICE = "✅ بله، حذف کن"
YES_RESET = "✅ بله، ریست کن"
NO = "↩️ خیر"
SAVE = "💾 ذخیره"
CONTINUE = "➡️ ادامه"

# Add / register
ADD_PANEL = "➕ افزودن پنل"
ADD_RESELLER = "➕ افزودن ریسلر"
ADD_TEMPLATE = "➕ افزودن قالب جدید"
REGISTER_PANEL = "✅ ثبت پنل"
REGISTER_TEMPLATE = "✅ ثبت قالب"
REGISTER_RESELLER = "✅ ثبت ریسلر"

# Panel
DELETE_PANEL = "🗑 حذف پنل"
LIST_INBOUNDS = "🔌 لیست اینباندها"
SKIP_PUBLIC_SUB = "⏭ بدون آدرس ساب عمومی"

# Reseller management
EDIT_RESELLER = "✏️ ویرایش ریسلر"
CHANGE_PANEL = "🔄 تغییر پنل"
DELETE_RESELLER = "🗑 حذف ریسلر"
NO_DISPLAY_NAME = "⏭ بدون نام"
UNLIMITED_MAX_CLIENTS = "♾ نامحدود (حذف محدودیت)"

# Reseller edit menu
EDIT_QUOTA = "📊 سقف حجم (GB)"
EDIT_ADD_QUOTA = "➕ افزودن سقف"
RESET_QUOTA_USAGE = "🔄 ریست مصرف (پکیج جدید)"
EDIT_MAX_CLIENTS = "🔢 سقف تعداد سرویس"
EDIT_DISPLAY_NAME = "🏷 نام نمایشی"
EDIT_ALLOWED_INBOUNDS = "🔌 اینباندهای مجاز"
EDIT_ATTACH_INBOUNDS = "🔗 اینباندهای متصل"

# Template wizard
USE_SUGGESTED_NAME = "💡 استفاده از نام پیشنهادی"
UNLIMITED_EXPIRY = "♾ نامحدود"

# Service creation / detail
MANUAL_ENTRY = "⌨️ ورود دستی"
RANDOM_NAME = "🎲 نام تصادفی"
LINK = "🔗 لینک"
TRAFFIC = "📈 ترافیک"
QR_CONFIG = "📲 QR کانفیگ"
CHANGE_EXPIRY = "📅 تغییر انقضا"
EDIT_SERVICE = "✏️ ویرایش سرویس"
DELETE = "🗑 حذف"
RESET_TRAFFIC = "🔄 ریست ترافیک"
EDIT_LIMIT_IP = "🔢 limitIp"
EDIT_COMMENT = "💬 کامنت"
ADD_DAYS = "➕ افزودن روز"
NEW_DATE = "📅 تاریخ جدید"


def active_toggle_label(*, is_active: bool) -> str:
    return "⏸ غیرفعال کردن" if is_active else "🔛 فعال کردن"


def reseller_hub_row_label(
    name: str, panel_name: str, *, is_active: bool, max_len: int = 40
) -> str:
    dot = "🟢" if is_active else "🔴"
    label = f"{dot} {name} — {panel_name}"
    if len(label) > max_len:
        label = label[: max_len - 3] + "..."
    return label


def panel_hub_row_label(
    panel_id: int, name: str, *, is_active: bool, max_len: int = 40
) -> str:
    dot = "🟢" if is_active else "🔴"
    status = "فعال" if is_active else "غیرفعال"
    label = f"{dot} #{panel_id} {name} ({status})"
    if len(label) > max_len:
        label = label[: max_len - 3] + "..."
    return label
