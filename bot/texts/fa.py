WELCOME_RESELLER = (
    "سلام{display_name}!\n\n"
    "پنل: {panel_name} (#{panel_id})\n"
    "سقف حجم: {quota_gb} GB\n"
    "مصرف‌شده (تخصیص): {used_gb} GB\n"
    "باقی‌مانده: {remaining_gb} GB\n"
    "تعداد سرویس: {client_count}\n"
    "سقف تعداد سرویس: {max_clients_line}\n"
    "{inbounds_summary}"
)

NOT_RESELLER = "شما به‌عنوان ریسلر ثبت نشده‌اید. با ادمین تماس بگیرید."

ADMIN_MENU = (
    "پنل ادمین\n\n"
    "برای دیدن همه دستورات، در چت `/` را بزنید.\n\n"
    "افزودن ریسلر (یک پیام):\n"
    "`5266810479 ali 1 100 1` — آیدی، نام، شماره پنل، سقف GB، اینباند\n"
    "بدون نام: `123456789 1 100 1` — آیدی، پنل، سقف، اینباند\n"
    "فرمت قدیم (پنل 1): `123456789 100 1`\n\n"
    "نمونه دستورات:\n"
    "`/panels` — مدیریت پنل‌های 3x-ui\n"
    "`/list_inbounds 1` — اینباند پنل شماره 1\n"
    "`/set_panel 123456789 2` — تغییر پنل ریسلر (بدون سرویس)\n"
    "`/set_quota 123456789 200`\n"
    "`/templates` — قالب‌های ساخت سرویس"
)

RESELLER_ADDED = (
    "ریسلر {label} با سقف {quota_gb} GB ثبت شد.\n"
    "پنل: {panel_name} (#{panel_id})\n"
    "مجاز: {allowed_inbounds}\n"
    "متصل هنگام ساخت: {attach_inbounds}"
)

NO_PANEL_ACCESS = (
    "پنل اختصاصی شما در دسترس نیست. با ادمین تماس بگیرید."
)
SERVICE_NOT_FOUND = "سرویس یافت نشد."
SERVICE_PANEL_UNAVAILABLE = (
    "پنل سرویس (#{panel_id}) در دسترس نیست (غیرفعال یا قطع). با ادمین تماس بگیرید."
)
NO_ACCESSIBLE_SERVICES = (
    "سرویس فعالی روی پنل‌های در دسترس ندارید. با ادمین تماس بگیرید."
)

PANEL_LIST_HEADER = "پنل‌های 3x-ui:"
PANEL_LIST_EMPTY = "پنلی ثبت نشده است."
PANEL_HUB_HINT = "برای افزودن پنل، «افزودن پنل» را بزنید."
PANEL_NOT_FOUND = "پنل یافت نشد."
PANEL_ADDED = "پنل #{id} ثبت شد: {name}\n{base_url}"
PANEL_DELETED = "پنل #{id} حذف شد."
PANEL_DELETE_CONFIRM = "حذف پنل #{id} ({name})؟"
PANEL_WIZARD_NAME = "نام پنل را وارد کنید (مثلاً پنل اروپا):"
PANEL_WIZARD_URL = (
    "آدرس پنل را وارد کنید:\n"
    "• https://host:2053 یا http://host:2053\n"
    "• یا فقط host:2053 (پیش‌فرض https)"
)
PANEL_WIZARD_TOKEN = "توکن API پنل را وارد کنید:"
PANEL_WIZARD_SUB = (
    "آدرس پایه ساب عمومی را وارد کنید:\n"
    "• https://sub.example.com:2096/save یا http://...\n"
    "• یا فقط host:2096/save (پیش‌فرض https)\n"
    "یا «بدون آدرس ساب عمومی» را بزنید."
)
PANEL_WIZARD_CONFIRM = (
    "تأیید ثبت پنل:\n"
    "نام: {name}\n"
    "آدرس: {base_url}\n"
    "ساب: {sub_public_url}\n\n"
    "پس از تأیید اتصال تست می‌شود."
)
PANEL_WIZARD_CANCELLED = "افزودن پنل لغو شد."
PANEL_AUTH_FAILED = "اتصال به پنل ناموفق بود:\n{error}"
PANEL_SET_FOR_RESELLER = (
    "پنل ریسلر {label} به {panel_name} (#{panel_id}) تغییر کرد."
)
PANEL_SET_UNCHANGED = "پنل ریسلر {label} از قبل روی {panel_name} (#{panel_id}) است."
PANEL_SET_BLOCKED_HAS_CLIENTS = (
    "ریسلر {label} الان {client_count} سرویس دارد.\n"
    "برای تغییر پنل ابتدا همه سرویس‌ها را حذف کنید."
)
PANEL_SET_WIZARD_PICK_RESELLER = "ریسلری را برای تغییر پنل انتخاب کنید:"
PANEL_SET_WIZARD_PICK_PANEL = (
    "ریسلر: {label}\n"
    "پنل فعلی: {current_panel_name} (#{current_panel_id})\n"
    "سرویس: {client_count}\n\n"
    "پنل جدید را انتخاب کنید:"
)
PANEL_SET_WIZARD_CONFIRM = (
    "تأیید تغییر پنل:\n"
    "ریسلر: {label}\n"
    "از: {old_panel_name} (#{old_panel_id})\n"
    "به: {new_panel_name} (#{new_panel_id})\n\n"
    "ادامه می‌دهید؟"
)
PANEL_SET_WIZARD_CANCELLED = "تغییر پنل لغو شد."
PANEL_SET_NO_RESELLERS = "ریسلری ثبت نشده است."
PANEL_SET_NO_PANELS = "پنل فعالی برای انتخاب وجود ندارد."
ALLOWED_INBOUNDS_UPDATED = (
    "اینباندهای مجاز ریسلر {label} به {allowed_inbounds} تغییر کرد.\n"
    "متصل هنگام ساخت: {attach_inbounds}{warning}"
)
ATTACH_INBOUNDS_UPDATED = (
    "اینباندهای متصل ریسلر {label} به {attach_inbounds} تنظیم شد."
)
QUOTA_UPDATED = "سقف ریسلر {label} به {quota_gb} GB تغییر کرد."
MAX_CLIENTS_UPDATED = (
    "سقف تعداد سرویس ریسلر {label} به {max_clients} تنظیم شد.{warning}"
)
MAX_CLIENTS_CLEARED = "محدودیت تعداد سرویس برای ریسلر {label} برداشته شد."
NAME_UPDATED = "نام ریسلر به {label} تغییر کرد."
RESELLER_DISABLED = "ریسلر {label} غیرفعال شد."
RESELLER_ENABLED = "ریسلر {label} فعال شد."

RESELLER_LIST_HEADER = "ریسلرها:"
RESELLER_LIST_EMPTY = "ریسلری ثبت نشده است."
RESELLER_HUB_HINT = (
    "روی هر ریسلر بزنید برای مدیریت؛ «افزودن ریسلر» برای ویزارد ثبت."
)
RESELLER_VIEW_DETAIL = (
    "ریسلر: {label}\n"
    "وضعیت: {status}\n"
    "پنل: {panel_name} (#{panel_id})\n"
    "سقف: {quota_gb} GB | استفاده: {used_gb} GB | باقی: {remaining_gb} GB\n"
    "سرویس: {client_count} | حداکثر سرویس: {max_clients_line}\n"
    "مجاز: {allowed_inbounds}\n"
    "متصل هنگام ساخت: {attach_inbounds}"
)
RESELLER_EDIT_MENU = "ویرایش ریسلر {label} — گزینه را انتخاب کنید:"
RESELLER_EDIT_QUOTA_PROMPT = (
    "سقف حجم (GB) برای {label}:\nیکی از دکمه‌ها را بزنید یا عدد بنویسید:"
)
RESELLER_EDIT_NAME_PROMPT = (
    "نام نمایشی جدید برای {label} (a-z 0-9 _ -):"
)
RESELLER_EDIT_MAX_CLIENTS_PROMPT = (
    "سقف تعداد سرویس برای {label}:\n"
    "یکی از دکمه‌ها را بزنید، عدد بنویسید، یا «نامحدود»."
)
RESELLER_EDIT_ALLOW_PROMPT = (
    "اینباندهای مجاز — پنل #{panel_id}:\n"
    "روی هر اینباند بزنید (انتخاب/لغو)؛ سپس «ذخیره»."
)
RESELLER_EDIT_ATTACH_PROMPT = (
    "اینباندهای متصل هنگام ساخت (زیرمجموعهٔ مجاز):\n"
    "روی هر مورد بزنید؛ سپس «ذخیره»."
)
RESELLER_EDIT_INBOUNDS_NONE = "حداقل یک اینباند انتخاب کنید."
RESELLER_EDIT_ATTACH_EMPTY_ALLOWED = "ابتدا اینباندهای مجاز را تنظیم کنید."
RESELLER_DELETE_CONFIRM = "حذف کامل ریسلر {label} از دیتابیس؟\nاین عمل برگشت‌پذیر نیست."
RESELLER_DELETED = "ریسلر {label} حذف شد."
RESELLER_DELETE_BLOCKED_HAS_CLIENTS = (
    "ریسلر {label} الان {client_count} سرویس دارد.\n"
    "برای حذف ابتدا همه سرویس‌ها را حذف کنید."
)
RESELLER_WIZARD_TELEGRAM_ID = (
    "مرحله ۱ — آیدی عددی تلگرام ریسلر را وارد کنید:"
)
RESELLER_WIZARD_DISPLAY_NAME = (
    "مرحله ۲ — نام نمایشی (فقط a-z 0-9 _ -) یا «بدون نام»:"
)
RESELLER_WIZARD_PICK_PANEL = "مرحله ۳ — پنل ریسلر را انتخاب کنید:"
RESELLER_WIZARD_QUOTA = (
    "مرحله ۴ — سقف حجم (GB):\n"
    "یکی از دکمه‌ها را بزنید یا عدد بنویسید:"
)
RESELLER_WIZARD_INBOUNDS = (
    "مرحله ۵ — اینباندهای مجاز (پنل #{panel_id}):\n"
    "روی هر اینباند بزنید تا انتخاب/لغو شود؛ سپس «ادامه»."
)
RESELLER_WIZARD_INBOUNDS_EMPTY = "اینبندی در این پنل یافت نشد."
RESELLER_WIZARD_INBOUNDS_NONE_SELECTED = "حداقل یک اینباند انتخاب کنید."
RESELLER_WIZARD_CONFIRM = (
    "تأیید ثبت ریسلر:\n"
    "آیدی: {telegram_id}\n"
    "نام: {display_name}\n"
    "پنل: {panel_name} (#{panel_id})\n"
    "سقف: {quota_gb} GB\n"
    "اینباندها: {inbound_ids}"
)
RESELLER_WIZARD_CANCELLED = "افزودن ریسلر لغو شد."
RESELLER_ALREADY_EXISTS = "این آیدی از قبل ریسلر است؛ از لیست ریسلرها مدیریت کنید."

TEMPLATE_ADDED = (
    "قالب #{id} ثبت شد: {name}\n"
    "حجم: {volume_gb} GB | انقضا: {expiry_label}"
)
TEMPLATE_LIST_HEADER = "قالب‌های ساخت سرویس (سراسری):"
TEMPLATE_LIST_EMPTY = "قالبی ثبت نشده است."
TEMPLATE_DELETED = "قالب #{id} حذف شد."
TEMPLATE_NOT_FOUND = "قالب یافت نشد."
TEMPLATE_HUB_HINT = "برای افزودن قالب، دکمه «افزودن قالب جدید» را بزنید."
TEMPLATE_DELETE_CONFIRM = (
    "حذف قالب #{id}؟\n"
    "{name} — {volume_gb} GB — {expiry_label}"
)
TEMPLATE_WIZARD_VOLUME = (
    "مرحله ۱ از ۴ — حجم قالب (گیگابایت):\n"
    "یکی از دکمه‌ها را بزنید یا عدد را بنویسید (مثلاً 10):"
)
TEMPLATE_WIZARD_EXPIRY = (
    "مرحله ۲ از ۴ — مدت انقضا:\n"
    "یکی از دکمه‌ها را بزنید یا تعداد روز را بنویسید (0 = نامحدود):"
)
TEMPLATE_WIZARD_NAME = (
    "مرحله ۳ از ۴ — نام دکمه قالب:\n"
    "این متن روی دکمهٔ ریسلر نمایش داده می‌شود.\n"
    "پیشنهاد: `{suggested}`\n\n"
    "نام را بنویسید یا «استفاده از نام پیشنهادی» را بزنید."
)
TEMPLATE_WIZARD_CONFIRM = (
    "مرحله ۴ از ۴ — تأیید ثبت قالب:\n"
    "نام: {name}\n"
    "حجم: {volume_gb} GB\n"
    "انقضا: {expiry_label}\n\n"
    "ثبت شود؟"
)
TEMPLATE_WIZARD_CANCELLED = "افزودن قالب لغو شد."

CREATE_PICK_TEMPLATE = (
    "یک قالب آماده انتخاب کنید، یا «ورود دستی» برای وارد کردن حجم و انقضا."
)
CREATE_CANCELLED = "ساخت سرویس لغو شد."
CREATE_VOLUME_PROMPT = "حجم سرویس را به گیگابایت وارد کنید (مثلاً 10):"
CREATE_EXPIRY_PROMPT = "تعداد روز انقضا را وارد کنید (0 = نامحدود):"
CREATE_CLIENT_NAME_PROMPT = (
    "نام سرویس را وارد کنید (فقط حروف انگلیسی، عدد، زیرخط و -)\n"
    "مثال: myvpn → ایمیل: {prefix}-client-myvpn\n\n"
    "یا «نام تصادفی» را بزنید."
)
CREATE_CONFIRM = (
    "تأیید ساخت سرویس:\n"
    "ایمیل: `{email_preview}`\n"
    "{template_line}"
    "حجم: {volume_gb} GB\n"
    "انقضا: {expiry_label}\n"
    "اینباندهای متصل: {inbounds}\n\n"
    "ادامه می‌دهید؟"
)
EMAIL_TAKEN = "این نام سرویس قبلاً استفاده شده. نام دیگری انتخاب کنید."
# SERVICE_CREATED is built via format_delivery_message in bot/utils/format_delivery.py
DELETE_CONFIRM = (
    "آیا از حذف سرویس `{email}` مطمئن هستید؟\n"
    "این کار قابل بازگشت نیست."
)
CREATE_SESSION_EXPIRED = (
    "اطلاعات ساخت ناقص یا منقضی شده است. از «ساخت سرویس» دوباره شروع کنید."
)
QR_CHOOSE = "کانفیگ VLESS را برای دریافت QR انتخاب کنید:"
QR_NOT_AVAILABLE = "کانفیگ VLESS برای این سرویس یافت نشد."
QR_SENT = "QR ارسال شد."
QR_CAPTION = "{remark_line}اسکن در کلاینت VPN"

USAGE_ALERT_RESELLER = (
    "اعلان\n\n"
    "{threshold}٪ سقف حجم ریسلر شما مصرف شده.\n"
    "تخصیص: {used_gb} از {quota_gb} GB ({percent}٪)"
)
USAGE_ALERT_CLIENT = (
    "اعلان\n\n"
    "{threshold}٪ حجم سرویس مصرف شده.\n"
    "سرویس: {email}\n"
    "مصرف: {used} از {total} ({percent}٪)"
)
SERVICE_DELETED = "سرویس حذف شد."
SERVICE_ENABLED = "سرویس فعال شد."
SERVICE_DISABLED = "سرویس غیرفعال شد."
EXPIRY_CHOOSE_MODE = (
    "سرویس: `{email}`\n"
    "انقضای فعلی: {expiry_label}\n\n"
    "روش تغییر انقضا را انتخاب کنید:"
)
EXPIRY_PROMPT_ADD_DAYS = "چند روز به انقضا اضافه شود؟ (عدد صحیح، مثلاً 30):"
EXPIRY_PROMPT_SET_DATE = (
    "تاریخ انقضای جدید را وارد کنید (YYYY-MM-DD)\n"
    "یا 0 برای نامحدود:"
)
EXPIRY_UPDATED = "انقضا به‌روز شد.\nجدید: {expiry_label}"
EDIT_MENU = (
    "ویرایش سرویس `{email}`\n\n"
    "limitIp فعلی: {limit_ip_label}\n"
    "کامنت: {comment_label}"
)
RESET_TRAFFIC_CONFIRM = (
    "آیا مصرف ترافیک سرویس `{email}` ریست شود؟\n"
    "این کار قابل بازگشت نیست."
)
TRAFFIC_RESET_OK = "ترافیک سرویس ریست شد."
LIMIT_IP_PROMPT = "limitIp جدید را وارد کنید (0 = نامحدود، مثلاً 2):"
LIMIT_IP_UPDATED = "limitIp به {limit_ip_label} تغییر کرد."
COMMENT_PROMPT = "کامنت را وارد کنید (خالی = حذف کامنت، حداکثر ۲۰۰ کاراکتر):"
COMMENT_UPDATED = "کامنت ذخیره شد."
NO_SERVICES = "هنوز سرویسی نساخته‌اید."
INVALID_INPUT = "ورودی نامعتبر است. دوباره تلاش کنید."
RATE_LIMITED = "تعداد درخواست زیاد است. چند ثانیه صبر کنید."

VERSION_INFO = "نسخه ربات: {version}"

BOT_UPDATE_PROMPT = (
    "آپدیت ربات (نسخه فعلی: {version})\n\n"
    "فایل ZIP ریلیز GitHub را بفرستید (حداکثر {max_mb} مگابایت).\n"
    "پس از تأیید، سرویس ری‌استارت می‌شود و آپدیت هنگام بالا آمدن اعمال می‌شود.\n"
    "دستور: /bot_update"
)
BOT_UPDATE_NOT_ZIP = "لطفاً یک فایل ZIP بفرستید."
BOT_UPDATE_TOO_LARGE = "حجم فایل بیش از حد مجاز است."
BOT_UPDATE_READY = (
    "بسته آماده است.\n"
    "فعلی: {current}\n"
    "هدف: {target}\n"
    "فایل: {filename}\n\n"
    "با «اعمال و ری‌استارت» ادامه دهید."
)
BOT_UPDATE_CANCELLED = "آپدیت لغو شد."
BOT_UPDATE_NO_PENDING = "بسته‌ای در صف نیست."
BOT_UPDATE_RESTARTING = (
    "در حال ری‌استارت سرویس `{service}`…\n"
    "پس از بالا آمدن، نسخه {target} اعمال می‌شود."
)
BOT_UPDATE_RESTART_MANUAL = (
    "ری‌استارت خودکار انجام نشد.\n"
    "نسخه هدف: {target}\n"
    "جزئیات: {detail}\n\n"
    "دستی: sudo systemctl restart {service}"
)
BOT_UPDATE_RESULT_OK = (
    "ربات به‌روز شد: {previous} → {new_version}\n{message}"
)
BOT_UPDATE_RESULT_FAIL = "آپدیت ناموفق بود ({previous}): {message}"
