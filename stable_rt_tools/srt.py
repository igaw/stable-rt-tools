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


def srt_get_argparser():
    parser = argparse.ArgumentParser(description='srt - stable -rt tool')
    parser.add_argument('-d', '--debug',
                        action='store_true',
                        help='Enable debug logging')

    subparser = parser.add_subparsers(help='sub command help', dest='cmd')

    sub_cmd = {
        'commit': srt_commit,
        'tag': srt_tag,
        'create': srt_create,
        'sign': srt_sign,
        'upload': srt_upload,
        'push': srt_push,
        'announce': srt_announce,
    }

    for _,cmd in sub_cmd.items():
        cmd.add_argparser(subparser)

    return parser


def main():
    parser = srt_get_argparser()
    args = parser.parse_args(sys.argv[1:])
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    if args.cmd in sub_cmd:
        sub_cmd[args.cmd].execute(args)


if __name__ == "__main__":
    main()
