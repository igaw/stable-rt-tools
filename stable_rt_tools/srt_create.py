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
from logging import debug
from subprocess import Popen, PIPE

from stable_rt_tools.srt_util import cmd, get_config, get_context


def create_patch_file(old_tag, new_tag, filename):
    with open(filename, 'w') as file:
        c1 = ['git', 'diff', str(old_tag), str(new_tag)]
        c2 = ['xz', '-9']

        debug('run: ' + ' '.join(c1) + ' | ' + ' '.join(c2))

        p1 = Popen(c1, stdout=PIPE)
        p2 = Popen(c2, stdin=p1.stdout, stdout=file)
        p1.stdout.close()
        p2.wait()


def create_series(old_tag, new_tag, dirname):
    cmd(['git', 'format-patch', '-q', '-o', dirname,
         '{0}..{1}'.format(old_tag, new_tag)])

    patches = [f for f in sorted(os.listdir(dirname))
               if os.path.isfile(os.path.join(dirname, f))]
    with open(dirname + '/series', 'w') as file:
        for p in patches:
            file.write('{0}\n'.format(p))


def create_tar_file(dirname, filename):
    cmd(['tar', '-C', dirname, '-cJf', filename, 'patches/'])


def create(config, ctx):
    for d in [ctx.new_dir_patches, ctx.new_dir_series]:
        if not os.path.exists(d):
            os.makedirs(d)

    if ctx.new_tag.is_rc:
        create_patch_file(ctx.old_tag.base, str(ctx.new_tag), ctx.new_fln_patch)
        create_series(ctx.old_tag, ctx.new_tag, ctx.new_dir_series)
    else:
        create_patch_file(ctx.new_tag.base, str(ctx.new_tag), ctx.new_fln_patch)
        create_series(ctx.new_tag.base, ctx.new_tag.rebase, ctx.new_dir_series)

    create_tar_file(ctx.new_dir_patches, ctx.new_fln_tar)

    if ctx.fln_incr:
        create_patch_file(str(ctx.old_tag), str(ctx.new_tag), ctx.fln_incr)

    print('Created the following files in {0}'.format(ctx.new_dir_patches))
    for f in ctx.get_files():
        print('\t{0}'.format(f))
    print('Review them')


def add_argparser(parser):
    prs = parser.add_parser('create')
    prs.add_argument('OLD_TAG')
    prs.add_argument('NEW_TAG')
    return prs


def execute(args):
    ctx = get_context(args)
    if not ctx:
        sys.exit(1)

    create(get_config(), ctx)
