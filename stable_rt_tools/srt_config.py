#!/usr/bin/env python3
#
# srt - stable rt tooling
#
# Copyright (c) Daniel Wagner, 2026
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE


"""Convert srt.conf files from srt 1.x to the 2.0 format.

srt 1.x needed a group for every branch of a series, e.g.
[linux/stable-rt/v6.12-rt], [linux/stable-rt/v6.12-rt-patches] and
[linux/stable-rt/v6.12-rt-rebase], and enabled the quilt workflow with
quilt_workflow = true. srt 2.0 uses one group per series, WORKFLOW = quilt,
derives LOCALVERSION and shares common settings in [DEFAULT].
"""

import os
import sys
import tempfile
from configparser import ConfigParser

from stable_rt_tools.srt_util import config_dirs

BRANCH_SUFFIXES = ('-patches', '-rebase', '-next')
DEFAULT = 'DEFAULT'


def _parser() -> ConfigParser:
    # [DEFAULT] as a plain section: every group shows only its own
    # settings. Keep the case of the keys and the values as written.
    parser = ConfigParser(default_section='\0', interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    return parser


def _get(parser: ConfigParser, section: str, key: str) -> str | None:
    """A setting, ignoring the case of the key like srt does."""
    for k, v in parser.items(section):
        if k.lower() == key.lower():
            return v
    return None


def _remove(parser: ConfigParser, section: str, key: str) -> None:
    for k in list(parser.options(section)):
        if k.lower() == key.lower():
            parser.remove_option(section, k)


def _groups(parser: ConfigParser) -> list[str]:
    return [s for s in parser.sections() if s != DEFAULT]


def convert(parser: ConfigParser) -> list[str]:
    """Convert parser in place, return what was changed."""
    changes = []
    defaults = parser.has_section(DEFAULT)

    for group in _groups(parser):
        old = _get(parser, group, 'quilt_workflow')
        if old is None:
            continue
        _remove(parser, group, 'quilt_workflow')
        if old.lower() in ('1', 'yes', 'true', 'on'):
            parser.set(group, 'WORKFLOW', 'quilt')
            changes.append(f'[{group}]: quilt_workflow = {old} -> '
                           'WORKFLOW = quilt')
        else:
            changes.append(f'[{group}]: dropped quilt_workflow = {old}')

    for group in _groups(parser):
        for suffix in BRANCH_SUFFIXES:
            series = group.removesuffix(suffix)
            if series == group or not parser.has_section(series):
                continue
            own = dict(parser.items(group))
            if all(_get(parser, series, k) == v for k, v in own.items()):
                parser.remove_section(group)
                changes.append(f'[{group}]: dropped, [{series}] has the same '
                               'settings')
            break

    for group in _groups(parser):
        suffix = (_get(parser, group, 'SUFFIX') or
                  (defaults and _get(parser, DEFAULT, 'SUFFIX')) or 'rt')
        if _get(parser, group, 'LOCALVERSION') == f'localversion-{suffix}':
            _remove(parser, group, 'LOCALVERSION')
            changes.append(f'[{group}]: dropped LOCALVERSION, it is the '
                           'default')

    groups = _groups(parser)
    if len(groups) > 1:
        first = dict(parser.items(groups[0]))
        for key, value in first.items():
            if any(_get(parser, g, key) != value for g in groups[1:]):
                continue
            if defaults and _get(parser, DEFAULT, key) is not None:
                continue
            if not parser.has_section(DEFAULT):
                parser.add_section(DEFAULT)
                defaults = True
            parser.set(DEFAULT, key, value)
            for g in groups:
                _remove(parser, g, key)
            changes.append(f'{key}: the same in all groups, moved to '
                           '[DEFAULT]')
    return changes


def _write(parser: ConfigParser, path: str) -> None:
    # [DEFAULT] first, as configparser would write it
    order = ([DEFAULT] if parser.has_section(DEFAULT) else []) + \
        _groups(parser)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or '.',
                               prefix='.srt.conf.')
    try:
        with os.fdopen(fd, 'w') as f:
            for section in order:
                f.write(f'[{section}]\n')
                for key, value in parser.items(section):
                    f.write(f'{key} = {value}\n')
                f.write('\n')
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _backup_path(path: str) -> str:
    backup = path + '.bak'
    n = 1
    while os.path.exists(backup):
        backup = f'{path}.bak{n}'
        n += 1
    return backup


def convert_file(path: str) -> list[str]:
    """Convert the srt.conf at path if needed, return the changes."""
    parser = _parser()
    with open(path) as f:
        text = f.read()
    parser.read_string(text, source=path)
    changes = convert(parser)
    if not changes:
        return []
    if not os.access(path, os.W_OK) or \
            not os.access(os.path.dirname(path) or '.', os.W_OK):
        print(f'srt: {path} uses the srt 1.x format, convert it by '
              'running srt as its owner', file=sys.stderr)
        return []
    backup = _backup_path(path)
    with open(backup, 'w') as f:
        f.write(text)
    _write(parser, path)
    print(f'srt: converted {path} to the srt 2.0 format, the old file is '
          f'{backup}:', file=sys.stderr)
    for change in changes:
        print(f'  {change}', file=sys.stderr)
    return changes


def convert_config_files() -> None:
    """Convert the srt.conf files srt reads, once."""
    for d in config_dirs():
        path = os.path.join(d, 'srt.conf')
        if os.path.isfile(path):
            convert_file(path)
