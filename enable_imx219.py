# SPDX-License-Identifier: MIT
"""Small DTB and host helpers; no external Python dependencies."""
import argparse
import hashlib
import json
import shutil
import tempfile
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
    if not re.search(r'^# R39 \(release\), REVISION: 2\.[12](?:,|\s|$)', release):
        raise ValueError('Expected L4T R39.2.1 or R39.2.2: ' + release)
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


def build(base, camera, extras, output, release):
    overlays = [*extras, camera]
    if len({p.resolve() for p in overlays}) != len(overlays):
        raise ValueError('Duplicate overlay')
    for path in overlays:
        if path.suffix != '.dtbo' or not path.is_file():
            raise ValueError('Expected a .dtbo file: ' + str(path))
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Choose a new output directory: ' + str(output))
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        tmp = Path(tmp)
        working = tmp / 'base-working.dtb'
        shutil.copyfile(base, working)
        original = parse_dtb(working)
        if b'nvidia,p3768-0000+p3767-0000' not in original['/'].get('compatible', b'').split(b'\0'):
            raise ValueError('Expected P3768/P3767-0000 Orin NX 16GB base')
        if any(v.get('compatible') == b'sony,imx219\0' for v in original.values()):
            raise ValueError('Base already contains IMX219')
        inputs = []
        for i, path in enumerate(overlays):
            copy = tmp / f'{i}.dtbo'
            shutil.copyfile(path, copy)
            inputs.append(copy)
        baseline = working
        if extras:
            baseline = tmp / 'carrier.dtb'
            run('fdtoverlay', '-i', working, '-o', baseline, *inputs[:-1])
        carrier = parse_dtb(baseline) if extras else original
        target = tmp / 'imx219-local.dtb'
        run('fdtoverlay', '-i', baseline, '-o', target, inputs[-1])
        merged = parse_dtb(target)
        validation = validate_camera(merged, 'CSI0')
        # Carrier overlays may legitimately change existing properties. The camera
        # overlay may not then undo them (including a previously enabled UART).
        for node, props in carrier.items():
            if node not in merged:
                raise ValueError('Unexpected deleted node: ' + node)
            for key, value in props.items():
                if merged[node].get(key) != value and node != '/__symbols__':
                    raise ValueError('Unexpected camera overlay change: ' + node + '/' + key)
        report = {'release': release, 'port': 'CSI0',
                  'base_name': base.name, 'base_sha256': sha256(working),
                  'camera_overlay_name': camera.name, 'camera_overlay_sha256': sha256(inputs[-1]),
                  'overlays': [{'name': p.name, 'sha256': sha256(copy)}
                               for p, copy in zip(overlays, inputs)],
                  'output_sha256': sha256(target), 'validation': validation,
                  'changed_existing_properties': [[n, k] for n, props in original.items()
                      for k, v in props.items() if merged.get(n, {}).get(k) != v],
                  'hardware_capture_tested_by_this_build': False}
        manifest = tmp / 'manifest.json'
        manifest.write_text(json.dumps(report, indent=2) + '\n')
        output.mkdir()
        for path in (working, target, manifest):
            path.rename(output / path.name)
    return report


def main():
    p = argparse.ArgumentParser(description='Build locally from the installed BSP; does not install a boot entry.')
    p.add_argument('--base', type=Path, default=Path('/boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb'))
    p.add_argument('--output', type=Path, default=Path('build'))
    p.add_argument('--extra-overlays', nargs='+', type=Path, default=[], metavar='FILE.dtbo',
                   help='Apply these carrier overlays in order, then IMX219-A')
    a = p.parse_args()
    release = require_tested_host()
    if not shutil.which('fdtoverlay'):
        p.error('Missing tool: fdtoverlay')
    camera = Path('/boot/tegra234-p3767-camera-p3768-imx219-A.dtbo')
    report = build(a.base, camera, a.extra_overlays, a.output, release)
    print(json.dumps(report, indent=2))
    print('Built', a.output / 'imx219-local.dtb', '; /boot has NOT been changed.')


if __name__ == '__main__':
    main()
