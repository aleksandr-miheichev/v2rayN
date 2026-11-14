# PR10598 installed-package evidence

Source: `cd1161b116f9d9e0704dbcbfb1df665eb4f9199e`. [Build/install/runtime CI](https://github.com/aleksandr-miheichev/v2rayN/actions/runs/43590793248).

Four independently captured installed-apphost screenshots cover DEB on Debian13 and RPM on AlmaLinux10.2 (RPM build in UBI10), with script-default SDK10.0.114 and SDK11.0.100. Their app runtime packs are10.0.14 and10.0.15 respectively. Captures within each format are byte-identical because the displayed empty-profile UI is the same; identity is retained per job/artifact in screenshots.json.

Private software-rendered Xvfb displays, empty profiles, TUN disabled and system-proxy mode unchanged. The invalid-configuration notice is expected without a server profile. No proxy/TUN traffic or graceful exit is claimed. These hosted-VM/container captures do not establish physical Linux or hardware GPU operation.

Native payload/loaded hashes, SQLite integrity and two settled passive frames were checked. Existing DEBUG Interaction messages remain in raw CI logs. Publishing these files does not add them to the upstream product branch.
