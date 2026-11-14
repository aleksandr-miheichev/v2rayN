# PR 10598 installed-package screenshots

These complete frames show actual installed v2rayN apphosts from source commit b0a6e0937f0ff722a1bf02745e637e814ab7d8e2. The production DEB/RPM builders, fresh package resolver installation, native file hashes, SQLite integrity and settled passive UI were checked in run https://github.com/aleksandr-miheichev/v2rayN/actions/runs/43558791305.

DEB build/runtime used Debian 13. RPM build used UBI 10 and installation/runtime used AlmaLinux 10.2. Images show a private Xvfb display in disposable Linux containers on GitHub-hosted VMs; physical Linux and hardware GPU are not established.

Profiles were intentionally empty, TUN off and system-proxy mode unchanged. The visible invalid-configuration notice is the expected empty-profile state, not a native-library startup failure. No personal server, profile or credential data is shown.

Default-script SDK 10.0.114 selected self-contained runtime pack 10.0.14; the current SDK 11.0.100 override selected runtime pack 10.0.15. The screenshots are observational evidence and do not establish graceful application exit or proxy/TUN traffic.
