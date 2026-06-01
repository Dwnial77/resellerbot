# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `scripts/install.sh` for one-step Linux VPS install
- README quick install section and GitHub links (`Dwnial77/resellerbot`)

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
