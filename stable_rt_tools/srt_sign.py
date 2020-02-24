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
from logging import error, debug
from subprocess import Popen, PIPE


def gpg_sign(key_id, filename):
    f = os.path.splitext(filename)[0]
    basename = os.path.splitext(os.path.basename(filename))[0]

    c1 = ['xz', '-dc', '--', filename]
    c2 = ['gpg2',
          '--local-user', '{}!'.format(key_id),
          '--quiet', '--armor', '--detach-sign',
          '-o', '{0}.sign'.format(f),
          '--set-filename', basename, '-']

    debug('run: ' + ' '.join(c1) + ' | ' + ' '.join(c2))

    p1 = Popen(c1, stdout=PIPE)
    p2 = Popen(c2, stdin=p1.stdout)
    p1.stdout.close()
    p2.wait()


def sign(config, ctx):
    for f in ctx.get_files():
        if not os.path.isfile(f):
            error('Unable to read {0}, did you remember to create?'.format(f))
            sys.exit(1)

    for f in ctx.get_files():
        gpg_sign(config['GPG_KEY_ID'], f)


def add_argparser(parser):
    prs = parser.add_parser('sign')
    prs.add_argument('OLD_TAG')
    prs.add_argument('NEW_TAG')
    return prs


def execute(args, config, ctx):
    if args.cmd != 'sign':
        return False

    sign(config, ctx)
