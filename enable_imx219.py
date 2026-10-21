# SPDX-License-Identifier: MIT
"""Small DTB and host helpers; no external Python dependencies."""
import hashlib
import re
import struct
import subprocess
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(*args):
    return subprocess.check_output([str(x) for x in args], text=True).strip()


def require_tested_host():
    model = Path('/proc/device-tree/model')
    if not model.exists() or 'Jetson' not in model.read_text():
        raise ValueError('Run on the Jetson host, not an x86 PC or unexposed container')
    release = Path('/etc/nv_tegra_release').read_text().splitlines()[0]
    if not re.search(r'^# R39 \(release\), REVISION: 2\.1(?:,|\s|$)', release):
        raise ValueError('Only L4T R39.2.1 is validated by this project: ' + release)
    return release


def parse_dtb(path):
    data = Path(path).read_bytes()
    if len(data) < 40:
        raise ValueError('Truncated DTB')
    h = struct.unpack_from('>10I', data)
    if h[0] != 0xd00dfeed or h[1] > len(data):
        raise ValueError('Invalid DTB header')
    pos, strings = h[2], h[3]
    nodes, stack = {}, []
    while True:
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            end = data.index(0, pos)
            stack.append(data[pos:end].decode())
            pos = (end + 4) & ~3
            name = '/' + '/'.join(stack[1:])
            if name in nodes:
                raise ValueError('Duplicate node: ' + name)
            nodes[name] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, off = struct.unpack_from('>II', data, pos)
            pos += 8
            end = data.index(0, strings + off)
            key = data[strings + off:end].decode()
            props = nodes['/' + '/'.join(stack[1:])]
            if key in props:
                raise ValueError('Duplicate property: ' + key)
            props[key] = data[pos:pos + size]
            pos = (pos + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            return nodes
        else:
            raise ValueError('Unexpected FDT token: ' + str(token))


def string(value):
    return value.rstrip(b'\0').decode()


def cell(value):
    return struct.unpack('>I', value)[0]


def validate_camera(nodes, port='CSI0'):
    sensors = [p for p, v in nodes.items() if v.get('compatible') == b'sony,imx219\0']
    if len(sensors) != 1:
        raise ValueError('Expected exactly one IMX219 node; got ' + str(sensors))
    sensor = sensors[0]
    expected = 'serial_b' if port == 'CSI0' else 'serial_c'
    if string(nodes[sensor + '/mode0']['tegra_sinterface']) != expected:
        raise ValueError('Sensor interface differs from selected connector')
    # A missing status property means enabled; every ancestor must also be enabled.
    for p in [sensor] + [sensor[:i] for i, c in enumerate(sensor) if c == '/' and i]:
        if p in nodes and nodes[p].get('status', b'okay\0') not in (b'okay\0', b'ok\0'):
            raise ValueError('Disabled camera ancestor: ' + p)
    handles = {}
    for p, props in nodes.items():
        if 'phandle' in props:
            number = cell(props['phandle'])
            if number in handles:
                raise ValueError('Duplicate phandle: ' + str(number))
            handles[number] = p
    links = []
    for p, props in nodes.items():
        camera_path = p.startswith(sensor) or p.startswith('/tegra-capture-vi') or '/nvcsi@' in p
        if camera_path and 'remote-endpoint' in props:
            peer = handles[cell(props['remote-endpoint'])]
            if cell(nodes[peer]['remote-endpoint']) != cell(props['phandle']):
                raise ValueError('Nonreciprocal camera graph link: ' + p)
            links.append([p, peer])
    if len(links) != 4 or cell(nodes['/tegra-capture-vi']['num-channels']) != 1:
        raise ValueError('Unexpected single-camera topology')
    return {'sensor': sensor, 'reciprocal_graph_links': links}


# SPDX-License-Identifier: MIT
"""Build locally from the installed BSP; never download or overwrite /boot."""
import argparse
import json
import shutil
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, default=Path('/boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb'))
    p.add_argument('--output', type=Path, default=Path('build'))
    a = p.parse_args()
    release = require_tested_host()
    for tool in ('fdtoverlay',):
        if not shutil.which(tool):
            p.error('Missing tool: ' + tool)
    original = parse_dtb(a.base)
    if any(v.get('compatible') == b'sony,imx219\0' for v in original.values()):
        p.error('Base already contains an IMX219 node; supply an unmodified installed BSP DTB')
    compatible = original['/'].get('compatible', b'').split(b'\0')
    if b'nvidia,p3768-0000+p3767-0000' not in compatible:
        p.error('Base is not the validated P3768/P3767-0000 Orin NX 16GB baseline')
    suffix = 'A'
    camera = Path(f'/boot/tegra234-p3767-camera-p3768-imx219-{suffix}.dtbo')
    if not camera.is_file():
        p.error('Installed NVIDIA camera overlay missing: ' + str(camera))
    a.output.mkdir(parents=True, exist_ok=False)
    base = a.output / 'base-working.dtb'
    shutil.copyfile(a.base, base)
    target = a.output / 'imx219-local.dtb'
    run('fdtoverlay', '-i', base, '-o', target, camera)
    merged = parse_dtb(target)
    validation = validate_camera(merged, 'CSI0')
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
    report = {'release': release, 'port': 'CSI0',
              'base_name': a.base.name, 'base_sha256': sha256(a.base),
              'camera_overlay_name': camera.name, 'camera_overlay_sha256': sha256(camera),
              'output_sha256': sha256(target), 'changed_existing_properties': changed,
              'validation': validation, 'hardware_capture_tested_by_this_build': False}
    (a.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('Built', target, '; /boot has NOT been changed.')


if __name__ == '__main__':
    main()
