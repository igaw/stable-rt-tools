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

from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    check_context,
    clear_srt_state,
    cmd,
    confirm,
    get_config,
    get_remote_branch_name,
    interactive,
    is_quilt_workflow,
    next_step,
    require,
)
from stable_rt_tools.srt_util_context import SrtContext


def push(config: Config, ctx: SrtContext, dry_run: bool = False) -> None:
    branch = get_remote_branch_name()

    args = None
    if ctx.is_rc:
        args = [require(config, 'PRJ_GIT_TREE'),
                f'{ctx.new_tag}^{{}}:{branch}',
                'tag', str(ctx.new_tag)]
    else:
        args = [
            require(config, 'PRJ_GIT_TREE'),
            f'{ctx.new_tag}^{{}}:{branch}',
            f'+{ctx.new_tag}-rebase^{{}}:{branch}-rebase',
            'tag', str(ctx.new_tag),
            'tag', f'{ctx.new_tag}-rebase'
        ]
        if is_quilt_workflow(config):
            patches_branch = branch + '-patches'
            patches_tag = str(ctx.new_tag) + '-patches'
            args += [patches_branch, 'tag', patches_tag]

    gcp = ['git', 'push']
    if ctx.is_rc:
        gcp += ['-f']

    print('Dry run')
    cmd(gcp + ['-n'] + args, verbose=True)
    if dry_run:
        return

    if confirm('OK to push?'):
        cmd(gcp + args)
        clear_srt_state()
        if not ctx.is_rc:
            offer_announcement(config, ctx)


def offer_announcement(config: Config, ctx: SrtContext) -> None:
    """After the push: open the announcement in MAILER, or say how."""
    from stable_rt_tools.srt_announce import mail_announcement
    if not config.get('MAILER'):
        next_step('srt announce > ../announce, then send it, e.g. with '
                  'mutt -H ../announce (or set MAILER in srt.conf)')
        return
    # not from scripts or an agent: the mail client is for a person
    if interactive() and confirm('Open the announcement in the mail '
                                      'client?'):
        mail_announcement(config, ctx)
    else:
        next_step('srt announce --mail')


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('push')
    prs.add_argument('OLD_TAG', nargs='?')
    prs.add_argument('NEW_TAG', nargs='?')
    prs.add_argument('-n', '--dry-run', action='store_true',
                     help='only show what would be pushed (git push -n)')
    return prs


def execute(args: argparse.Namespace) -> None:
    ctx = SrtContext(args)
    check_context(ctx)

    push(get_config(), ctx, dry_run=args.dry_run)
