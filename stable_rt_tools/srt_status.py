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


"""The status of the prepared release, for both workflows.

The steps up to the tag differ (srt commit and srt tag, or srt quilt
refresh..release), the rest is the same: srt create and srt sign leave
their files in the release directory, a release published or made
on top of another one meanwhile is stale. srt status, srt mcp and agents
read the result, see status_info().
"""

import argparse
import json
import os
import re
from collections.abc import Mapping, Sequence
from subprocess import CalledProcessError
from typing import cast

from stable_rt_tools import srt_quilt
from stable_rt_tools.srt_quilt import git, pushed, rev, upstream
from stable_rt_tools.srt_util import SubParsers, read_srt_state
from stable_rt_tools.srt_util_context import release_dir, release_files

# a release like v6.12.116-rt22 and the upstream release it is made on
RELEASE_TAG = re.compile(r'v\d+\.\d+\.\d+-[a-z]+\d+')
UPSTREAM_TAG = re.compile(r'v\d+\.\d+\.\d+')


def last_tag(path: str) -> str | None:
    """The last tag on the upstream branch of the worktree."""
    try:
        return git(path, 'describe', '--tags', '--abbrev=0', '@{u}')
    except CalledProcessError:
        return None


def published(path: str, tag: str) -> bool:
    """True if the tag exists and its branch upstream contains it."""
    ref = rev(path, 'refs/tags/' + tag)
    return ref is not None and pushed(path, ref)


def stale_warnings(path: str, old: str, new: str) -> list[str]:
    """Why the prepared release old -> new doesn't fit the upstream branch
    of the worktree path (anymore)."""
    if published(path, new):
        return [f'{new} is published already, on {upstream(path)}: run '
                '"srt prep --clear" and "srt prep" for the next release']
    last = last_tag(path)
    if last is not None and RELEASE_TAG.fullmatch(last) and \
            last not in (old, new):
        return [f'{upstream(path)} is at {last}, the release was prepared '
                f'on top of {old}: run "srt prep --clear" and "srt prep"']
    return []


def file_steps(path: str, tag: str,
               tagged: bool) -> list[tuple[str, bool]]:
    """srt create and srt sign, done when the release is tagged and
    their files are there."""
    files = release_files(path, tag)
    created = tagged and all(os.path.isfile(f) for f in files)
    signed = created and all(os.path.isfile(os.path.splitext(f)[0] +
                                            '.sign') for f in files)
    return [('srt create', created), ('srt sign', signed)]


def leftover_warnings(path: str, tag: str, tagged: bool) -> list[str]:
    """Files of the release before it is tagged, e.g. of a release made
    and undone with srt 2.1: they must not be uploaded."""
    d = release_dir(path, tag)
    if tagged or not os.path.isdir(d) or not os.listdir(d):
        return []
    return [f'{d} holds files but {tag} is not tagged: remove them, srt '
            'create makes them after the release']


def release_next(tag: str, steps: Sequence[tuple[str, bool]],
                 warnings: Sequence[str],
                 overrides: Mapping[str, str]) -> str:
    """The next step of the release tag: the first one not done, told
    as overrides says (e.g. 'srt tag' -> 'srt commit and srt tag'). A
    stale release (the first warning is about the tag) is prepared
    again, a release with all steps done is published."""
    nxt = next((name for name, done in steps if not done), None)
    if warnings and warnings[0].startswith(tag):
        return 'srt prep --clear, then srt prep'
    if nxt is None:
        return 'srt upload, srt push, srt announce'
    return overrides.get(nxt, nxt)


def _info(workflow: str, old: str, new: str,
          steps: Sequence[tuple[str, bool]], warnings: list[str],
          nxt: str, **extra: object) -> dict[str, object]:
    return {
        'prepared': True,
        'workflow': workflow,
        'old_tag': old,
        'new_tag': new,
        **extra,
        'steps': [{'step': name, 'done': done} for name, done in steps],
        'warnings': warnings,
        'next': nxt,
    }


def git_status_info(old: str, new: str) -> dict[str, object]:
    """The release of the git workflow, prepared in the current worktree."""
    path = os.getcwd()
    tagged = rev(path, 'refs/tags/' + new) is not None
    steps = [('srt tag', tagged)] + file_steps(path, new, tagged)
    warnings = stale_warnings(path, old, new)
    warnings += leftover_warnings(path, new, tagged)
    nxt = release_next(new, steps, warnings,
                       {'srt tag': 'srt commit and srt tag'})
    return _info('git', old, new, steps, warnings, nxt)


def quilt_status_info(rel: srt_quilt.Release) -> dict[str, object]:
    """The release of the quilt workflow."""
    dropped, added = rel.series_changes()
    tagged = rel.done('release')
    steps = [(f'srt quilt {step}', rel.done(step))
             for step in srt_quilt.STEPS]
    steps += file_steps(rel.rt_dir, rel.release_tag, tagged)
    warnings = stale_warnings(rel.rt_dir, str(rel.old), rel.release_tag)
    warnings += leftover_warnings(rel.rt_dir, rel.release_tag, tagged)
    last_stable = last_tag(rel.stable_dir)
    if not rel.done('refresh') and last_stable and \
            UPSTREAM_TAG.fullmatch(last_stable) and last_stable != rel.base:
        warnings.append(f'upstream is at {last_stable}, the release was '
                        f'prepared for {rel.base}: run "srt prep" again')
    nxt = release_next(rel.release_tag, steps, warnings,
                       {'srt create': srt_quilt.RELEASE_NEXT})
    return _info('quilt', str(rel.old), rel.release_tag, steps, warnings,
                 nxt, dropped=dropped, added=added)


def status_info() -> dict[str, object]:
    """The prepared release, its steps, warnings and the next step."""
    state = read_srt_state()
    if not state or not state.get('new_tag'):
        return {'prepared': False,
                'next': 'srt prep (in the worktree of the series)'}
    if state.get('quilt_workflow'):
        return quilt_status_info(srt_quilt.Release(state))
    return git_status_info(state['old_tag'], state['new_tag'])


def status(as_json: bool = False) -> None:
    info = status_info()
    if as_json:
        print(json.dumps(info, indent=2))
    elif not info['prepared']:
        print('No release prepared.')
        print(f"next: {info['next']}")
    else:
        print_status(info)


def print_status(info: Mapping[str, object]) -> None:
    print(f"{info['old_tag']} -> {info['new_tag']}")
    for p in cast(list[str], info.get('dropped', [])):
        print(f'  dropped: {p}')
    for p in cast(list[str], info.get('added', [])):
        print(f'  added:   {p}')
    for step in cast(list[dict[str, object]], info['steps']):
        print('  [{}] {}'.format('x' if step['done'] else ' ', step['step']))
    for w in cast(list[str], info['warnings']):
        print(f'warning: {w}')
    print(f"next: {info['next']}")


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('status',
                            help='show the prepared release and next step')
    prs.add_argument('--json', action='store_true',
                     help='print the status as JSON, for scripts')
    return prs


def execute(args: argparse.Namespace) -> None:
    status(as_json=args.json)
