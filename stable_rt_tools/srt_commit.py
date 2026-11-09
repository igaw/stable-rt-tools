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
import re
import shutil
import sys
import tempfile

from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    cmd,
    confirm,
    get_config,
    get_gpg_env,
    get_last_rt_tag,
    get_remote_branch_name,
    is_dirty,
)


def localversion_set(filename: str, version: str) -> None:
    with open(filename, 'w') as f:
        f.write(version)
        f.write('\n')


def localversion_inc(filename: str) -> None:
    with open(filename, 'r+') as f:
        line = f.readline()
        version = int(line[3:])
        f.seek(0)
        f.write(f'-rt{version+1}\n')
        f.truncate()


def get_kernel_version() -> str:
    tmp = tempfile.mkdtemp()
    cmd(['make', f'O={tmp}', 'defconfig'])
    line = cmd(['make', '-s', f'O={tmp}', 'kernelrelease'])
    shutil.rmtree(tmp)
    return line.strip()[:-1]


def last_commit_was_release_commit() -> bool:
    p = re.compile(r'^.*Linux ([0-9\.]+[-a-z0-9]+)( REBASE)*')
    lines = cmd(['git', 'log', '-1', '--pretty=%B'])
    for msg in iter(lines.splitlines()):
        m = p.match(msg)
        if not m:
            continue
        return True
    return False


def commit(config: Config, rc: int | None) -> None:
    if is_dirty():
        print('repo is dirty -> abort', file=sys.stderr)
        return

    branch_name = get_remote_branch_name()
    post_fix = branch_name.split('-')[-1]
    branch_rebase = post_fix == 'rebase'

    old_head = cmd(['git', 'rev-parse', 'HEAD'])

    if branch_rebase:
        rt = get_last_rt_tag(branch_name, '-rebase')
        if last_commit_was_release_commit():
            cmd(['git', 'reset', 'HEAD~'])
        localversion_set(config['LOCALVERSION'], rt)
    elif rc:
        rt_ver = int(get_last_rt_tag(branch_name, '-next')[3:]) + 1
        localversion_set(config['LOCALVERSION'], f'-rt{rt_ver}-rc{rc}')
    else:
        localversion_inc(config['LOCALVERSION'])

    version = get_kernel_version()
    msg = f'Linux {version}'
    if branch_rebase:
        msg = msg + ' REBASE'

    print(f'git commit -m {msg}')
    if confirm('OK to commit?'):
        cmd(['git', 'add', config['LOCALVERSION']])
        cmd(['git', 'commit', '-s', '-m', msg],
            env=get_gpg_env(config))
    else:
        cmd(['git', 'reset', '--hard', old_head])


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('commit')
    prs.add_argument('--release-candidate', '-r',
                     default=None, metavar='N', type=int)
    return prs


def execute(args: argparse.Namespace) -> None:
    commit(get_config(), args.release_candidate)
