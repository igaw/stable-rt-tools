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


import re

from stable_rt_tools.srt_util import (cmd, confirm, get_config, get_gnupghome)


def tag(config, rc):
    p = re.compile(r'^.*Linux ([0-9\.]+[-a-z0-9]+)( REBASE)*')
    lines = cmd(['git', 'log', '-1', '--pretty=%B'])
    for msg in iter(lines.splitlines()):
        m = p.match(msg)
        if not m:
            continue

        tag = 'v' + m.group(1) + ('-rebase' if m.group(2) else '')
        if rc:
            tag = tag + '-rc{0}'.format(rc)
        print('tagging as {0} with message \'{1}\''.format(tag, msg))
        if confirm('OK to tag?'):
            cmd(['git', 'tag', '-s', '-u', config['GPG_KEY_ID'],
                 '-m', msg, tag],
                env={'GNUPGHOME': get_gnupghome(config)})


def add_argparser(parser):
    prs = parser.add_parser('tag')
    prs.add_argument('--release-candidate', '-r',
                     default=None, metavar='N', type=int)
    return prs


def execute(args):
    tag(get_config(), args.release_candidate)
