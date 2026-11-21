#!/usr/bin/env python3
#
# srt - stable rt tooling
#
# Copyright (c) Siemens AG, 2018
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


import argparse
import os
import re
import sys

from stable_rt_tools.srt_log import log_step
from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    cmd,
    confirm,
    get_config,
    get_gpg_env,
    get_last_release_number,
    get_remote_branch_name,
    get_suffix,
    is_dirty,
    next_step,
    require,
)
from stable_rt_tools.srt_util_tag import Tag, release_in_message


def localversion_set(filename: str, version: str) -> None:
    with open(filename, 'w') as f:
        f.write(version)
        f.write('\n')


def localversion_inc(filename: str) -> None:
    """-rt22 -> -rt23, the next release after a release candidate
    (-rt22-rc1 -> -rt23) too."""
    with open(filename, 'r+') as f:
        # parsed as the localversion of a tag of any version
        tag = Tag.parse('v0.0.0' + f.readline().strip())
        if tag is None or not tag.is_release:
            sys.exit(f'{filename} does not hold a -<suffix><number> version')
        f.seek(0)
        base = tag.base[len(tag.version):]
        f.write(f'{base}-{tag.suffix}{tag.number + 1}\n')
        f.truncate()


def get_kernel_version(path: str = '.') -> str:
    """The kernel release of the tree in path, what make kernelrelease
    says before HEAD is tagged without the scm suffix (+).

    The version of the top-level Makefile (VERSION, PATCHLEVEL, SUBLEVEL,
    EXTRAVERSION) and the localversion* files of the tree root, like
    scripts/setlocalversion: all of them in sorted order, without the
    ones with '~' in their name (backups), their trailing newlines cut
    off. CONFIG_LOCALVERSION is not used, srt keeps the release in the
    localversion file.
    """
    values: dict[str, str] = {}
    with open(os.path.join(path, 'Makefile')) as f:
        for line in f:
            m = re.match(r'^(VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)'
                         r'\s*=(.*)$', line)
            if m and m.group(1) not in values:
                values[m.group(1)] = m.group(2).split('#')[0].strip()
    if not values.get('VERSION'):
        sys.exit(f'no VERSION in {os.path.join(path, "Makefile")}')

    # $(VERSION)$(if $(PATCHLEVEL),.$(PATCHLEVEL)$(if $(SUBLEVEL),
    # .$(SUBLEVEL)))$(EXTRAVERSION)
    version = values['VERSION']
    if values.get('PATCHLEVEL'):
        version += '.' + values['PATCHLEVEL']
        if values.get('SUBLEVEL'):
            version += '.' + values['SUBLEVEL']
    version += values.get('EXTRAVERSION', '')

    for name in sorted(os.listdir(path)):
        file = os.path.join(path, name)
        if not name.startswith('localversion') or '~' in name or \
                not os.path.isfile(file):
            continue
        with open(file) as f:
            version += f.read().rstrip('\n')
    return version


def last_commit_was_release_commit() -> bool:
    msg = cmd(['git', 'log', '-1', '--pretty=%B'])
    return release_in_message(msg) is not None


def commit(config: Config, rc: int | None) -> None:
    if is_dirty():
        sys.exit('repo is dirty -> abort')

    suffix = get_suffix(config)
    localversion = require(config, 'LOCALVERSION')
    branch_name = get_remote_branch_name()
    post_fix = branch_name.split('-')[-1]
    branch_rebase = post_fix == 'rebase'

    old_head = cmd(['git', 'rev-parse', 'HEAD'])

    if branch_rebase:
        number = get_last_release_number(branch_name, suffix, '-rebase')
        if last_commit_was_release_commit():
            cmd(['git', 'reset', 'HEAD~'])
        localversion_set(localversion, f'-{suffix}{number}')
    elif rc:
        number = get_last_release_number(branch_name, suffix, '-next') + 1
        localversion_set(localversion, f'-{suffix}{number}-rc{rc}')
    else:
        localversion_inc(localversion)

    version = get_kernel_version()
    msg = f'Linux {version}'
    if branch_rebase:
        msg = msg + ' REBASE'

    print(f'git commit -m {msg}')
    if confirm('OK to commit?'):
        cmd(['git', 'add', localversion])
        cmd(['git', 'commit', '-s', '-m', msg],
            env=get_gpg_env(config))
        log_step('commit', f'v{version}', branch=branch_name,
                 commit=cmd(['git', 'rev-parse', 'HEAD']), subject=msg)
        next_step(f'srt tag -r {rc}' if rc else 'srt tag')
    else:
        cmd(['git', 'reset', '--hard', old_head])


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser(
        'commit', help='commit the release (git workflow)',
        description='Git workflow: commit the new localversion as the '
        'release commit "Linux <version>", signed off. On the series it '
        'increments the localversion file, e.g. -rt23 -> -rt24; with -r N '
        'it commits the release candidate -rt24-rcN instead. On the '
        '-rebase branch it sets the number of the last release of the '
        'series and adds REBASE to the message, replacing a release commit '
        'at HEAD. The worktree must be clean. srt commit asks before it '
        'commits and resets the localversion file if you say no.')
    prs.add_argument('--release-candidate', '-r',
                     default=None, metavar='N', type=int,
                     help='commit release candidate N of the next release, '
                     'e.g. -rt24-rc1')
    return prs


def execute(args: argparse.Namespace) -> None:
    commit(get_config(), args.release_candidate)
