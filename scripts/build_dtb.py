# SPDX-License-Identifier: MIT
"""Build locally from the installed BSP; never download or overwrite /boot."""
import argparse
import json
import shutil
from pathlib import Path
from common import parse_dtb, validate_camera, run, require_tested_host, sha256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, default=Path('/boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb'))
    p.add_argument('--port', choices=['CSI0', 'CSI1'], default='CSI0')
    p.add_argument('--allow-untested-port', action='store_true')
    p.add_argument('--output', type=Path, default=Path('build'))
    a = p.parse_args()
    release = require_tested_host()
    if a.port != 'CSI0' and not a.allow_untested_port:
        p.error('CSI1 was not hardware-tested; use --allow-untested-port only after checking wiring')
    for tool in ('fdtoverlay',):
        if not shutil.which(tool):
            p.error('Missing tool: ' + tool)
    original = parse_dtb(a.base)
    if any(v.get('compatible') == b'sony,imx219\0' for v in original.values()):
        p.error('Base already contains an IMX219 node; supply an unmodified installed BSP DTB')
    compatible = original['/'].get('compatible', b'').split(b'\0')
    if b'nvidia,p3768-0000+p3767-0000' not in compatible:
        p.error('Base is not the validated P3768/P3767-0000 Orin NX 16GB baseline')
    suffix = 'A' if a.port == 'CSI0' else 'C'
    camera = Path(f'/boot/tegra234-p3767-camera-p3768-imx219-{suffix}.dtbo')
    if not camera.is_file():
        p.error('Installed NVIDIA camera overlay missing: ' + str(camera))
    a.output.mkdir(parents=True, exist_ok=False)
    base = a.output / 'base-working.dtb'
    shutil.copyfile(a.base, base)
    target = a.output / 'imx219-local.dtb'
    run('fdtoverlay', '-i', base, '-o', target, camera)
    merged = parse_dtb(target)
    validation = validate_camera(merged, a.port)
    # Existing unrelated properties must stay intact. New camera subtrees are expected.
    allowed = {'/__symbols__'}
    changed = []
    for node, props in original.items():
        if node not in merged:
            raise ValueError('Unexpected deleted node: ' + node)
        for key, value in props.items():
            if merged[node].get(key) != value:
                if node not in allowed:
                    raise ValueError('Unexpected base change: ' + node + '/' + key)
                changed.append([node, key])
    report = {'release': release, 'port': a.port,
              'base_name': a.base.name, 'base_sha256': sha256(a.base),
              'camera_overlay_name': camera.name, 'camera_overlay_sha256': sha256(camera),
              'output_sha256': sha256(target), 'changed_existing_properties': changed,
              'validation': validation, 'hardware_capture_tested_by_this_build': False}
    (a.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('Built', target, '; /boot has NOT been changed.')


if __name__ == '__main__':
    main()
