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

from stable_rt_tools.srt_util import (check_context, cmd, confirm, get_config,
                                      get_remote_branch_name)
from stable_rt_tools.srt_util_context import SrtContext


def push(config, ctx):
    branch = get_remote_branch_name()

    args = None
    if ctx.is_rc:
        args = [config['PRJ_GIT_TREE'],
                '{0}^{{}}:{1}'.format(ctx.new_tag, branch),
                'tag', str(ctx.new_tag)]
    else:
        args = [config['PRJ_GIT_TREE'],
                '{0}^{{}}:{1}'.format(ctx.new_tag, branch),
                '+{0}-rebase^{{}}:{1}-rebase'.format(ctx.new_tag, branch),
                'tag', str(ctx.new_tag),
                'tag', '{0}-rebase'.format(ctx.new_tag)]

    gcp = ['git', 'push']
    if ctx.is_rc:
        gcp += ['-f']

    print('Dry run')
    cmd(gcp + ['-n'] + args, verbose=True)

    if confirm('OK to push?'):
        cmd(gcp + args)


def add_argparser(parser):
    prs = parser.add_parser('push')
    prs.add_argument('OLD_TAG', nargs='?')
    prs.add_argument('NEW_TAG', nargs='?')
    return prs


def execute(args):
    ctx = SrtContext(args)
    check_context(ctx)

    push(get_config(), ctx)
