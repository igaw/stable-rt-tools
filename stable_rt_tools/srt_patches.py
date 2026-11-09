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

import subprocess
import sys
import tempfile
from email.utils import make_msgid
from time import gmtime, strftime

from stable_rt_tools.srt_util import (
    cmd,
    confirm,
    get_config,
    get_gpg_env,
    get_gpg_fingerprint,
    get_remote_branch_name,
    get_template_path,
)
from stable_rt_tools.srt_util_context import SrtContext


def get_commit_tmpl_path(config):
    return get_template_path(config, 'COMMIT_TMPL', 'commit-tmpl.txt')


def cover_letter_replacements(config, ctx):
    r = {
        "mail_to": config['MAIL_TO'],
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
        "gpg_key_fingerprint": get_gpg_fingerprint(config),
    }
    if ctx.is_rc:
        r["new_tag_rc"] = ctx.new_tag.rc
    return r


def do_patches(config, ctx, args):
    # rfc2822.html
    # 3.3. Date and Time Specification
    timestamp = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())
    stable_rt_text = ''
    with open(get_commit_tmpl_path(config)) as f:
        stable_rt_text = f.read()
    r = cover_letter_replacements(config, ctx)
    r["date"] = timestamp
    r["branch_name"] = get_remote_branch_name()
    r["branch_head"] = cmd(['git', 'rev-parse', 'HEAD'])
    r["release_tag"] = str(ctx.new_tag)
    r["series_changes"] = ''

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(stable_rt_text.format(**r))
        msg_path = f.name
    subprocess.run(['git', 'commit', '--edit', '-F', msg_path])
    tag = str(ctx.new_tag) + '-patches'
    msg = 'Patch queue for ' + str(ctx.new_tag)
    print(f'tagging as {tag} with message \'{msg}\'')
    if confirm('OK to tag?'):
        cmd(
            ['git', 'tag', '-s', '-u', config['GPG_KEY_ID'],
             '-m', msg, tag],
            env=get_gpg_env(config)
        )


def do_rebase(config, ctx, args):
    tag = str(ctx.new_tag) + '-rebase'
    print(f'tagging as {tag} with message \'{tag}\'')
    if confirm('OK to tag?'):
        cmd(
            ['git', 'tag', '-s', '-u', config['GPG_KEY_ID'],
             '-m', tag, tag],
            env=get_gpg_env(config)
        )


def do_release(config, ctx, args):
    tag = str(ctx.new_tag)
    cmd(
        ['git', 'commit', '-s', '-m', tag],
        env=get_gpg_env(config)
    )
    print(f'tagging as {tag} with message \'{tag}\'')
    if confirm('OK to tag?'):
        cmd(
            ['git', 'tag', '-s', '-u', config['GPG_KEY_ID'],
             '-m', tag, tag],
            env=get_gpg_env(config)
        )


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
    prs.add_argument('--release-version', '-r', default=None)
    return prs


DEPRECATED = {
    'patches': 'srt quilt queue',
    'rebase': 'srt quilt rebase',
}


def execute(args):
    post_fix = get_remote_branch_name().split('-')[-1]
    print('srt patches is deprecated, use "{}"'.format(
        DEPRECATED.get(post_fix, 'srt quilt merge; srt quilt release')),
        file=sys.stderr)
    # no check_context(): srt patches creates the tags it would check
    patches(get_config(), SrtContext(args), args)
