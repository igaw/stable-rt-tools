#!/usr/bin/env python3
#
# srt - stable rt tooling
#
# Copyright (c) SUSE LCC, 2025
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


import re
import shutil
import sys
import tempfile
from datetime import date, timedelta
from email.utils import make_msgid
from time import gmtime, strftime
import subprocess

from stable_rt_tools.srt_util import (check_context, cmd, confirm, get_config, get_gnupghome,
                                      get_last_rt_tag,
                                      get_remote_branch_name,
                                      is_dirty,
                                      get_gpg_fingerprint)
from stable_rt_tools.srt_util_context import SrtContext

try:
    import importlib.resources as pkg_resources
except ImportError:
    import importlib_resources as pkg_resources

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
    tmp = tempfile.mkdtemp()
    cmd(['make', 'O=%s' % tmp, 'defconfig'])
    line = cmd(['make', '-s', 'O=%s' % tmp, 'kernelrelease'])
    shutil.rmtree(tmp)
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

def get_commit_tmpl_path(config):
    if 'COMMIT_TMPL' in config:
        return config['COMMIT_TMPL']

    with pkg_resources.path('stable_rt_tools', 'commit-tmpl.txt') as p:
        return str(p)

def cover_letter_replacements(config, ctx):
    r = {"mail_to": config['MAIL_TO'],
         "major": ctx.new_tag.major,
         "minor": ctx.new_tag.minor,
         "patch": ctx.new_tag.patch,
         "new_version": ctx.new_short_tag,
         "old_version": ctx.old_short_tag,
         "prj_dir": config['PRJ_DIR'],
         "message_id": make_msgid(),
         "sender": config['SENDER'],
         "name": config['NAME'],
         "new_tag_rt": ctx.new_tag.rt,
         "gpg_key_fingerprint": get_gpg_fingerprint(config)}
    if ctx.is_rc:
        r["new_tag_rc"] = ctx.new_tag.rc
    return r

def do_patches(config, ctx, args):
    # rfc2822.html
    # 3.3. Date and Time Specification
    timestamp = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())

    stable_rt_text = ''
    with open(get_commit_tmpl_path(config), 'r') as f:
        stable_rt_text = f.read()
    r = cover_letter_replacements(config, ctx)

    r["date"] = timestamp
    r["branch_name"] = get_remote_branch_name()
    r["branch_head"] = cmd(['git', 'rev-parse', 'HEAD'])

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(stable_rt_text.format(**r))
        msg_path = f.name

    subprocess.run(['git', 'commit', '--edit', '-F', msg_path])

    tag = str(ctx.new_tag) + '-patches'
    msg = 'Patch queue for ' + str(ctx.new_tag)
    print('tagging as {0} with message \'{1}\''.format(tag, msg))
    if confirm('OK to tag?'):
        cmd(['git', 'tag', '-s', '-u', config['GPG_KEY_ID'],
             '-m', msg, tag],
            env={'GNUPGHOME': get_gnupghome(config)})


def do_rebase(config, ctx, args):
    tag = str(ctx.new_tag) + '-rebase'
    print('tagging as {0} with message \'{1}\''.format(tag, tag))
    if confirm('OK to tag?'):
        cmd(['git', 'tag', '-s', '-u', config['GPG_KEY_ID'],
             '-m', tag, tag],
            env={'GNUPGHOME': get_gnupghome(config)})


def do_release(config, ctx, args):
    tag = str(ctx.new_tag)
    cmd(['git', 'commit', '-s', '-m', tag],
        env={'GNUPGHOME': get_gnupghome(config)})

    print('tagging as {0} with message \'{1}\''.format(tag, tag))
    if confirm('OK to tag?'):
        cmd(['git', 'tag', '-s', '-u', config['GPG_KEY_ID'],
             '-m', tag, tag],
            env={'GNUPGHOME': get_gnupghome(config)})


def patches(config, ctx, args):
    branch_name = get_remote_branch_name()
    post_fix = branch_name.split('-')[-1]

    if post_fix == 'patches':
        do_patches(config, ctx, args)
    elif post_fix == 'rebase':
        do_rebase(config, ctx, args)
    else:
        do_release(config, ctx, args)


def add_argparser(parser):
    prs = parser.add_parser('patches')
    prs.add_argument('OLD_TAG', nargs='?')
    prs.add_argument('NEW_TAG', nargs='?')
    prs.add_argument('--release-version', '-r',
                     default=None)
    return prs


def execute(args):
    ctx = SrtContext(args)
    check_context(ctx)

    patches(get_config(), ctx, args)
