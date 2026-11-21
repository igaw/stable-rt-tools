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
import sys

from stable_rt_tools.srt_log import log_step
from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    cmd,
    confirm,
    get_config,
    get_gpg_env,
    next_step,
    require,
)
from stable_rt_tools.srt_util_tag import Tag, release_in_message


def tag_next_step(tag: str) -> str:
    """What follows the tag in the git workflow."""
    t = Tag(tag)
    if t.is_rc:
        return 'test it, then srt announce (the review mails) and srt push'
    if t.has('rebase'):
        return 'srt create, in the worktree of the series'
    return ('in the -rebase worktree: git rebase the upstream release, '
            'srt commit and srt tag')


def tag(config: Config, rc: int | None) -> None:
    found = release_in_message(cmd(['git', 'log', '-1', '--pretty=%B']))
    if found is None:
        sys.exit('HEAD is no release commit (Linux <release>): srt commit')
    release, msg = found
    name = str(release)
    if rc and release.rc is None:
        name = f'{name}-rc{rc}'
    elif rc and release.rc != rc:
        sys.exit(f'HEAD is the release candidate {name}, not -rc{rc}')
    print(f'tagging as {name} with message \'{msg}\'')
    if not confirm('OK to tag?'):
        sys.exit('not tagged')
    cmd(['git', 'tag', '-s', '-u', require(config, 'GPG_KEY_ID'),
         '-m', msg, name],
        env=get_gpg_env(config))
    log_step('tag', name.removesuffix('-rebase'), tag=name,
             commit=cmd(['git', 'rev-parse', 'HEAD']))
    next_step(tag_next_step(name))


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser(
        'tag', help='tag the release commit (git workflow)',
        description='Git workflow: create the signed tag of the release '
        'commit at HEAD (srt commit), named after its message: '
        'v4.19.291-rt127 on the series, v4.19.291-rt127-rebase on the '
        '-rebase branch. With -r N the release candidate '
        'v4.19.291-rt127-rcN. It signs with GPG_KEY_ID and asks before it '
        'tags. The tag stays local until srt push.')
    prs.add_argument('--release-candidate', '-r',
                     default=None, metavar='N', type=int,
                     help='tag release candidate N, e.g. -rc1')
    return prs


def execute(args: argparse.Namespace) -> None:
    tag(get_config(), args.release_candidate)
