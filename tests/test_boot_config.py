# SPDX-License-Identifier: MIT
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from boot_config import add_entry, checked_rollback

CONFIG = '''TIMEOUT 30
DEFAULT primary
LABEL primary
      MENU LABEL primary kernel
      LINUX /boot/Image
      INITRD /boot/initrd
      APPEND ${cbootargs} root=PARTUUID=example rw console=ttyTCU0,115200
# LABEL commented-out
'''


class BootConfigTests(unittest.TestCase):
    def test_keeps_original_and_kernel_arguments(self):
        out = add_entry(CONFIG, 'camera', '/boot/dtb/test.dtb')
        original = CONFIG[CONFIG.index('LABEL primary'):]
        self.assertIn(original, out)
        self.assertEqual(out.count('APPEND ${cbootargs} root=PARTUUID=example rw console=ttyTCU0,115200'), 2)
        self.assertIn('DEFAULT camera\n', out)

    def test_clones_selected_default_not_first_label(self):
        conf = CONFIG.replace('DEFAULT primary', 'DEFAULT selected')
        conf += '\nLABEL selected\n LINUX /boot/other\n APPEND custom=1\n FDT /boot/old.dtb\n'
        new = add_entry(conf, 'camera', '/boot/new.dtb').split('LABEL camera\n')[1]
        self.assertIn('LINUX /boot/other', new)
        self.assertIn('APPEND custom=1', new)
        self.assertNotIn('/boot/old.dtb', new)

    def test_refuses_existing_overlay_stack(self):
        with self.assertRaises(ValueError):
            add_entry(CONFIG + ' FDTOVERLAYS /boot/old.dtbo\n', 'camera', '/boot/new.dtb')

    def test_refuses_duplicate_or_invalid_label(self):
        for name in ('primary', 'bad name', '../escape'):
            with self.assertRaises(ValueError):
                add_entry(CONFIG, name, '/boot/test.dtb')

    def test_refuses_ambiguous_default(self):
        with self.assertRaises(ValueError):
            add_entry(CONFIG + 'DEFAULT missing\n', 'camera', '/boot/test.dtb')

    def test_rollback_protects_subsequent_changes(self):
        current = add_entry(CONFIG, 'camera', '/boot/test.dtb')
        digest = hashlib.sha256(current.encode()).hexdigest()
        self.assertEqual(checked_rollback(current, digest, CONFIG), CONFIG)
        with self.assertRaises(ValueError):
            checked_rollback(current + '# later edit\n', digest, CONFIG)


if __name__ == '__main__':
    unittest.main()
