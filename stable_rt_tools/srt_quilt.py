#!/usr/bin/env python3
#
# srt - stable rt tooling
#
# Copyright (c) Daniel Wagner, 2026
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
from subprocess import CalledProcessError

from stable_rt_tools.srt_commit import localversion_inc
from stable_rt_tools.srt_util import cmd, read_srt_state


def _quilt_env():
    env = os.environ.copy()
    state = read_srt_state()
    if state and state.get('quilt_patches'):
        env['QUILT_PATCHES'] = state['quilt_patches']
    return env


def quilt(localversion):
    env = _quilt_env()
    try:
        while True:
            try:
                cmd(['quilt', 'push'], env=env)
            except CalledProcessError:
                break
            cmd(['quilt', 'refresh'], env=env)

        localversion_inc(localversion)
        cmd(['quilt', 'refresh'], env=env)
    finally:
        cmd(['quilt', 'pop', '-a'], env=env)


def add_argparser(parser):
    prs = parser.add_parser('quilt')
    prs.add_argument(
        '--localversion', '-l',
        default='localversion-rt',
        help='Localversion file to bump (default: localversion-rt)',
    )
    return prs


def execute(args):
    quilt(args.localversion)
