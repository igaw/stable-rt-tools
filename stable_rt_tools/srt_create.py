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
import os
import shutil

from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    check_context,
    cmd,
    get_config,
    is_quilt_workflow,
    next_step,
    pipe,
)
from stable_rt_tools.srt_util_context import SrtContext


def create_patch_file(old_tag: object, new_tag: object, filename: str) -> None:
    with open(filename, 'wb') as file:
        pipe(['git', 'diff', str(old_tag), str(new_tag)], ['xz', '-9'],
             stdout=file)


def create_series(old_tag: object, new_tag: object, dirname: str) -> None:
    cmd(['git', 'format-patch', '-q', '-o', dirname,
         f'{old_tag}..{new_tag}'])

    patches = [f for f in sorted(os.listdir(dirname))
               if os.path.isfile(os.path.join(dirname, f))]
    with open(dirname + '/series', 'w') as file:
        for p in patches:
            file.write(f'{p}\n')


def export_queue(tag: str, dirname: str) -> None:
    """Write the patches/ directory of the queue tag to dirname."""
    # nothing of an earlier run may stay in the tarball
    shutil.rmtree(dirname, ignore_errors=True)
    os.makedirs(dirname)
    pipe(['git', 'archive', tag, 'patches'],
         ['tar', '-x', '-C', os.path.dirname(dirname)])


def create_tar_file(dirname: str, filename: str) -> None:
    cmd(['tar', '-C', dirname, '-cJf', filename, 'patches/'])


def create(config: Config, ctx: SrtContext) -> None:
    for d in [ctx.new.dir, ctx.new.series_dir]:
        if not os.path.exists(d):
            os.makedirs(d)

    if ctx.new_tag.is_rc:
        create_patch_file(ctx.old_tag.base, str(
            ctx.new_tag), ctx.new.patch_file)
        create_series(ctx.old_tag, ctx.new_tag, ctx.new.series_dir)
    else:
        create_patch_file(ctx.new_tag.base, str(
            ctx.new_tag), ctx.new.patch_file)
        if is_quilt_workflow(config):
            # the quilt series as released, like linux-6.18.y-rt
            export_queue(f'{ctx.new_tag}-patches', ctx.new.series_dir)
        else:
            create_series(ctx.new_tag.base, ctx.new_tag.rebase,
                          ctx.new.series_dir)

    create_tar_file(ctx.new.dir, ctx.new.tar_file)

    print(f'Created the following files in {ctx.new.dir}')
    for f in ctx.new.files:
        print(f'\t{f}')
    print('Review them')
    next_step('srt sign')


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('create')
    prs.add_argument('OLD_TAG', nargs='?')
    prs.add_argument('NEW_TAG', nargs='?')
    return prs


def execute(args: argparse.Namespace) -> None:
    ctx = SrtContext(args)
    check_context(ctx)

    create(get_config(), ctx)
