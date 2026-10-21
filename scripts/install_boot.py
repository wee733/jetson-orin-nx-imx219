# SPDX-License-Identifier: MIT
"""Preview by default; --apply backs up extlinux and selects a new boot entry."""
import argparse
import datetime
import difflib
import json
import os
import re
import tempfile
from pathlib import Path
from boot_config import add_entry
from common import require_tested_host, parse_dtb, validate_camera, sha256


def atomic_write(path, data):
    stat = path.stat() if path.exists() else None
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, (stat.st_mode & 0o777) if stat else 0o644)
        if stat:
            os.chown(tmp, stat.st_uid, stat.st_gid)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dtb', type=Path, required=True)
    p.add_argument('--label', default='imx219-local')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--allow-replace-fdt', action='store_true', help='Explicitly allow replacing a custom FDT in the selected entry')
    a = p.parse_args()
    require_tested_host()
    manifest = json.loads(a.dtb.with_name('manifest.json').read_text())
    digest = sha256(a.dtb)
    if digest != manifest['output_sha256']:
        p.error('DTB differs from validated build manifest')
    validate_camera(parse_dtb(a.dtb), manifest['port'])
    source_data = a.dtb.read_bytes()
    if sha256(a.dtb) != digest:
        p.error('DTB changed while reading')
    dest = Path('/boot/dtb') / ('imx219-local-' + digest[:12] + '.dtb')
    conf = Path('/boot/extlinux/extlinux.conf')
    old = conf.read_text()
    new = add_entry(old, a.label, str(dest))
    print(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                       fromfile='current/extlinux.conf', tofile='planned/extlinux.conf')))
    print('DTB destination:', dest)
    if not a.apply:
        print('PLAN ONLY. Use sudo and --apply to install. No reboot is performed.')
        return
    if os.geteuid() != 0:
        p.error('--apply requires root')
    for var in Path('/sys/firmware/efi/efivars').glob('SecureBoot-*'):
        value = var.read_bytes()
        if len(value) >= 5 and value[4] == 1:
            p.error('Secure Boot enabled; signed-DTB installation is outside this script')
    default_label = re.search(r'(?m)^DEFAULT[ \t]+(\S+)', old).group(1)
    selected = re.search(r'(?ms)^LABEL[ \t]+' + re.escape(default_label) + r'[ \t]*\n(.*?)(?=^LABEL[ \t]|\Z)', old).group(1)
    fdt = re.search(r'(?m)^\s*FDT[ \t]+(\S+)', selected)
    if fdt and Path(fdt.group(1)).name != manifest['base_name'] and not a.allow_replace_fdt:
        p.error('Selected entry already uses a custom FDT. Review existing board changes; use --allow-replace-fdt only when intentional.')
    # Refuse a conflicting existing destination; never overwrite a stock DTB.
    if dest.exists() and sha256(dest) != digest:
        p.error('Destination exists with unexpected content')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = Path('/var/backups/jetson-imx219') / stamp
    backup.mkdir(parents=True, mode=0o700)
    atomic_write(backup / 'extlinux.conf', old.encode())
    import hashlib
    state = {'installed_conf_sha256': hashlib.sha256(new.encode()).hexdigest(),
             'backup_conf_sha256': hashlib.sha256(old.encode()).hexdigest(),
             'installed_dtb': str(dest), 'installed_dtb_sha256': digest}
    atomic_write(backup / 'state.json', (json.dumps(state, indent=2) + '\n').encode())
    atomic_write(dest, source_data)
    if conf.read_text() != old:
        p.error('Boot configuration changed during planning; backup retained, config not written')
    atomic_write(conf, new.encode())
    print('Installed. Backup:', backup)
    print('Reboot manually when ready. Original boot entry remains selectable; automatic fallback is not configured.')


if __name__ == '__main__':
    main()
