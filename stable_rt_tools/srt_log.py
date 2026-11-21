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

"""The history of a series: what srt did, for people to read.

The steps which change something append an event to the log of their
series when they succeed, one JSON object per line, in the git common
dir next to the release state: <git common dir>/srt/<series>.log. The
worktrees of a work area share it. The status comes from the trees,
srt reads the log for one fact only: srt status takes an announcement it
found once in the archive of the mailing list from the 'announced'
event, the archive can always tell it again. A failure to write it is a
warning, the step is done anyway.

The fields of an event (see docs/userguide.rst):

  time     when the step finished, ISO 8601 in UTC
  series   the series, e.g. v6.12-rt
  step     the command, e.g. 'quilt queue', 'tag', 'prep --clear'
  release  the release the step is about, e.g. v6.12.118-rt24
  old      the release before it, if known
  srt      the version of srt
  user     git user.name, who ran the step, if set

and the details of the step, e.g. tag and commit, files, refs, the
Message-ID of a mail.
"""

import argparse
import json
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Any

from stable_rt_tools import about
from stable_rt_tools.srt_util import (
    SubParsers,
    cmd,
    get_git_common_dir,
    get_series,
    read_srt_state,
)

if TYPE_CHECKING:
    from stable_rt_tools.srt_util_context import SrtContext

# the fields every event can have, in this order; the details follow
FIELDS = ('time', 'series', 'step', 'release', 'old', 'srt', 'user')


def get_log_path(path: str | None = None) -> str | None:
    """The log of the series of the worktree at path, None for a
    detached HEAD."""
    series = get_series(path)
    if series is None:
        return None
    return os.path.join(get_git_common_dir(path), 'srt', f'{series}.log')


def _user(path: str | None) -> str | None:
    try:
        return cmd(['git', 'config', '--get', 'user.name'], cwd=path) or None
    except CalledProcessError:
        return None


def _prepared_old(release: str, path: str | None) -> str | None:
    """The old release srt prep recorded for release, if it did."""
    try:
        state = read_srt_state(path)
    except (OSError, ValueError):
        return None
    if state and state.get('new_tag') == release:
        return state.get('old_tag')
    return None


def make_event(step: str, release: object | None, old: object | None,
               path: str | None, details: Mapping[str, Any]) -> \
        dict[str, Any]:
    if release is not None and old is None:
        # the git workflow: srt commit and srt tag know only the release
        old = _prepared_old(str(release), path)
    event: dict[str, Any] = {
        'time': datetime.now(UTC).isoformat(timespec='seconds'),
        'series': get_series(path),
        'step': step,
        'release': None if release is None else str(release),
        'old': None if old is None else str(old),
        'srt': about.__version__,
        'user': _user(path),
    }
    event = {k: v for k, v in event.items() if v is not None}
    event.update((k, v) for k, v in details.items() if v is not None)
    return event


def log_step(step: str, release: object | None = None,
             old: object | None = None, path: str | None = None,
             ctx: 'SrtContext | None' = None, **details: Any) -> None:
    """Append the event of a successful step to the log of the series
    of the worktree at path (the current directory for None). ctx gives
    release, old and path of the steps after the tag."""
    # The step is done: nothing which goes wrong here may fail it.
    try:
        if ctx is not None:
            release, old, path = ctx.new_tag, ctx.old_tag, ctx.path
        log = get_log_path(path)
        if log is None:
            return
        line = json.dumps(make_event(step, release, old, path, details))
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, 'a') as f:
            f.write(line + '\n')
    except Exception as err:
        print(f'srt: warning: srt {step} is not in the log: {err}',
              file=sys.stderr)


def read_log(path: str | None = None) -> list[dict[str, Any]]:
    """The events of the series of the worktree at path, oldest first.
    Lines which are no event (cut off, edited) are left out."""
    log = get_log_path(path)
    if log is None:
        sys.exit('srt log: HEAD is detached, check out the branch of a '
                 'series')
    if not os.path.exists(log):
        return []
    events = []
    with open(log) as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def _value(value: Any) -> str:
    if isinstance(value, list):
        # files, refs (a refspec list reads as git push takes it)
        return ' '.join(_value(v) for v in value) or '-'
    text = str(value)
    if len(text) == 40 and all(c in '0123456789abcdef' for c in text):
        # a commit
        return text[:12]
    return text


def format_event(event: Mapping[str, Any]) -> str:
    """An event for people: a line with the time (UTC), the step, the
    release and who, then the details of the step, one per line,
    indented."""
    time = str(event.get('time', '?'))[:16].replace('T', ' ')
    head = f"{time}  {event.get('step', '?'):<14} " \
        f"{event.get('release', '-')}"
    if event.get('old'):
        head += f" (from {event['old']})"
    if event.get('user'):
        head += f"  by {event['user']}"
    details = [(k, _value(v)) for k, v in event.items() if k not in FIELDS]
    width = max((len(k) for k, _ in details), default=0)
    return '\n'.join([head] + [f'    {k:<{width}}  {v}'
                                for k, v in details])


def show_log(count: int | None = None, as_json: bool = False) -> None:
    events = read_log()
    if count is not None:
        events = events[-count:] if count > 0 else []
    if as_json:
        print(json.dumps(events, indent=2))
        return
    if not events:
        print(f'no history of {get_series()} yet')
        return
    # a blank line between the events: most have details below
    print('\n\n'.join(format_event(e) for e in events))


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('log',
                            help='show what srt did in the series, oldest '
                            'first',
                            description='Show the history of the series of '
                            'the current worktree: each step which changed '
                            'something, with the time in UTC, the release, '
                            'its details (tags, commits, files, pushed refs, '
                            'Message-IDs) and who ran it. It is kept in '
                            '<git common dir>/srt/<series>.log, for people '
                            'to read; where a release stands is what srt '
                            'status says.')
    prs.add_argument('-n', '--max-count', type=int, metavar='N',
                     help='only the last N steps')
    prs.add_argument('--json', action='store_true',
                     help='print the steps as JSON list, for scripts')
    return prs


def execute(args: argparse.Namespace) -> None:
    show_log(args.max_count, as_json=args.json)
