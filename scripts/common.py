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
