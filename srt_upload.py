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
from pprint import pformat
from subprocess import CalledProcessError

from srt_util import cmd, confirm


def upload(config, ctx):
    for f in ctx.get_files():
        if not os.path.isfile(f):
            print('Unable to read {0}, did you remember to create?'.format(f))
            sys.exit(1)

    path = config['PRJ_DIR']
    older_path = path + '/' + 'older'
    incr_path = path + '/' + 'incr'

    kup = ['kup']

    for i, f in enumerate(ctx.get_files()):
        basename = os.path.splitext(f)[0]
        if i == 2:
            kup.extend(['put', basename + '.xz', basename + '.sign',
                        incr_path + '/', '--'])
        else:
            kup.extend(['put', basename + '.xz', basename + '.sign',
                        older_path + '/', '--'])

    # skip incr_file
    for f in ctx.get_files()[:2]:
        kup.extend(['ln', older_path + '/' + os.path.basename(f), '../', '--'])

    # If we're uploading an -rc release, don't delete the old release.
    if not ctx.is_rc:
        kup.extend(['rm', path + '/' + os.path.basename(ctx.old_fln_patch),
                    '--'])
        kup.extend(['rm', path + '/' + os.path.basename(ctx.old_fln_tar),
                    '--'])

    kup.extend(['ls', path])

    print(pformat(kup))
    if confirm('OK to commit?'):
        try:
            cmd(kup)
        except CalledProcessError as e:
            print('kup failed with error code {0}'.format(e.returncode),
                  file=sys.stderr)


def add_argparser(parser):
    prs = parser.add_parser('upload')
    prs.add_argument('OLD_TAG')
    prs.add_argument('NEW_TAG')
    return prs


def execute(args, config, ctx):
    if args.cmd != 'upload':
        return False

    upload(config, ctx)
