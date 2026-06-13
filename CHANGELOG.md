# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.5] - 2026-06-01

### Added

- راهنمای استفاده (ساب / QR) زیر پیام تحویل کانفیگ برای مشتری نهایی
- ریسلر: **کاهش ترافیک** سرویس موجود (برگشت سهمیه، جلوگیری از کاهش زیر مصرف)
- ادمین: **پیام همگانی** به ریسلرهای فعال (`/broadcast` یا دکمه منو)

### Fixed

- نمایش label کانفیگ VLESS: ایمیل کلاینت + remark اینباند در پیام و fragment لینک
- باگ «ورود دستی» در ساخت سرویس (حلقه برگشت به انتخاب قالب)

### Changed

- حداقل حجم ساخت سرویس جدید: 20 GB (دستی، قالب، validate_create)
- QR caption: اشاره به v2rayNG / Hiddify و لینک ساب برای بروزرسانی خودکار

## [1.2.1] - 2026-06-01

### Added

- Admin **ویرایش پنل**: تغییر نام، آدرس (URL/پورت)، توکن API و آدرس ساب عمومی از صفحهٔ جزئیات پنل
- تست اتصال قبل از ذخیرهٔ آدرس یا توکن؛ reload خودکار `PanelRegistry` پس از تغییر
- Admin **مجاز/ممنوع ساخت کلاینت** per-panel (toggle روی تخصیص پنل ریسلر)
- **صفحه‌بندی «سرویس‌های من»** برای ریسلر (۸ سرویس در هر صفحه، قبلی/بعدی)

## [1.2.0] - 2026-06-01

### Added

- **Multi-panel resellers**: admin assigns multiple 3x-ui panels per reseller with independent quota, inbounds, max clients, and active flag (`reseller_panels` table, migration 007)
- Admin **مدیریت پنل‌ها** hub: add/remove panel assignments, per-panel quota edit, set default panel
- Reseller picks panel when creating a service (skipped when only one active panel)
- Account status and admin reports show per-panel quota summary
- Usage alerts for quota thresholds are per-panel
- `/set_panel` now sets the **default** panel among existing assignments (no longer requires zero clients)

### Changed

- `QuotaService` and `ResellerService` operate per `(reseller, panel_id)`; legacy `resellers` columns synced for default panel compat
- Admin bot update menu: **آپدیت از GitHub** downloads latest release ZIP from GitHub Releases

## [1.1.5] - 2026-06-01

### Added

- Reseller **افزودن ترافیک** on existing service from service detail: top-up client limit via panel `bulkAdjust`, deducts from reseller quota (lifetime allocation)
- Confirm step shows current service cap, added volume, and remaining quota before apply
- Quick volume buttons (5/10/20/50 GB) plus custom GB input

## [1.1.0] - 2026-06-01

### Added

- Admin **گزارش‌گیری**: select reseller → service count and allocation usage (quota / used / remaining); hub summary, progress bar, refresh button
- `/add_quota` and `/reset_quota_usage` commands; admin buttons to add ceiling and reset quota consumption for a fresh package
- Quota refund on service delete when actual traffic (up+down) is below 1 GB (configurable via `QUOTA_REFUND_MAX_TRAFFIC_GB`)
- Lifetime quota tracking (`lifetime_allocated_bytes`) — consumption persists after service delete
- `xui_for_reseller` with registry reload from DB when panel missing from cache
- Clear reseller panel error messages (inactive / missing / not loaded)
- `scripts/bootstrap.sh` for one-line VPS install (`curl | sudo bash`)

### Fixed

- Deleting a service no longer frees reseller quota without traffic check; refund only when panel usage is under threshold
- New resellers on panel #2+ could not create clients (`NO_PANEL_ACCESS`) until full bot restart
- `scripts/install.sh` for one-step Linux VPS install
- README quick install (curl + git clone) and GitHub links (`Dwnial77/resellerbot`)

### Notes

- DB migration **006** adds `lifetime_allocated_bytes` with backfill from active services on first startup after update
- ZIP update via `/bot_update` preserves `data/` (database) and `.env`; automatic DB backup before apply
- Build release ZIP with `scripts/build_release_zip.sh` or `scripts/build_release_zip.ps1` (not manual Windows zip)

## [1.0.0] - 2026-06-01

### Added

- Multi-panel 3x-ui support; one panel per reseller
- Reseller hub: add/edit resellers, quotas, inbounds, display names
- Service creation with templates, custom client suffix, cancel flow
- My services: links, VLESS QR, traffic, expiry edit, enable/disable, delete
- Usage alerts at 80% / 90% quota and per-client traffic
- Admin bot update via Telegram (release ZIP) with apply-on-restart
- Linux systemd unit (`deploy/resellerbot.service`)
- Numbered DB schema migrations (`schema_migrations` table)
- Release ZIP build script (`scripts/build_release_zip.sh`)

### Notes

- Compatible with 3x-ui panel API **v3.2.0 +**
- Upgrade path: upload release ZIP in bot admin menu, confirm restart
