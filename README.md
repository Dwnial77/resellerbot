# 🤖 Reseller Bot for 3x-ui (v3.2.0)

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](CHANGELOG.md)[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)[![Repository](https://img.shields.io/badge/github-resellerbot-darkviolet.svg)](https://github.com/Dwnial77/resellerbot)

پروژه **Reseller Bot** یک ربات تلگرام پیشرفته است که لایهٔ **ریسلر (نمایندگی فروش)** را روی پنل [3x-ui (MHSanaei)](https://github.com/MHSanaei/3x-ui "null") اضافه می‌کند. به‌جای دادن دسترسی مستقیم پنل به هر فروشنده، ادمین ریسلرها را با سقف حجم، اینباند مجاز و (در صورت نیاز) چند پنل جدا تعریف می‌کند؛ ریسلر فقط از تلگرام سرویس می‌سازد و مدیریت می‌کند.

ربات با API نسخه **v3.2.0** کار می‌کند، داده‌ها را در دیتابیس **SQLite** نگه می‌دارد، برای مدیریت راحت سرور لینوکس از **systemd** استفاده می‌کند و یک اسکریپت نصب خودکار اختصاصی دارد. همچنین ادمین می‌تواند نسخهٔ جدید را تنها با آپلود فایل ZIP از منوی ربات به‌روزرسانی کند.

## ⚙️ منطق اعتبارسنجی اینباندها (Inbounds)

- **مجاز** (`allowed_inbound_ids`): مجموعه‌ای از اینباندها که اعتبارسنجی ریسلر روی آن‌ها انجام می‌شود.
    
- **متصل هنگام ساخت** (`attach_inbound_ids`): اینباندهایی که با `inboundIds` روی کلاینت جدید وصل می‌شوند (که باید زیرمجموعهٔ اینباندهای مجاز باشند).
    

## 🛠 پیش‌نیازها

- Python `3.11+`
    
- پنل 3x-ui نسخه **v3.2.0** با inbound آماده
    
- **API Token** از پنل (توصیه‌شده) یا نام کاربری و رمز عبور ادمین
    
- توکن ربات تلگرام از [@BotFather](https://t.me/BotFather "null")
    

## 🚀 نصب سریع (لینوکس / VPS)

مخزن: [github.com/Dwnial77/resellerbot](https://github.com/Dwnial77/resellerbot)

### روش ۱ — یک‌خطی (`curl`)

اسکریپت [`scripts/bootstrap.sh`](scripts/bootstrap.sh) مخزن را clone می‌کند و [`scripts/install.sh`](scripts/install.sh) را اجرا می‌کند (کاربر سیستم، venv، systemd، `.env` اولیه).

```bash
# وابستگی‌ها (Debian/Ubuntu)
sudo apt update && sudo apt install -y git curl python3 python3-venv python3-pip

# نصب یک‌خطی
curl -fsSL https://raw.githubusercontent.com/Dwnial77/resellerbot/main/scripts/bootstrap.sh | sudo bash

# تنظیم توکن ربات و پنل
sudo nano /opt/resellerbot/.env
sudo systemctl restart resellerbot
sudo journalctl -u resellerbot -f
```

برای production ترجیحاً اسکریپت را با **tag** ثابت بگیرید (بعد از انتشار tag روی GitHub):

```bash
curl -fsSL https://raw.githubusercontent.com/Dwnial77/resellerbot/v1.0.0/scripts/bootstrap.sh | sudo bash
```

پارامترها (از طریق `bash -s --`):

```bash
curl -fsSL https://raw.githubusercontent.com/Dwnial77/resellerbot/main/scripts/bootstrap.sh | sudo bash -s -- --no-start
```

> **امنیت:** قبل از `curl | bash` محتوای [bootstrap.sh](https://raw.githubusercontent.com/Dwnial77/resellerbot/main/scripts/bootstrap.sh) را بررسی کنید. مخزن **private** بدون SSH/PAT روی VPS با این روش clone نمی‌شود.

### روش ۲ — کلون دستی (`git`)

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip
sudo git clone https://github.com/Dwnial77/resellerbot.git /opt/resellerbot
cd /opt/resellerbot
sudo bash scripts/install.sh
sudo nano /opt/resellerbot/.env
sudo systemctl restart resellerbot
sudo journalctl -u resellerbot -f
```

### گزینه‌های اسکریپت نصب (`install.sh` / `bootstrap.sh`)

- `--dir PATH`: تغییر مسیر نصب (پیش‌فرض: `/opt/resellerbot`).
- `--branch NAME`: شاخهٔ git هنگام bootstrap (پیش‌فرض: `main`).
- `--no-start`: آماده‌سازی بدون استارت خودکار سرویس.
    

### 🔐 تنظیم دسترسی Sudoers (برای آپدیت ZIP از تلگرام)

برای ری‌استارت شدن خودکار سرویس بعد از آپلود فایل ZIP در ربات، دسترسی زیر را اعمال کنید:

```
sudo visudo -f /etc/sudoers.d/resellerbot
```

خط زیر را داخل فایل قرار داده و ذخیره کنید:

```
resellerbot ALL=(root) NOPASSWD: /bin/systemctl restart resellerbot
```

## 💻 نصب دستی (ویندوز / محیط توسعه)

```bash
git clone https://github.com/Dwnial77/resellerbot.git
cd resellerbot
python -m venv .venv

# فعال‌سازی در ویندوز:
.venv\Scripts\activate
# فعال‌سازی در لینوکس یا مک:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env    # Windows
# cp .env.example .env    # Linux

# مقادیر فایل .env را پر کنید و سپس اجرا کنید:
python -m bot.main
```

## ⚙️ تنظیم فایل `.env`

|   |   |
|---|---|
|**متغیر**|**توضیح**|
|`BOT_TOKEN`|توکن ربات تلگرام|
|`ADMIN_TELEGRAM_IDS`|آیدی عددی ادمین‌ها (جدا شده با کاما)|
|`XUI_BASE_URL`|آدرس **پنل اول** (هنگام اولین اجرا در دیتابیس ذخیره می‌شود)|
|`XUI_API_TOKEN`|توکن API پنل اول|
|`XUI_SUB_PUBLIC_URL`|آدرس پایه سابسکریپشن عمومی؛ ربات `subId` را به انتها می‌چسباند|
|`XUI_DEFAULT_INBOUND_IDS`|پیش‌فرض آیدی اینباند (معمولاً `1`)|
|`XUI_VERIFY_SSL`|بررسی گواهی SSL پنل (`true` / `false`)|
|`XUI_AUTO_VISION_FLOW`|فعال‌سازی flow خودکار `xtls-rprx-vision` برای کانفیگ‌های VLESS مناسب|
|`XUI_AUTO_RESELLER_GROUP`|ساخت گروه در پنل به نام `{display_name}-{telegram_id}`|
|`DATABASE_URL`|مسیر دیتابیس SQLite (پیش‌فرض: `./data/bot.db`)|
|`CREATE_RATE_LIMIT`|حداکثر تعداد مجاز ساخت سرویس در دقیقه توسط ریسلر (پیش‌فرض: `5`)|
|`USAGE_ALERT_ENABLED`|ارسال اعلان خودکار هنگام مصرف ۸۰٪ / ۹۰٪|
|`USAGE_ALERT_INTERVAL_SECONDS`|فاصله زمانی بررسی اعلان‌ها به ثانیه|
|`UPDATE_ZIP_MAX_BYTES`|حداکثر حجم مجاز فایل ZIP آپدیت از تلگرام|
|`SYSTEMD_SERVICE_NAME`|نام سرویس systemd (پیش‌فرض: `resellerbot`)|
|`ALLOW_UPDATE_DOWNGRADE`|اجازه نصب نسخه‌های قدیمی‌تر از طریق فایل ZIP|

_جزئیات بیشتر و مقادیر پیش‌فرض در فایل [`.env.example`](.env.example) موجود است._

## 🐧 استقرار دستی لینوکس (بدون install.sh)

اگر ترجیح می‌دهید مراحل را مرحله‌به‌مرحله انجام دهید، کارهای داخل [`scripts/install.sh`](scripts/install.sh) را دستی پیش ببرید: ساخت کاربر `resellerbot`، ساخت venv، تنظیم [`deploy/resellerbot.service`](deploy/resellerbot.service) و اجرای `systemctl enable --now resellerbot`.

دستور ری‌استارت سرویس:

```
sudo systemctl restart resellerbot
```

## ⬆️ آپدیت ربات (ZIP از GitHub)

1. از بخش [Releases](https://github.com/Dwnial77/resellerbot/releases) فایل `resellerbot-X.Y.Z.zip` را دانلود کنید.
    
2. در تلگرام دکمه **⬆️ آپدیت ربات** یا دستور `/bot_update` را بزنید و فایل ZIP را بفرستید.
    
3. گزینه **اعمال و ری‌استارت** را انتخاب کنید. سرویس ری‌استارت شده و کدها و وابستگی‌ها آپدیت می‌شوند (فایل `.env` و دیتابیس `data/bot.db` کاملاً حفظ می‌شوند).
    
4. با دستور `/version` می‌توانید نسخه فعلی را چک کنید.
    

**ساخت فایل ZIP ریلیز (روی سیستم توسعه):**

```
bash scripts/build_release_zip.sh
# خروجی در مسیر: dist/resellerbot-1.0.0.zip
```

> ⚠️ **توجه:** روی سرور پروداکشن (Production) فقط از روش ZIP یا فقط از روش `git pull` استفاده کنید؛ ترکیب همزمان هر دو روش توصیه نمی‌شود.

## 👨‍✈️ راهنمای استفاده — ادمین

در چت با ربات دستور **`/`** را بفرستید تا لیست دستورات با توضیح کوتاه نمایش داده شود. ادمین‌ها دسترسی‌های مدیریتی پیشرفته‌تری دارند.

1. **شروع کار:** دستور `/start` یا `/admin` برای باز کردن منوی اصلی ادمین.
    
2. **مدیریت پنل‌ها:** از طریق دکمه منو یا دستور `/panels` پنل‌های دوم و بعدی را با ویزارد گام‌به‌گام اضافه کنید (نام، URL، توکن، ساب).
    
3. **لیست ریسلرها:** از طریق دکمه منو یا دستور `/list_resellers` وارد هاب مدیریت شوید: انتخاب ریسلر ← **ویرایش ریسلر** (سقف حجم، تعداد سرویس، نام، اینباندها)، فعال/غیرفعال، حذف یا تغییر پنل.
    
    - _فرمت ارسال سریع (در یک پیام):_ `[آیدی تلگرام] [نام] [شماره پنل] [سقف حجم به گیگ] [آیدی اینباند]` (مثال: `5266810479 ali 1 100 1`).
        
    - _فرمت بدون نام:_ `123456789 1 100 1` یا فرمت قدیمی (پنل ۱): `123456789 100 1`.
        
4. **مشاهده اینباندها:** دستور `/list_inbounds 2` برای دیدن اینباندهای پنل شماره ۲ (پیش‌فرض: ۱).
    
5. **تغییر پنل ریسلر:** از طریق دکمه منو یا دستور `/set_panel` (انتخاب ریسلر ← پنل ← تأیید). مسیر سریع: `/set_panel 123456789 2` (تنها در صورتی مجاز است که ریسلر **هیچ سرویسی** نداشته باشد).
    
6. **دستورات متنی چت:** دستوراتی مثل `/set_quota` ، `/set_max_clients` ، `/set_name` و `/set_allowed_inbounds` مستقیماً از طریق چت هم با همان منطق دکمه‌ها کار می‌کنند.
    
7. **قالب‌های سرویس:** تعریف پکیج‌های سراسری (حجم/انقضا) برای ساخت سریع سرویس روی پنل اختصاصی همان ریسلر.
    

### 👥 گروه‌بندی کلاینت‌ها در پنل

وقتی ریسلر نام نمایشی دارد (مثلاً `ali`)، هر سرویس جدید در پنل 3x-ui داخل گروه **`ali-5266810479`** (`نام-آیدی_تلگرام`) قرار می‌گیرد. اگر ریسلر نام نداشته باشد، گروه فقط شامل آیدی عددی خواهد بود.

برای غیرفعال‌سازی این قابلیت، مقدار زیر را در `.env` قرار دهید:

```
XUI_AUTO_RESELLER_GROUP=false
```

## 🧑‍💼 راهنمای استفاده — ریسلر (نماینده)

1. **داشبورد:** دستور `/start` میزان سقف حجم مجاز، حجم مصرفی و باقی‌مانده سهمیه را نشان می‌دهد.
    
2. **ساخت سرویس:** اگر ادمین قالب تعبیه کرده باشد، انتخاب قالب با یک کلیک انجام می‌شود. در غیر این صورت با انتخاب **ورود دستی**، مراحل (حجم به گیگ ← روز انقضا، `0` = نامحدود) ← **نام سرویس** ← تأیید طی می‌شود.
    
    - _فرمت ایمیل کلاینت:_ `{نام_ریسلر}-client-{نام_سرویس}` (مثال: `ali-client-myvpn`). اگر ریسلر نام نداشته باشد فرمت به صورت `r{telegram_id}-client-{نام}` خواهد بود.
        
    - دکمه **نام تصادفی** برای ساخت پسوند خودکار تعبیه شده است.
        
3. **سرویس‌های من:** دریافت لینک اتصال (VLESS + سابسکریپشن)، **دریافت QR Code اختصاصی هر کانفیگ VLESS** به صورت عکس در تلگرام، مشاهده ترافیک، **تغییر انقضا**، **ویرایش سرویس** (ریست ترافیک با تأیید، limitIp، کامنت)، فعال/غیرفعال کردن و حذف سرویس (با تأیید مکرر).
    
4. **سیستم هوشمند اعلان مصرف:** وقتی مصرف سهمیه ریسلر یا ترافیک واقعی یک سرویس به **۸۰٪** یا **۹۰٪** برسد، ربات هشداری در تلگرام ارسال می‌کند (هر آستانه یک‌بار تا زمان افت مصرف زیر ۷۵٪ ارسال می‌شود).
    

## 🔌 اتصالات و دسترسی‌های API پنل (v3.2.0)

ربات از Endpointهای زیر در پنل 3x-ui استفاده می‌کند:

- `POST /panel/api/clients/add`
    
- `POST /panel/api/clients/groups/create` — ساخت گروه اختصاصی ریسلر
    
- `POST /panel/api/clients/groups/bulkAdd` — اختصاص کلاینت به گروه
    
- `POST /panel/api/clients/del/:email`
    
- `POST /panel/api/clients/update/:email` — ویرایش وضعیت، limitIp و کامنت
    
- `POST /panel/api/clients/resetTraffic/:email` — ریست مصرف ترافیک کلاینت
    
- `GET /panel/api/clients/traffic/:email`
    
- `GET /panel/api/clients/links/:email` — دریافت کانفیگ‌های VLESS
    
- `GET /panel/api/clients/subLinks/:subId` — دریافت URL سابسکریپشن
    
- `GET /panel/api/clients/get/:email` — سیستم Fallback برای دریافت `subId` کلاینت‌های قدیمی
    

> ⚠️ **نکته فنی:** فیلد `totalGB` در بدنه درخواست‌ها **بر حسب بایت** محاسبه می‌شود (مثلاً ۱۰ گیگابایت = `10737418240`).

### 🔗 لینک‌های سابسکریپشن (Subscription)

ربات لینک سابسکریپشن را از ترکیب **`subId` کلاینت** و متغیر **`XUI_SUB_PUBLIC_URL`** تولید می‌کند:

```
XUI_SUB_PUBLIC_URL=https://sub.example.com:2096/save/
```

خروجی نهایی برای `subId=abc123`: `https://sub.example.com:2096/save/abc123`

این آدرس معمولاً با آدرس اصلی پنل (`XUI_BASE_URL`) متفاوت است. در صورت نیاز، API مربوط به `subLinks` نیز بررسی و تست می‌شود.

### ⚡️ تنظیم خودکار Flow (Vision / Reality)

هنگام ساخت سرویس جدید، ربات لیست اینباندها را بررسی می‌کند. اگر **همهٔ** اینباندهای انتخاب شده از نوع **VLESS + TCP + TLS یا Reality** باشند، فیلد `flow` کلاینت به‌صورت خودکار روی گزینهٔ `xtls-rprx-vision` تنظیم می‌شود. در صورت ترکیب نامناسب اینباندها، فیلد flow خالی می‌ماند تا اختلالی در اتصال ایجاد نشود.

غیرفعال‌سازی از فایل `.env`:

```
XUI_AUTO_VISION_FLOW=false
```


## 📂 ساختار پوشه‌ها و فایلهای پروژه

```
bot/          — هندلرهای تلگرام، کیبوردها و ماشین وضعیت FSM
db/           — فایل SQLite و سیستم Migration
services/     — ماژول‌های مدیریت سهمیه (quota)، آپدیتور و رجیستری پنل‌ها
xui/          — کلاینت متصل به API پنل 3x-ui
deploy/       — فایل پیکربندی سرویس لینوکسی systemd
scripts/      — bootstrap.sh (curl نصب)، install.sh، build_release_zip.sh
tests/        — تست‌های پروژه
```

## 🔒 امنیت

- اطلاعات حساس پنل‌ها فقط و فقط در سرور ربات شما نگهداری می‌شوند.
    
- ریسلرها منحصراً به کلاینت‌های ثبت‌شده در بخش خودشان در دیتابیس دسترسی دارند.
    
- محدودیت نرخ ساخت (`CREATE_RATE_LIMIT`) از اسپم پنل جلوگیری می‌کند.
    

## 📄 مجوز

این پروژه تحت مجوز [MIT](LICENSE) منتشر شده است.