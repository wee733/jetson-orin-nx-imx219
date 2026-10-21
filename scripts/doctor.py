# SPDX-License-Identifier: MIT
"""Read-only camera report; excludes hostnames, MACs, UUIDs and raw images."""
import argparse
import glob
import json
import subprocess
from pathlib import Path


def command(args):
    try:
        r = subprocess.run(args, text=True, capture_output=True, timeout=15)
        return {'returncode': r.returncode, 'stdout': r.stdout.strip(), 'stderr': r.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'error': type(e).__name__}


def read(path):
    p = Path(path)
    return p.read_text().replace('\x00', '').strip() if p.exists() else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    release = read('/etc/nv_tegra_release')
    sensors = []
    for path in Path('/sys/firmware/devicetree/base').rglob('compatible'):
        try:
            if b'sony,imx219' in path.read_bytes():
                sensors.append(str(path.parent).replace('/sys/firmware/devicetree/base', ''))
        except OSError:
            pass
    checks = {
        'model': read('/proc/device-tree/model'),
        'l4t': release.splitlines()[0] if release else None,
        'kernel': command(['uname', '-r']),
        'video_nodes': sorted(glob.glob('/dev/video*')),
        'imx219_dt_nodes': sensors,
        'driver': command(['modinfo', '-F', 'filename', 'nv_imx219']),
        'devices': command(['v4l2-ctl', '--list-devices']),
        'formats': command(['v4l2-ctl', '-d', '/dev/video0', '--list-formats-ext']),
        'media_graph': command(['media-ctl', '-p']),
        'argus_state': command(['systemctl', 'is-active', 'nvargus-daemon']),
        'gstreamer_source': command(['gst-inspect-1.0', 'nvarguscamerasrc']),
        'text_isp_override_present': Path('/var/nvidia/nvcam/settings/camera_overrides.isp').exists(),
        'reference_nito_present': Path('/var/nvidia/nvcam/settings/imx219.nito').exists(),
    }
    text = json.dumps(checks, indent=2, ensure_ascii=False) + '\n'
    print(text)
    if a.output:
        a.output.write_text(text)


if __name__ == '__main__':
    main()
