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


import os
from time import gmtime, strftime
from datetime import date, timedelta

from srt_util import confirm, get_local_branch_name, get_remote_branch_name, cmd

def create_rc_patches(config, ctx):
    branch_name = get_local_branch_name()
    cmd(['git', 'checkout', '-b', 'next-tmp'])

    srt_env = os.environ.copy()
    srt_env['SRT_REVIEW_TAG'] = str(ctx.new_tag)
    srt_path = os.path.dirname(os.path.realpath(__file__))
    cmd(['git', 'filter-branch', '-f', '--msg-filter',
         srt_path + '/srt_git_filter.py', str(ctx.old_tag) + '..'],
        env=srt_env)

    cmd(['git', 'format-patch', str(ctx.old_tag) + '..',
         '-o', ctx.new_dir_mails, '--subject-prefix', 'PATCH RT',
         '--cover-letter'])

    cmd(['git', 'checkout', branch_name])
    cmd(['git', 'branch', '-D', 'next-tmp'])


def write_rc_cover_letter(config, ctx):
    with open(ctx.new_dir_mails + '/0000-cover-letter.patch', 'r') as f:
        coverletter = f.read()

    coverletter = coverletter.replace('*** SUBJECT HERE ***',
                                      'Linux ' + str(ctx.new_tag))

    rc_text = ''
    with open(config['RC_TEXT'], 'r') as f:
        rc_text = f.read()

    today = date.today()
    rc_date = today + timedelta(weeks=1)
    rc_text = rc_text.format(new_version=ctx.new_tag,
                             release_date=rc_date)

    coverletter = coverletter.replace('*** BLURB HERE ***',
                                      rc_text)

    with open(ctx.new_dir_mails + '/0000-cover-letter.patch', 'w') as f:
        f.write(coverletter)


def send_rc_patches(config, ctx):
    gmd = ['git', 'send-email']
    gmd += ['--to="{}"'.format(t) for t in config['MAIL_TO'].split(',')]
    gmd += [ctx.new_dir_mails]

    print('Dry run')
    gmdd = gmd
    gmdd.insert(2, '--dry-run')
    cmd(gmdd, verbose=True)
    if confirm('OK to send patches?'):
        cmd(gmd)


def announce_rc(config, ctx):
    create_rc_patches(config, ctx)
    write_rc_cover_letter(config, ctx)
    send_rc_patches(config, ctx)


def announce(config, ctx):
    if ctx.is_rc:
        announce_rc(config, ctx)
        return

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
