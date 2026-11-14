#!/usr/bin/env bash
# Test-only wrapper. The subject packaging scripts run unmodified from main().
set -euo pipefail
export LC_ALL=C
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1

phase=${1:?Expected build or install}
: "${SUBJECT_SHA:?}" "${PACKAGE_FORMAT:?}" "${SDK_MODE:?}"
[[ "$SUBJECT_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$PACKAGE_FORMAT" == deb || "$PACKAGE_FORMAT" == rpm ]]
[[ "$SDK_MODE" == script-default || "$SDK_MODE" == 11.0.100 ]]
mkdir -p /evidence/packages /evidence/runtime

inventory() {
  local tree=$1 prefix=$2
  [[ -d "$tree" ]] || return 0
  (
    cd "$tree"
    find . -type f -printf '%m %s %P\n' | sort > "$prefix-files.txt"
    find . -type f -print0 | sort -z | xargs -0 -r sha256sum > "$prefix-files.sha256"
    find . -type f \( -name '*.so' -o -name '*.so.*' -o -name v2rayN \) -print0 |
      sort -z | xargs -0 -r sha256sum > "$prefix-native.sha256"
    find . -type f \( -name '*.so' -o -name '*.so.*' -o -name v2rayN \) -exec file {} + > "$prefix-native-types.txt"
  )
}

bootstrap_rpm() {
  command -v curl >/dev/null || dnf -y install curl ca-certificates
  dnf -y install dnf-plugins-core
  if dnf repolist all | grep -q ubi-10-codeready-builder-rpms; then
    dnf config-manager --set-enabled ubi-10-codeready-builder-rpms
  fi
  # Same public EPEL bootstrap sources as the subject's release workflow.
  local el_major arch fedora rocky alma
  # The image supplies /etc/os-release; the Windows lint host cannot follow it.
  # shellcheck disable=SC1091
  el_major=$(. /etc/os-release; printf '%s' "${VERSION_ID%%.*}")
  arch=$(uname -m)
  fedora="https://dl.fedoraproject.org/pub/epel/epel-release-latest-${el_major}.noarch.rpm"
  rocky="https://dl.rockylinux.org/pub/rocky/${el_major}/extras/${arch}/os"
  alma="https://repo.almalinux.org/almalinux/${el_major}/extras/${arch}/os"
  install_epel_from_dir() {
    local base=$1 epel_rpm
    epel_rpm=$({ curl -fsSL "$base/Packages/"; curl -fsSL "$base/Packages/e/" | sed 's|href="|href="e/|'; } |
      sed -n 's/.*href="\([^"]*epel-release-[^"]*\.noarch\.rpm\)".*/\1/p' | sort -V | tail -n1) || true
    [[ -n "$epel_rpm" ]] || return 1
    dnf -y install "$base/Packages/$epel_rpm"
  }
  curl -fsSLI "$fedora" >/dev/null && dnf -y install "$fedora" ||
    install_epel_from_dir "$rocky" || install_epel_from_dir "$alma"
  dnf repolist
}

record_build() {
  local result=$1 pub package source_root extracted
  set +e
  printf 'exit_code=%s\nsubject_sha=%s\n' "$result" "$SUBJECT_SHA" > /evidence/build-status.txt
  git -C /source rev-parse HEAD > /evidence/source-head-after.txt
  git -C /source diff --exit-code > /evidence/source-tracked-diff-after.txt
  git -C /source status --porcelain > /evidence/source-status-after.txt
  sha256sum /source/package-{debian,rhel}.sh > /evidence/script-source-after.sha256
  if [[ -x "$HOME/.dotnet/dotnet" ]]; then
    (cd /source; "$HOME/.dotnet/dotnet" --info) > /evidence/dotnet-info.txt 2>&1
    (cd /source; "$HOME/.dotnet/dotnet" --version) > /evidence/selected-sdk.txt 2>&1
    "$HOME/.dotnet/dotnet" --list-runtimes > /evidence/installed-dotnet-runtimes.txt 2>&1
  fi
  pub=/source/v2rayN/v2rayN.Desktop/bin/Release/net10.0/linux-x64/publish
  inventory "$pub" /evidence/publish
  for metadata in "$pub"/*.deps.json "$pub"/*.runtimeconfig.json; do
    [[ -f "$metadata" ]] && cp "$metadata" /evidence/
  done
  source_root=/source/v2rayN/v2rayN.Desktop/obj
  if [[ -f "$source_root/project.assets.json" ]]; then
    cp "$source_root/project.assets.json" /evidence/desktop-project.assets.json
    python3 - "$source_root/project.assets.json" > /evidence/selected-native-packages.json <<'PY'
import json
import sys
from pathlib import Path
assets = json.loads(Path(sys.argv[1]).read_text())
libraries = {key: value for key, value in assets.get('libraries', {}).items()
             if 'skia' in key.lower() or 'harfbuzz' in key.lower()}
targets = {target: {key: value for key, value in entries.items()
                   if key in libraries} for target, entries in assets.get('targets', {}).items()}
print(json.dumps({'libraries': libraries, 'targets': targets}, indent=2))
PY
  fi
  if [[ "$PACKAGE_FORMAT" == deb ]]; then
    find "$HOME/debbuild" -type f -name '*.deb' -exec cp {} /evidence/packages/ \;
  else
    find "$HOME/rpmbuild/RPMS" -type f -name '*.rpm' -exec cp {} /evidence/packages/ \;
  fi
  for package in /evidence/packages/*; do
    [[ -f "$package" ]] || continue
    sha256sum "$package" >> /evidence/package.sha256
    extracted=$(mktemp -d)
    if [[ "$PACKAGE_FORMAT" == deb ]]; then
      dpkg-deb --info "$package" > /evidence/package-metadata.txt
      dpkg-deb --contents "$package" > /evidence/package-contents.txt
      dpkg-deb --extract "$package" "$extracted"
    else
      rpm -qpi "$package" > /evidence/package-metadata.txt
      rpm -qp --requires "$package" > /evidence/package-requires.txt
      rpm -qplv "$package" > /evidence/package-contents.txt
      (cd "$extracted"; rpm2cpio "$package" | cpio -idm --quiet)
    fi
    inventory "$extracted/opt/v2rayN" /evidence/package-payload
  done
  if [[ "$PACKAGE_FORMAT" == deb ]]; then dpkg-query -W; else rpm -qa | sort; fi > /evidence/build-os-packages.txt 2>&1
  return 0
}

if [[ "$phase" == build ]]; then
  trap 'record_build "$?"' EXIT
  cat /etc/os-release > /evidence/build-os-release.txt
  uname -a > /evidence/build-kernel.txt
  if [[ "$PACKAGE_FORMAT" == deb ]]; then
    export DEBIAN_FRONTEND=noninteractive
    dpkg-query -W > /evidence/install-os-packages-before-package.txt
    apt-get update
    apt-get install --no-install-recommends -y sudo git curl ca-certificates python3 binutils \
      libc6 libgcc-s1 libstdc++6 zlib1g libicu-dev libssl-dev
    script=/source/package-debian.sh
  else
    bootstrap_rpm
    dnf -y install sudo git rpm-build rpmdevtools rsync findutils tar gzip unzip which python3 binutils cpio
    script=/source/package-rhel.sh
  fi
  git config --global --add safe.directory /source
  test "$(git -C /source rev-parse HEAD)" = "$SUBJECT_SHA"
  git -C /source diff --exit-code
  sha256sum "$script" > /evidence/executed-script.sha256
  if [[ "$SDK_MODE" != script-default ]]; then export DOTNET_SDK_VERSION="$SDK_MODE"; fi
  printf 'bash -x %s --buildfrom 3 --arch x64\nDOTNET_SDK_VERSION=%s\n' \
    "$script" "${DOTNET_SDK_VERSION:-<script default: existing pipeline reference>}" > /evidence/command.txt
  cd /source
  # Execute the complete source script; do not source it, stub functions, or pass a release version.
  bash -x "$script" --buildfrom 3 --arch x64
  test "$(git -C /source rev-parse HEAD)" = "$SUBJECT_SHA"
  git -C /source diff --exit-code
  if [[ "$PACKAGE_FORMAT" == deb ]]; then
    test "$(find "$HOME/debbuild" -name '*.deb' -type f | wc -l)" -eq 1
  else
    test "$(find "$HOME/rpmbuild/RPMS" -name '*.rpm' -type f | wc -l)" -eq 1
  fi
elif [[ "$phase" == install ]]; then
  trap 'printf "exit_code=%s\nsubject_sha=%s\n" "$?" "$SUBJECT_SHA" > /evidence/install-status.txt' EXIT
  cat /etc/os-release > /evidence/install-os-release.txt
  uname -a > /evidence/install-kernel.txt
  shopt -s nullglob
  packages=(/evidence/packages/*)
  test "${#packages[@]}" -eq 1
  if [[ "$PACKAGE_FORMAT" == deb ]]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    # Install with the package resolver first; extraction is only a payload inventory.
    apt-get install --no-install-recommends -y "${packages[0]}"
    dpkg-query -W > /evidence/installed-os-packages-before-smoke-tools.txt
    # Inspection/user tools only. Missing app libraries must remain observable.
    apt-get install --no-install-recommends -y python3 passwd file
    dpkg-query -W > /evidence/installed-os-packages.txt
  else
    rpm -qa | sort > /evidence/install-os-packages-before-package.txt
    # UBI10 is the build reference; a full public EL10 distro is a separate runtime target.
    # shellcheck disable=SC1091
    install_os=$(. /etc/os-release; printf '%s:%s' "$ID" "$VERSION_ID")
    case "${INSTALL_TARGET:?}:$install_os" in
      almalinux-10.2:almalinux:10.2) ;;
      ubi10:rhel:10*) bootstrap_rpm ;;
      *) printf 'Unexpected RPM installation environment: %s / %s\n' "$INSTALL_TARGET" "$install_os" >&2; exit 1 ;;
    esac
    dnf repolist -v > /evidence/install-enabled-repositories.txt 2>&1
    set +e
    dnf list --showduplicates --available xdg-utils > /evidence/install-xdg-utils-available.txt 2>&1
    probe_result=$?
    set -e
    printf 'exit_code=%s\n' "$probe_result" >> /evidence/install-xdg-utils-available.txt
    dnf -y install "${packages[0]}"
    rpm -qa | sort > /evidence/installed-os-packages-before-smoke-tools.txt
    # Do not supplement ICU, X11 or fonts before the decisive runtime smoke.
    dnf -y install python3 shadow-utils file
    rpm -qa | sort > /evidence/installed-os-packages.txt
  fi
  test -x /opt/v2rayN/v2rayN
  inventory /opt/v2rayN /evidence/installed-payload
  diff -u /evidence/package-payload-native.sha256 /evidence/installed-payload-native.sha256 > /evidence/native-package-install-comparison.txt
  for native in /opt/v2rayN/libSkiaSharp.so /opt/v2rayN/libHarfBuzzSharp.so /opt/v2rayN/libhostfxr.so /opt/v2rayN/libcoreclr.so; do
    test -f "$native"
    printf '\n%s\n' "$native" >> /evidence/installed-native-linking.txt
    ldd "$native" >> /evidence/installed-native-linking.txt 2>&1
  done
  if grep -q 'not found' /evidence/installed-native-linking.txt; then exit 1; fi
  useradd --uid 10001 --create-home --shell /bin/bash smokeci
  chown 10001:10001 /evidence/runtime
else
  printf 'Unknown phase: %s\n' "$phase" >&2
  exit 2
fi
