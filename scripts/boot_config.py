# SPDX-License-Identifier: MIT
"""Pure extlinux transformations, shared by installer and tests."""
import re


def add_entry(text, label, dtb):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', label):
        raise ValueError('Invalid boot label')
    labels = list(re.finditer(r'(?m)^LABEL[ \t]+([^\s#]+)[ \t]*$', text))
    names = [m.group(1) for m in labels]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate existing boot labels')
    if label in names:
        raise ValueError('Label already exists; choose another --label')
    defaults = list(re.finditer(r'(?m)^DEFAULT[ \t]+([^\s#]+)[ \t]*$', text))
    if len(defaults) != 1 or defaults[0].group(1) not in names:
        raise ValueError('Expected one DEFAULT naming an existing LABEL')
    index = names.index(defaults[0].group(1))
    start = labels[index].end()
    end = labels[index + 1].start() if index + 1 < len(labels) else len(text)
    lines = text[start:end].splitlines()
    active = [x for x in lines if x.strip() and not x.lstrip().startswith('#')]
    if any(re.match(r'\s*(?:FDTOVERLAYS|OVERLAYS)\s', x, re.I) for x in active):
        raise ValueError('Selected boot entry has overlays; manual review required')
    if not any(re.match(r'\s*LINUX\s', x) for x in active):
        raise ValueError('Selected entry has no LINUX line')
    if not any(re.match(r'\s*APPEND\s', x) for x in active):
        raise ValueError('Selected entry has no APPEND line')
    kept = [x for x in active if not re.match(r'\s*(?:FDT|MENU\s+LABEL)\s', x, re.I)]
    new = '\n# Added by jetson-orin-nx-imx219-guide; original entries retained.\n'
    new += f'LABEL {label}\n      MENU LABEL IMX219 local configuration\n'
    new += '\n'.join(kept) + '\n      FDT ' + dtb + '\n'
    changed = text[:defaults[0].start()] + 'DEFAULT ' + label + text[defaults[0].end():]
    return changed.rstrip() + '\n' + new


def checked_rollback(current, expected_hash, backup):
    import hashlib
    if hashlib.sha256(current.encode()).hexdigest() != expected_hash:
        raise ValueError('Boot config changed since install; refusing to overwrite later edits')
    return backup
