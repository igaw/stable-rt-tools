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


import sys
import os
import re

from srt_util import confirm, get_remote_branch_name, is_dirty, cmd


def localversion_set(filename, version):
    with open(filename, 'w') as f:
        f.write(version)
        f.write('\n')


def localversion_inc(filename):
    with open(filename, 'r+') as f:
        line = f.readline()
        version = int(line[3:])
        f.seek(0)
        f.write('-rt{0}\n'.format(version+1))
        f.truncate()


def get_kernel_version():
    if not os.path.exists('/tmp/build'):
        os.makedirs('/tmp/build')

    cmd(['make', 'O=/tmp/build', 'defconfig'])
    line = cmd(['make', '-s', 'O=/tmp/build', 'kernelrelease'])
    return line.strip()[:-1]


def last_commit_was_release_commit():
    p = re.compile(r'^.*Linux ([0-9\.]+[-a-z0-9]+)( REBASE)*')
    lines = cmd(['git', 'log', '-1', '--pretty=%B'])
    for msg in iter(lines.splitlines()):
        m = p.match(msg)
        if not m:
            continue
        return True
    return False


def get_last_rt(branch_name, postfix):
    base_branch = branch_name[:-len(postfix)]
    last_tag = cmd(['git', 'describe', base_branch])
    m = re.search(r'(-rt[-a-z0-9]+)$', last_tag)
    if not m:
        print('Last tag tag {0} does not end in -rt[0-9]+ on {1}'.
              format(last_tag, branch_name),
              file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def commit(config, rc):
    if is_dirty():
        print('repo is dirty -> abort', file=sys.stderr)
        return

    branch_name = get_remote_branch_name()
    post_fix = branch_name.split('-')[-1]
    branch_rebase = True if post_fix == 'rebase' else False

    old_head = cmd(['git', 'rev-parse', 'HEAD'])

    if branch_rebase:
        rt = get_last_rt(branch_name, '-rebase')
        if last_commit_was_release_commit():
            cmd(['git', 'reset', 'HEAD~'])
        localversion_set(config['LOCALVERSION'], rt)
    elif rc:
        rt = get_last_rt(branch_name, '-next')
        rt = rt[3:]
        rt = int(rt) + 1
        localversion_set(config['LOCALVERSION'], '-rt{0}-rc{1}'.format(rt, rc))
    else:
        localversion_inc(config['LOCALVERSION'])

    version = get_kernel_version()
    msg = 'Linux {0} {1}'.format(version, 'REBASE' if branch_rebase else '')

    print('git commit -m {0}'.format(msg))
    if confirm('OK to commit?'):
        cmd(['git', 'add', config['LOCALVERSION']])
        cmd(['git', 'commit', '-s', '-m', msg])
    else:
        cmd(['git', 'reset', '--hard', old_head])


def add_argparser(parser):
    prs = parser.add_parser('commit')
    prs.add_argument('--release-canditate', '-r',
                     default=None, metavar='N', type=int)
    return prs


def execute(args, config, ctx):
    if args.cmd != 'commit':
        return False

    commit(config, args.release_canditate)
