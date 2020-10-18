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
from email.utils import make_msgid
try:
    import importlib.resources as pkg_resources
except ImportError:
    import importlib_resources as pkg_resources

from stable_rt_tools.srt_util import (confirm, get_local_branch_name,
                                      get_remote_branch_name, cmd, get_config,
                                      get_context)

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

def cover_letter_replacements(config, ctx):
    r = {"mail_to" : config['MAIL_TO'],
         "major" : ctx.new_tag.major,
         "minor" : ctx.new_tag.minor,
         "patch" : ctx.new_tag.patch,
         "new_version" : ctx.new_short_tag,
         "old_version" : ctx.old_short_tag,
         "prj_dir" : config['PRJ_DIR'],
         "message_id" : make_msgid(),
         "sender" : config['SENDER'],
         "name" : config['NAME'],
         "new_tag_rt" : ctx.new_tag.rt}
    if ctx.is_rc:
        r["new_tag_rc"] = ctx.new_tag.rc
    return r

def write_rc_cover_letter(config, ctx):
    with open(ctx.new_dir_mails + '/0000-cover-letter.patch', 'r') as f:
        coverletter = f.read()

    coverletter = coverletter.replace('*** SUBJECT HERE ***',
                                      'Linux ' + str(ctx.new_tag))

    rc_text = ''
    with open(get_rc_templ_path(config), 'r') as f:
        rc_text = f.read()

    r = cover_letter_replacements(config, ctx)

    today = date.today()
    rc_date = today + timedelta(weeks=1)
    r["release_date"] = rc_date

    rc_text = rc_text.format(**r)

    coverletter = coverletter.replace('*** BLURB HERE ***',
                                      rc_text)

    with open(ctx.new_dir_mails + '/0000-cover-letter.patch', 'w') as f:
        f.write(coverletter)


def send_rc_patches(config, ctx, args):
    gmd = ['git', 'send-email', '--confirm=never']
    if args.suppress_cc:
        gmd += ['--suppress-cc=all']
    gmd += ['--to="{}"'.format(t) for t in config['MAIL_TO'].split(',')]
    gmd += [ctx.new_dir_mails]

    print('Dry run')
    gmdd = gmd.copy()
    gmdd.insert(2, '--dry-run')
    print(cmd(gmdd, verbose=True))
    if confirm('OK to send patches?'):
        cmd(gmd)


def announce_rc(config, ctx, args):
    create_rc_patches(config, ctx)
    write_rc_cover_letter(config, ctx)
    send_rc_patches(config, ctx, args)


def get_announce_tmpl_path(config):
    if 'ANNOUNCE' in config:
        return config['ANNOUNCE']

    with pkg_resources.path('stable_rt_tools', 'announce-srt.txt') as p:
        return str(p)


def get_rc_templ_path(config):
    if 'RC_TEXT' in config:
        return config['RC_TEXT']

    with pkg_resources.path('stable_rt_tools', 'announce-srt-rc.txt') as p:
        return str(p)


def announce(config, ctx, args):
    if ctx.is_rc:
        announce_rc(config, ctx, args)
        return

    # rfc2822.html
    # 3.3. Date and Time Specification
    timestamp = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())

    stable_rt_text = ''
    with open(get_announce_tmpl_path(config), 'r') as f:
        stable_rt_text = f.read()

    r = cover_letter_replacements(config, ctx)

    r["date"] = timestamp
    r["branch_name"] = get_remote_branch_name()
    r["branch_head"] = cmd(['git', 'rev-parse', 'HEAD'])

    print(stable_rt_text.format(**r))

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
    prs.add_argument('--suppress-cc', '-s', action="store_true", default=False,
                     help='Don''t auto-cc anyone (for testing)')
    return prs


def execute(args):
    ctx = get_context(args)
    if not ctx:
        sys.exit(1)

    announce(get_config(), ctx, args)
