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


import argparse
import json
import os

from stable_rt_tools import srt_quilt
from stable_rt_tools.srt_util import SubParsers, read_srt_state


def git_status_info(old: str, new: str) -> dict[str, object]:
    """The release of the git workflow, prepared in the current worktree."""
    path = os.getcwd()
    tagged = srt_quilt.rev(path, 'refs/tags/' + new) is not None
    steps = [('srt tag', tagged)] + srt_quilt.file_steps(path, new, tagged)
    warnings = srt_quilt.stale_warnings(path, old, new)
    warnings += srt_quilt.leftover_warnings(path, new, tagged)
    nxt = next((name for name, done in steps if not done), None)
    if warnings and warnings[0].startswith(new):
        nxt = 'srt prep --clear, then srt prep'
    elif nxt == 'srt tag':
        nxt = 'srt commit and srt tag'
    elif nxt is None:
        nxt = 'srt upload, srt push, srt announce'
    return {
        'prepared': True,
        'workflow': 'git',
        'old_tag': old,
        'new_tag': new,
        'steps': [{'step': name, 'done': done} for name, done in steps],
        'warnings': warnings,
        'next': nxt,
    }


def status_info() -> dict[str, object]:
    """The prepared release, its steps, warnings and the next step."""
    state = read_srt_state()
    if not state or not state.get('new_tag'):
        return {'prepared': False,
                'next': 'srt prep (in the worktree of the series)'}
    if state.get('quilt_workflow'):
        return srt_quilt.status_info(srt_quilt.Release(state))
    return git_status_info(state['old_tag'], state['new_tag'])


def status(as_json: bool = False) -> None:
    info = status_info()
    if as_json:
        print(json.dumps(info, indent=2))
    elif not info['prepared']:
        print('No release prepared.')
        print(f"next: {info['next']}")
    else:
        srt_quilt.print_status(info)


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('status',
                            help='show the prepared release and next step')
    prs.add_argument('--json', action='store_true',
                     help='print the status as JSON, for scripts')
    return prs


def execute(args: argparse.Namespace) -> None:
    status(as_json=args.json)
