# PR10598 installed-package evidence

Source: `3e5a81ce7bf8159519c4273683e13f1fbc018255`. [Fresh packaging CI](https://github.com/aleksandr-miheichev/v2rayN/actions/runs/43918887726).

Four independent installed-apphost captures cover DEB on Debian 13 and RPM on AlmaLinux 10.2 (RPM build in UBI 10), with script-default SDK 10.0.114/runtime pack 10.0.14 and SDK 11.0.100/runtime pack 10.0.15. Provenance and exact image hashes are in screenshots.json; identical image bytes do not merge the separate job identities.

Private Xvfb displays, empty profiles, TUN disabled, system-proxy mode unchanged. The invalid-configuration notice is expected without a server profile. Complete painted UI was manually reviewed, and package/installed/mapped native hashes plus SQLite integrity were checked. Existing DEBUG Interaction messages remain in raw logs. These are hosted VM/container software-rendering checks; no physical Linux, hardware GPU, proxy/TUN traffic or graceful desktop-GUI exit claim.

This evidence branch is separate from the upstream product diff.
