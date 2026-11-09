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

from stable_rt_tools.srt_util import check_context, cmd, get_config, pipe
from stable_rt_tools.srt_util_context import SrtContext


def create_patch_file(old_tag, new_tag, filename):
    with open(filename, 'wb') as file:
        pipe(['git', 'diff', str(old_tag), str(new_tag)], ['xz', '-9'],
             stdout=file)


def create_series(old_tag, new_tag, dirname):
    cmd(['git', 'format-patch', '-q', '-o', dirname,
         f'{old_tag}..{new_tag}'])

    patches = [f for f in sorted(os.listdir(dirname))
               if os.path.isfile(os.path.join(dirname, f))]
    with open(dirname + '/series', 'w') as file:
        for p in patches:
            file.write(f'{p}\n')


def create_tar_file(dirname, filename):
    cmd(['tar', '-C', dirname, '-cJf', filename, 'patches/'])


def create(config, ctx):
    for d in [ctx.new_dir_patches, ctx.new_dir_series]:
        if not os.path.exists(d):
            os.makedirs(d)

    if ctx.new_tag.is_rc:
        create_patch_file(ctx.old_tag.base, str(
            ctx.new_tag), ctx.new_fln_patch)
        create_series(ctx.old_tag, ctx.new_tag, ctx.new_dir_series)
    else:
        create_patch_file(ctx.new_tag.base, str(
            ctx.new_tag), ctx.new_fln_patch)
        create_series(ctx.new_tag.base, ctx.new_tag.rebase, ctx.new_dir_series)

    create_tar_file(ctx.new_dir_patches, ctx.new_fln_tar)

    print(f'Created the following files in {ctx.new_dir_patches}')
    for f in ctx.get_files():
        print(f'\t{f}')
    print('Review them')


def add_argparser(parser):
    prs = parser.add_parser('create')
    prs.add_argument('OLD_TAG', nargs='?')
    prs.add_argument('NEW_TAG', nargs='?')
    return prs


def execute(args):
    ctx = SrtContext(args)
    check_context(ctx)

    create(get_config(), ctx)
