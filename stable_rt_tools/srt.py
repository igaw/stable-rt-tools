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
import logging
import sys
from subprocess import CalledProcessError

from stable_rt_tools import (
    about,
    srt_announce,
    srt_check,
    srt_commit,
    srt_create,
    srt_log,
    srt_mcp,
    srt_prep,
    srt_push,
    srt_quilt,
    srt_setup,
    srt_sign,
    srt_status,
    srt_tag,
    srt_upload,
)
from stable_rt_tools.srt_config import convert_config_files
from stable_rt_tools.srt_util import set_assume_yes

sub_cmd = {
    'setup': srt_setup,
    'prep': srt_prep,
    'commit': srt_commit,
    'tag': srt_tag,
    'create': srt_create,
    'sign': srt_sign,
    'upload': srt_upload,
    'push': srt_push,
    'announce': srt_announce,
    'quilt': srt_quilt,
    'status': srt_status,
    'log': srt_log,
    'check': srt_check,
    'mcp': srt_mcp,
}


def srt_get_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='srt - maintain out-of-tree patch series on top of '
        'upstream releases')
    parser.add_argument('-d', '--debug',
                        action='store_true',
                        help='Enable debug logging')
    parser.add_argument('-v', '--version',
                        action='store_true',
                        help='Show stable-rt-tools version')

    subparser = parser.add_subparsers(help='sub command help', dest='cmd')

    for _, cmd in sub_cmd.items():
        cmd.add_argparser(subparser)

    add_yes_option(parser)
    return parser


def add_yes_option(parser: argparse.ArgumentParser) -> None:
    """Add -y/--yes to parser and all its sub commands, so it can be
    given before or after them (srt -y push, srt push -y)."""
    # SUPPRESS: the default of a sub command must not reset a -y given
    # before it
    parser.add_argument('-y', '--yes', action='store_true',
                        default=argparse.SUPPRESS,
                        help='answer yes to all questions, e.g. for '
                        'scripts')
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                add_yes_option(sub)


def main() -> None:
    parser = srt_get_argparser()
    args = parser.parse_args(sys.argv[1:])
    if args.version:
        print(f'stable-rt-tools version {about.__version__}')
        return

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    set_assume_yes(getattr(args, 'yes', False))

    if args.cmd not in sub_cmd:
        parser.print_help(sys.stderr)
        sys.exit(2)
    try:
        convert_config_files()
        sub_cmd[args.cmd].execute(args)
    except CalledProcessError as e:
        if args.debug:
            raise
        sys.exit(command_failed(e))
    except KeyboardInterrupt:
        if args.debug:
            raise
        sys.exit(130)


def command_failed(e: CalledProcessError) -> str:
    """The message for a command which failed: what failed and its
    error output, instead of a traceback."""
    command = e.cmd if isinstance(e.cmd, str) else ' '.join(e.cmd)
    if e.returncode < 0:
        msg = f'srt: {command} was killed by signal {-e.returncode}'
    else:
        msg = f'srt: {command} failed (exit {e.returncode})'
    err = e.stderr
    if isinstance(err, bytes):
        err = err.decode('utf-8', errors='replace')
    if err and err.strip():
        msg += '\n' + err.strip()
    return msg


if __name__ == "__main__":
    main()
