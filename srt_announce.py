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


from time import gmtime, strftime

from srt_util import get_remote_branch_name, cmd


def announce(config, ctx):
    # rfc2822.html
    # 3.3. Date and Time Specification
    timestamp = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())

    stable_rt_text = ''
    with open(config['ANNOUNCE'], 'r') as f:
        stable_rt_text = f.read()

    print(stable_rt_text.format(
        date=timestamp,
        mail_to=config['MAIL_TO'],
        branch_name=get_remote_branch_name(),
        branch_head=cmd(['git', 'rev-parse', 'HEAD']),
        major=ctx.new_tag.major,
        minor=ctx.new_tag.minor,
        patch=ctx.new_tag.patch,
        new_version=ctx.new_short_tag,
        old_version=ctx.old_short_tag,
        prj_dir=config['PRJ_DIR'],
        new_tag_rt=ctx.new_tag.rt))

    print(cmd(['git', '--no-pager', 'shortlog', '{0}..{1}'.
               format(ctx.old_tag, ctx.new_tag)]))

    print('---')

    print(cmd(['git', '--no-pager', 'diff', '--stat', '{0}..{1}'.
               format(ctx.old_tag, ctx.new_tag)]))

    print('---')

    print(cmd(['git', '--no-pager', 'diff', '{0}..{1}'.
               format(ctx.old_tag, ctx.new_tag)]))


def add_argparser(parser):
    prs = parser.add_parser('announce')
    prs.add_argument('OLD_TAG')
    prs.add_argument('NEW_TAG')
    return prs


def execute(args, config, ctx):
    if args.cmd != 'announce':
        return False

    announce(config, ctx)
