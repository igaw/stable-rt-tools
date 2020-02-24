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
import argparse
import logging

from stable_rt_tools import srt_announce
from stable_rt_tools import srt_commit
from stable_rt_tools import srt_create
from stable_rt_tools import srt_push
from stable_rt_tools import srt_sign
from stable_rt_tools import srt_tag
from stable_rt_tools import srt_upload

from stable_rt_tools.srt_util import get_config, get_context


def main():
    parser = argparse.ArgumentParser(description='srt - stable -rt tool')
    parser.add_argument('-d', '--debug',
                        action='store_true',
                        help='Enable debug logging')

    subparser = parser.add_subparsers(help='sub command help', dest='cmd')

    sub_cmd = [
        srt_commit,
        srt_tag,
        srt_create,
        srt_sign,
        srt_upload,
        srt_push,
        srt_announce,
    ]

    for cmd in sub_cmd:
        cmd.add_argparser(subparser)

    args = parser.parse_args(sys.argv[1:])
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    config = get_config()
    ctx = get_context(args)
    if not ctx:
        sys.exit(1)

    for cmd in sub_cmd:
        cmd.execute(args, config, ctx)


if __name__ == "__main__":
    main()
