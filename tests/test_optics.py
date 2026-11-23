import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import enable_imx219 as dt
import imx219 as cam
import install_isp_override as isp


class TestOptics(unittest.TestCase):
    def test_profile_is_opt_in(self):
        with patch.object(cam.cv2, 'VideoCapture') as capture:
            capture.return_value.read.return_value = (True, object())
            with cam.IMX219() as sensor:
                self.assertIn('wbmode=1 exposurecompensation=0.0', sensor.pipeline)
                self.assertIs(sensor.read()[1], capture.return_value.read.return_value[1])
            with cam.IMX219(Path(cam.__file__).with_name('white_balance.json')) as sensor:
                self.assertIsNotNone(sensor.lut)
                self.assertIn('wbmode=2', sensor.pipeline)

    def test_ae_cap(self):
        self.assertEqual(cam.control_properties({'max_exposure_us': 8000}), ' exposuretimerange="13000 8000000"')
        with self.assertRaises(SystemExit):
            cam.control_properties({'shutter_us': 5000, 'max_exposure_us': 8000})

    def test_supported_revisions(self):
        for revision, ok in [('2.1', True), ('2.2', True), ('2.10', False), ('2.3', False)]:
            line = '# R39 (release), REVISION: '+revision+', TEST'
            with patch.object(Path, 'exists', return_value=True), patch.object(Path, 'read_text', side_effect=['Jetson',line]):
                if ok: self.assertEqual(dt.require_tested_host(), line)
                else:
                    with self.assertRaises(ValueError): dt.require_tested_host()

    def test_refuse_missing_rbp194(self):
        with self.assertRaises(ValueError): isp.extract(b'other sensor\0')

    @unittest.skipUnless(isp.LIB.is_file() and isp.VENDOR.is_file(), 'on-device calibration inputs required')
    def test_real_profile(self):
        base = isp.extract(isp.LIB.read_bytes()); vendor = isp.VENDOR.read_text()
        merged = isp.merge(base, vendor)
        def attrs(s):
            return {m[1]:m[2] for row in s.splitlines() if (m:=isp.ASSIGN.fullmatch(row))}
        src, old, new = map(attrs, (vendor,base,merged))
        self.assertEqual(set(old)-set(new), {k for k in old if k.startswith('lensShading.ctrlPoints[3].')})
        self.assertFalse(set(new)-set(old))
        for k,v in src.items():
            if k in new and isp.optical(k): self.assertEqual(new[k], v, k)
        for k in isp.AWB: self.assertEqual(src['awb.'+k],new['awb.v4.'+k])
        self.assertEqual(new['awb.v4.GrayLineSoftClamp[0]'],'{%s, %s}' % ((src['awb.LowU'],)*2))
        bad = vendor.replace('lensShading.ctrlPoints[2].controlPointB[9][9]', 'unknown.attribute')
        with self.assertRaisesRegex(ValueError,'Incomplete'): isp.merge(base,bad)

    def test_revert_absent_and_preserve_user_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'camera_overrides.isp'; state=Path(folder)/'.backup'; state.mkdir()
            (state/'original-absent').touch(); (state/'installed.sha256').write_text(hashlib.sha256(b'installed').hexdigest())
            with patch.object(isp,'TARGET',dest), patch.object(isp,'STATE',state), patch.object(isp,'restart') as restart:
                dest.write_bytes(b'edited')
                with self.assertRaises(RuntimeError): isp.uninstall()
                restart.assert_not_called(); self.assertEqual(dest.read_bytes(),b'edited')
                dest.write_bytes(b'installed'); isp.uninstall(); restart.assert_called_once()
                self.assertFalse(dest.exists()); self.assertFalse(state.exists())
