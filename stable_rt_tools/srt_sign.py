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
import sys
from logging import error

from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    check_context,
    get_config,
    get_gnupghome,
    pipe,
)
from stable_rt_tools.srt_util_context import SrtContext


def gpg_sign(config: Config, filename: str) -> None:
    f = os.path.splitext(filename)[0]
    basename = os.path.splitext(os.path.basename(filename))[0]

    xz = ['xz', '-dc', '--', filename]
    gpg = [
        'gpg2',
        '--homedir', get_gnupghome(config),
        '--local-user', '{}!'.format(config['GPG_KEY_ID']),
        '--quiet', '--armor', '--detach-sign',
        '-o', f'{f}.sign',
        '--set-filename', basename, '-'
    ]
    pipe(xz, gpg)


def sign(config: Config, ctx: SrtContext) -> None:
    for f in ctx.get_files():
        if not os.path.isfile(f):
            error(f'Unable to read {f}, did you remember to create?')
            sys.exit(1)
        gpg_sign(config, f)


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('sign')
    prs.add_argument('OLD_TAG', nargs='?')
    prs.add_argument('NEW_TAG', nargs='?')
    return prs


def execute(args: argparse.Namespace) -> None:
    ctx = SrtContext(args)
    check_context(ctx)

    sign(get_config(), ctx)
