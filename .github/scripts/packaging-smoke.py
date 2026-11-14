#!/usr/bin/env python3
"""Start only the installed apphost in a disposable unprivileged Linux container."""
import hashlib
import json
import os
from contextlib import closing
from pathlib import Path
import subprocess
import time

import packaging_readiness as detector


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def validate_safe_config(config):
    assert config['IndexId'] == config['SubIndexId'] == ''
    assert config['SystemProxyItem']['SysProxyType'] == 2
    assert config['TunModeItem']['EnableTun'] is False
    assert config['GuiItem']['AutoRun'] is False
    assert config['GuiItem']['AutoUpdateInterval'] == 0
    assert config['GuiItem']['EnableStatistics'] is False
    assert config['CheckUpdateItem']['SelectedCoreTypes'] == []
    assert config['GlobalHotkeys'] == []


def inspect_database(path):
    import sqlite3

    if not path.is_file():
        raise RuntimeError(f'The actual application database was not created: {path}')
    with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as connection:
        check = [row[0] for row in connection.execute('PRAGMA quick_check')]
        count = connection.execute('SELECT COUNT(*) FROM ProfileItem').fetchone()[0]
    return {'path': str(path), 'quick_check': check, 'profile_count': count}


def validate_database(observation):
    if observation['quick_check'] != ['ok']:
        raise RuntimeError(f"SQLite quick_check failed: {observation['quick_check']}")
    if observation['profile_count'] != 0:
        raise RuntimeError(f"Expected an empty ProfileItem table, found {observation['profile_count']}")


def main():
    import pwd

    output = Path('/evidence/runtime')
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert os.getuid() == 10001 and str(home) != '/root'
    assert Path(os.environ.get('HOME', str(home))) == home
    environment = dict(os.environ)
    directories = {'XDG_DATA_HOME': home / '.local/share',
                   'XDG_CONFIG_HOME': home / '.config',
                   'XDG_CACHE_HOME': home / '.cache',
                   'XDG_RUNTIME_DIR': home / '.runtime'}
    for key, path in directories.items():
        path.mkdir(parents=True, exist_ok=False, mode=0o700)
        environment[key] = str(path)
    environment['V2RAYN_LOCAL_APPLICATION_DATA_V2'] = '1'
    environment['LIBGL_ALWAYS_SOFTWARE'] = '1'
    environment['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    config = json.loads((Path(__file__).parent / 'packaging-smoke-config.json').read_text())
    validate_safe_config(config)
    config_dir = directories['XDG_DATA_HOME'] / 'v2rayN/guiConfigs'
    config_dir.mkdir(parents=True, exist_ok=False)
    config_path = config_dir / 'guiNConfig.json'
    write_json(config_path, config)
    write_json(output / 'initial-config.json', config)
    result = {'subject_sha': os.environ['SUBJECT_SHA'],
              'package_format': os.environ['PACKAGE_FORMAT'], 'sdk_mode': os.environ['SDK_MODE'],
              'scenario': 'Installed apphost; fresh unprivileged user; no profiles, proxy, TUN, updates or network',
              'uid': os.getuid(), 'home': str(home), 'xdg_directories': {k: str(v) for k, v in directories.items()},
              'executable': '/opt/v2rayN/v2rayN',
              'apphost_sha256': hashlib.sha256(Path('/opt/v2rayN/v2rayN').read_bytes()).hexdigest(),
              'mesa_environment_request': {'LIBGL_ALWAYS_SOFTWARE': '1'},
              'stages': [], 'passive_startup_ready': False, 'eventual_ready': False,
              'first_ready_stage': None, 'manual_full_window_review': 'Required',
              'physical_linux_and_hardware_gpu': 'Not run: hosted VM and containers; software Mesa requested'}
    process = None
    display = None
    x11 = None
    try:
        with (output / 'app-stdout.log').open('wb') as stdout, (output / 'app-stderr.log').open('wb') as stderr:
            process = subprocess.Popen(['/opt/v2rayN/v2rayN'], cwd=home, env=environment,
                                       stdout=stdout, stderr=stderr)
            result['pid'] = process.pid
            # Launch first: absent declared client libraries must not be hidden by capture setup.
            try:
                import packaging_x11 as x11
            except Exception as error:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                raise RuntimeError('X11 inspection unavailable in the package-resolved environment; '
                                   f'apphost launch attempted, exit={process.poll()}; see app stderr') from error
            display = x11.open_display(None)
            if not display:
                raise RuntimeError('Cannot connect to the task-owned Xvfb Unix socket')
            window = None
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and process.poll() is None:
                windows = x11.window_inventory(display, x11.root_window(display))
                write_json(output / 'window-inventory.json', windows)
                candidates = [item for item in windows if item['pid'] == process.pid
                              and item['map_state'] == 2 and item['geometry']
                              and item['geometry']['width'] >= 700 and item['geometry']['height'] >= 400
                              and 'v2rayN' in item['name']]
                if candidates:
                    window = int(candidates[0]['window'], 16)
                    result['main_window'] = candidates[0]
                    break
                time.sleep(0.5)
            if window is None:
                raise RuntimeError(f'No mapped main window for owned PID {process.pid}; exit={process.poll()}')

            for kind in ('initial', 'focus', 'pointer', 'resize'):
                stage = {'kind': kind, 'frames': []}
                if kind != 'initial':
                    stage['stimulus'] = x11.apply_stimulus(display, window, process.pid, kind)
                start = time.monotonic()
                offsets = (0, 2, 5, 10, 20, 30) if kind == 'initial' else (0, 0.5, 2)
                for frame_index, offset in enumerate(offsets):
                    time.sleep(max(0, offset - (time.monotonic() - start)))
                    if process.poll() is not None:
                        raise RuntimeError(f'Apphost exited during {kind}: {process.returncode}')
                    state = x11.input_state(display, window, process.pid)
                    image = output / f'{kind}-{frame_index:02d}-full-screen.png'
                    x11.capture(display, x11.root_window(display), image)
                    assessment = detector.assess(image, state['geometry'])
                    stage['frames'].append({'elapsed_seconds': time.monotonic() - start,
                                            'input_state': state, 'readiness': assessment})
                    if assessment['toolbar_and_headers_present']:
                        result['eventual_ready'] = True
                        result['first_ready_stage'] = kind
                        result['passive_startup_ready'] = kind == 'initial'
                        break
                result['stages'].append(stage)
                write_json(output / 'runtime.json', result)
                if result['eventual_ready']:
                    break

            maps = Path(f'/proc/{process.pid}/maps').read_text()
            (output / 'process-maps.txt').write_text(maps)
            mapped_paths = sorted({line.split(maxsplit=5)[5] for line in maps.splitlines()
                                   if len(line.split(maxsplit=5)) == 6 and line.split(maxsplit=5)[5].startswith('/')})
            mapped_native_paths = [path for path in mapped_paths
                                   if Path(path).is_file() and ('.so' in Path(path).name or Path(path).name == 'v2rayN')]
            result['mapped_native_files'] = [{'path': path, 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                                             for path in mapped_native_paths]
            components = ('libcoreclr.so', 'libclrjit.so', 'libhostfxr.so',
                          'libhostpolicy.so', 'System.Private.CoreLib.dll')
            result['clr_runtime_component_paths'] = {name: [path for path in mapped_paths if Path(path).name == name]
                                                     for name in components}
            result['loaded_native_libraries'] = sorted({line.split()[-1] for line in maps.splitlines()
                                                       if 'libSkiaSharp' in line or 'libHarfBuzzSharp' in line})
            result['direct_children'] = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
            result['child_commands'] = {pid: Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', 'replace')
                                        for pid in result['direct_children'] if Path(f'/proc/{pid}/cmdline').exists()}
            if any(any(name in command.lower() for name in ('xray', 'sing-box', 'mihomo'))
                   for command in result['child_commands'].values()):
                raise RuntimeError('A proxy core started unexpectedly')
            for library in ('libSkiaSharp.so', 'libHarfBuzzSharp.so'):
                if f'/opt/v2rayN/{library}' not in mapped_native_paths:
                    raise RuntimeError(f'The actual apphost did not map the installed /opt/v2rayN/{library}')
            result['database'] = inspect_database(config_dir / 'guiNDB.db')
            validate_database(result['database'])
            validate_safe_config(json.loads(config_path.read_text()))
            write_json(output / 'final-config.json', json.loads(config_path.read_text()))
            if not result['passive_startup_ready']:
                raise RuntimeError('Toolbar and DataGrid headers did not become ready without input; see diagnostic stages')
            result['status'] = 'OBSERVED: installed apphost loaded native libraries; passive toolbar/header band guard passed; manual full-window review required'
    except Exception as error:
        result['status'] = 'FAILED'
        result['error'] = str(error)
        raise
    finally:
        if process and process.poll() is None:
            result['stop_method'] = 'SIGTERM sent only to the owned apphost PID after capture; no Options or exit-dialog interaction'
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                result['stop_method'] += '; bounded SIGKILL fallback'
        result['final_exit_code'] = process.returncode if process else None
        write_json(output / 'runtime.json', result)
        if display:
            x11.close_display(display)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
