# SPDX-License-Identifier: MIT
"""Restore an installation backup, without overwriting later boot-config edits."""
import argparse
import json
import os
from pathlib import Path
from boot_config import checked_rollback
from common import sha256
from install_boot import atomic_write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backup', required=True, type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    state = json.loads((a.backup / 'state.json').read_text())
    backup = a.backup / 'extlinux.conf'
    if sha256(backup) != state['backup_conf_sha256']:
        p.error('Backup checksum mismatch')
    target = Path('/boot/extlinux/extlinux.conf')
    restored = checked_rollback(target.read_text(), state['installed_conf_sha256'], backup.read_text())
    print('Will restore', backup, 'to', target, '; installed DTB will be retained.')
    if a.apply:
        if os.geteuid() != 0:
            p.error('--apply requires root')
        atomic_write(target, restored.encode())
        print('Original config restored. Reboot manually when ready.')
    else:
        print('PLAN ONLY. Use sudo and --apply to restore.')


if __name__ == '__main__':
    main()
