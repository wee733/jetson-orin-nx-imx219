# SPDX-License-Identifier: MIT
"""Generate an IMX219-77 CONFIG-mode override from the local NVIDIA BSP."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

LIB = Path('/usr/lib/aarch64-linux-gnu/nvidia/libnvodm_imager.so')
VENDOR = Path('/home/nvidia/workspaces/damiao-bringup/waveshare-isp/camera_overrides.isp')
SETTINGS = Path('/var/nvidia/nvcam/settings')
TARGET = SETTINGS / 'camera_overrides.isp'
STATE = SETTINGS / '.imx219-77-backup'
UNIT = 'nvargus-daemon.service'
PART = re.compile(rb'^#\*\s*Part#:\s*RBP194[ \t\r]*$', re.M)
ASSIGN = re.compile(r'\s*([\w.\[\]]+)\s*=\s*([^;#]+?)\s*;\s*(?:#.*)?')
GROUP = re.compile(r'lensShading\.ctrlPoints\[(\d+)\]\.')
AWB = ('GrayLineSlope', 'GrayLineIntercept', 'UtoMIRED', 'MIREDtoU', 'UtoCCT', 'CCTtoU', 'LowU', 'HighU')


def extract(blob):
    hits = list(PART.finditer(blob))
    if len(hits) != 1:
        raise ValueError('Expected exactly one embedded RBP194 profile')
    pos = hits[0].start()
    text = blob[blob.rfind(b'\0', 0, pos)+1:blob.index(b'\0', pos)].decode('ascii')
    if text.count('Part#:') != 1 or not re.search(r'^#\*\s*Sensor:\s*IMX219\s*$', text, re.M):
        raise ValueError('Unexpected embedded profile boundaries or sensor')
    return text


def optical(key):
    return (key.startswith(('lensShading.', 'falloff_srfc.', 'opticalBlack.', 'colorCorrection.srgbMatrix[',
                            'awb.GrayLine', 'awb.Uto')) or key in {'awb.' + k for k in AWB})


def merge(template, calibration):
    rows = template.splitlines(keepends=True)
    base = {}
    for row in rows:
        if row.strip() and not row.lstrip().startswith('#'):
            m = ASSIGN.fullmatch(row.rstrip('\r\n'))
            if not m:
                raise ValueError('Unsupported RBP194 syntax: ' + row[:80])
            base[m[1]] = m[2]
    values = {}
    for row in calibration.splitlines():
        key = row.partition('=')[0].strip()
        if key not in base or not optical(key):
            continue  # No legacy-only keys or continuation lines are imported.
        m = ASSIGN.fullmatch(row)
        if not m or key in values:
            raise ValueError('Malformed or duplicate optical attribute: ' + key)
        values[key] = m[2]
    if values.get('lensShading.ctrlPointsCount') != '3':
        raise ValueError('Expected three IMX219-77 control point sets')
    required = {'colorCorrection.srgbMatrix[%d]' % i for i in range(3)}
    for g in range(3):
        prefix = f'lensShading.ctrlPoints[{g}].'
        required.add(prefix+'cct')
        required.update(prefix+f'controlPoint{ch}[{y}][{x}]' for ch in ('R','GR','GB','B')
                        for y in range(10) for x in range(10))
    required.update('awb.'+k for k in AWB)
    missing = required - values.keys()
    if missing:
        raise ValueError('Incomplete lens calibration: missing ' + min(missing))
    for key in AWB:
        values['awb.v4.'+key] = values['awb.'+key]
    low = values['awb.LowU']
    float(low)  # This clamp requires a scalar, not a pair.
    values['awb.v4.GrayLineSoftClamp[0]'] = '{%s, %s}' % (low, low)
    if not values.keys() <= base.keys():
        raise ValueError('RBP194 lacks required awb.v4 attributes')
    result = []
    for row in rows:
        m = ASSIGN.fullmatch(row.rstrip('\r\n'))
        if m:
            group = GROUP.match(m[1])
            if group and int(group[1]) >= 3:
                continue
            if m[1] in values:
                row = row[:m.start(2)] + values[m[1]] + row[m.end(2):]
        result.append(row)
    return ''.join(result)


def command(*args, timeout=45):
    return subprocess.check_output(args, text=True, timeout=timeout)


def check_config_mode():
    pid = int(command('systemctl', 'show', UNIT, '-p', 'MainPID', '--value'))
    if pid <= 0:
        raise RuntimeError('Start nvargus-daemon in CONFIG mode first')
    env = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
    if b'NVCAMERA_NITO_PATH=NITO' in env:
        raise RuntimeError('NITO mode is active; select CONFIG mode first')


def restart():
    for pattern in ('nvcam_cache_*.bin', 'serial_no_*.bin'):
        for path in SETTINGS.glob(pattern):
            path.unlink()
    command('systemctl', 'restart', UNIT)


def verify():
    check_config_mode()
    invocation = command('systemctl', 'show', UNIT, '-p', 'InvocationID', '--value').strip()
    if not re.fullmatch('[0-9a-f]{32}', invocation):
        raise RuntimeError('No systemd invocation ID')
    command('gst-launch-1.0', '-q', 'nvarguscamerasrc', 'sensor-id=0', 'sensor-mode=2',
            'wbmode=1', 'exposurecompensation=0', 'num-buffers=60', '!',
            'video/x-raw(memory:NVMM),format=NV12,width=1280,height=720,framerate=30/1',
            '!', 'fakesink', 'sync=false')
    command('journalctl', '--sync')
    logs = command('journalctl', '--no-pager', '-o', 'cat', '_SYSTEMD_INVOCATION_ID='+invocation)
    match = f'Found override file [{TARGET}]'
    if match not in logs or 'invalid isp config attribute' in logs.lower():
        raise RuntimeError(f'No confirmed clean override load; inspect journal invocation {invocation}')
    print(match, '; invalid ISP attributes: 0; journal invocation:', invocation)


def restore():
    backup = STATE / 'original.isp'
    if backup.is_file():
        with tempfile.NamedTemporaryFile(dir=SETTINGS, delete=False) as f:
            tmp = Path(f.name)
        try:
            shutil.copy2(backup, tmp)
            st = backup.stat()
            os.chown(tmp, st.st_uid, st.st_gid)
            tmp.replace(TARGET)
        finally:
            tmp.unlink(missing_ok=True)
    elif (STATE / 'original-absent').is_file():
        TARGET.unlink(missing_ok=True)
    else:
        raise RuntimeError('Backup incomplete; refusing to remove existing override')
    restart()


def install(data):
    check_config_mode()
    if TARGET.is_symlink() or (TARGET.exists() and not TARGET.is_file()):
        raise RuntimeError('Unexpected override file type')
    STATE.mkdir(mode=0o700)  # Never overwrite an earlier installation/backup.
    digest = hashlib.sha256(data).hexdigest()
    if TARGET.exists():
        backup = STATE / 'original.isp'
        shutil.copy2(TARGET, backup)
        st = TARGET.stat()
        os.chown(backup, st.st_uid, st.st_gid)
    else:
        (STATE / 'original-absent').touch()
    (STATE / 'installed.sha256').write_text(digest+'\n')
    try:
        with tempfile.NamedTemporaryFile(dir=STATE, delete=False) as f:
            f.write(data)
            os.fchmod(f.fileno(), 0o644)
            os.fchown(f.fileno(), 0, 0)
        Path(f.name).replace(TARGET)
        restart()
        verify()
    except BaseException:
        restore()
        shutil.rmtree(STATE)
        raise


def uninstall():
    expected = (STATE / 'installed.sha256').read_text().strip()
    if TARGET.is_symlink() or hashlib.sha256(TARGET.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Installed file was changed; inspect backup before reverting')
    restore()
    shutil.rmtree(STATE)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library', type=Path, default=LIB)
    p.add_argument('--waveshare', type=Path, default=VENDOR)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--install', action='store_true')
    mode.add_argument('--uninstall', action='store_true')
    a = p.parse_args()
    if not a.output and os.geteuid() != 0:
        p.error('Use sudo for install/uninstall; stop camera clients first')
    if a.uninstall:
        uninstall()
        return
    data = merge(extract(a.library.read_bytes()), a.waveshare.read_text(encoding='utf-8-sig')).encode()
    if a.output:
        if a.output.resolve().is_relative_to(SETTINGS):
            p.error('Use --install for the live settings directory')
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with a.output.open('xb') as f:
            f.write(data)
    else:
        install(data)
    print('SHA256:', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
