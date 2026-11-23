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

"""srt test: test the release in your lab, with TEST_COMMAND of srt.conf.

srt doesn't know how a lab tests a kernel: srt.conf says it, in up to
three phases, each a shell command with placeholders for the release
({tag}, {old_tag}, {upstream}, {series}, {worktree}): TEST_COMMAND
submits the tests, TEST_WAIT waits for them, TEST_CHECK judges them.
srt test fills them in, shows them, asks, and runs them with sh in the
worktree of the series, each noted in the history (test-submit,
test-wait, test-check). Run again it goes on where it stopped: a test
round takes hours, and a terminal that dies must not submit a second
one. Whether the release passed is for the maintainer to judge.

A small contract next to the shell commands, for scripts: SRT_RELEASE is
a JSON file with the release, and the check gets SRT_TEST_RESULT, an
empty file it may write its result to as JSON (status, summary, url and
any other keys). srt keeps the result in the history and srt status
shows it; the exit code still decides.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from typing import Any

from stable_rt_tools import srt_status
from stable_rt_tools.srt_log import log_step
from stable_rt_tools.srt_quilt import git
from stable_rt_tools.srt_util import (
    TEST_PHASES,
    Config,
    SubParsers,
    confirm,
    get_config,
    get_last_release,
    get_suffix,
    is_quilt_workflow,
    phases_text,
    print_test,
    release_test_phases,
    release_test_values,
)
from stable_rt_tools.srt_util_tag import Tag

# the environment srt test gives the command, besides the placeholders
TEST_ENV = {'tag': 'SRT_TAG', 'old_tag': 'SRT_OLD_TAG',
            'upstream': 'SRT_UPSTREAM', 'series': 'SRT_SERIES',
            'worktree': 'SRT_WORKTREE'}


def rc_at_head(path: str, suffix: str) -> str | None:
    """A release candidate of the series tagged at HEAD (git workflow,
    srt tag -r N), the newest if there are several."""
    found = []
    for name in git(path, 'tag', '--points-at', 'HEAD').splitlines():
        tag = Tag.parse(name)
        if tag is not None and tag.is_rc and tag.suffix == suffix:
            found.append(tag)
    if not found:
        return None
    return str(max(found, key=lambda t: t.rc or 0))


def release_to_test(path: str, config: Config) -> tuple[str, str | None]:
    """The release srt test tests and the one before it: a release
    candidate tagged at HEAD, else the release srt status shows (the
    prepared one, or the one the trees show)."""
    suffix = get_suffix(config)
    rc = rc_at_head(path, suffix)
    if rc is not None:
        return rc, get_last_release('HEAD', suffix, path=path)
    info = srt_status.status_info(offline=True)
    if 'new_tag' not in info:
        sys.exit('no release to test: srt prep and the release steps first')
    old = info.get('old_tag')
    return str(info['new_tag']), None if old is None else str(old)


def release_json(config: Config, values: dict[str, str]) -> dict[str, Any]:
    """The release, as SRT_RELEASE has it."""
    return {**values,
            'old_tag': values['old_tag'] or None,
            'workflow': 'quilt' if is_quilt_workflow(config) else 'git',
            'rc': Tag(values['tag']).is_rc}


def read_result(path: str, code: int) -> dict[str, Any] | None:
    """The result the command wrote to SRT_TEST_RESULT: None if it wrote
    nothing or no JSON object (a warning). A status which contradicts the
    exit code is warned about; the exit code decides."""
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        result = json.loads(text)
    except ValueError as err:
        print(f'srt: warning: SRT_TEST_RESULT is no JSON ({err}), the '
              'exit code decides', file=sys.stderr)
        return None
    if not isinstance(result, dict):
        print('srt: warning: SRT_TEST_RESULT is no JSON object, the exit '
              'code decides', file=sys.stderr)
        return None
    status = result.get('status')
    if (status == 'pass' and code != 0) or (status == 'fail' and code == 0):
        print(f'srt: warning: the result says {status}, the command exited '
              f'with {code}: the exit code decides', file=sys.stderr)
    return result


def print_result(result: dict[str, Any]) -> None:
    """The result's status, summary and url, as far as it has them."""
    line = ' - '.join(str(result[k]) for k in ('status', 'summary')
                      if result.get(k))
    if line:
        print(f'result: {line}')
    if result.get('url'):
        print(f"        {result['url']}")


def duration(seconds: float) -> str:
    """'5h12m', '3m20s', '12s'."""
    s = int(seconds)
    if s >= 3600:
        return f'{s // 3600}h{s % 3600 // 60:02d}m'
    if s >= 60:
        return f'{s // 60}m{s % 60:02d}s'
    return f'{s}s'


def phases_to_run(phases: list[tuple[str, str]],
                  events: dict[str, dict[str, Any]],
                  again: bool = False, only: str | None = None) -> \
        tuple[list[tuple[str, str]], list[str]]:
    """The phases this srt test runs and why the others are skipped: all
    with again; from wait or only the check with only; else the ones
    not done successfully yet (a submit or wait with exit 0 since the
    last submit). The check always runs again."""
    have = dict(phases)
    if only is not None:
        if only not in have:
            key = dict(TEST_PHASES)[only]
            sys.exit(f'srt test --{only}: {key} is not set in srt.conf')
        order = [p for p, _ in TEST_PHASES]
        start = order.index(only)
        return [(p, t) for p, t in phases if order.index(p) >= start], []
    if again:
        return phases, []
    run: list[tuple[str, str]] = []
    skipped: list[str] = []
    for phase, text in phases:
        done = events.get(phase)
        if phase != 'check' and done is not None and done.get('exit') == 0 \
                and not run:
            what = 'submitted' if phase == 'submit' else 'waited'
            when = srt_status.local_time(done)
            skipped.append(f'{what} already on {when} (srt test --again '
                           'submits again)')
            continue
        run.append((phase, text))
    return run, skipped


def run_phase(phase: str, text: str, path: str, env: dict[str, str],
              tag: str, old: str | None) -> tuple[int, Any]:
    """Run the command of a phase; its exit code and, for the check, the
    result it wrote to SRT_TEST_RESULT. Noted in the history as
    test-<phase>."""
    env = dict(env)
    result = None
    if phase == 'check':
        open(env['SRT_TEST_RESULT'], 'w').close()
    else:
        env.pop('SRT_TEST_RESULT', None)
    print(f'{phase}: started {datetime.now().strftime("%Y-%m-%d %H:%M")}, '
          'runs as long as the command, Ctrl-C stops it')
    sys.stdout.flush()
    start = time.monotonic()
    try:
        code = subprocess.run(['sh', '-c', text], cwd=path,
                              env=env).returncode
    except KeyboardInterrupt:
        # sh got the Ctrl-C too: note that the phase didn't finish
        code = 130
    took = time.monotonic() - start
    if phase == 'check':
        result = read_result(env['SRT_TEST_RESULT'], code)
    log_step(f'test-{phase}', tag, old, path=path, exit=code, command=text,
             seconds=round(took), result=result)
    print(f'{phase}: exit {code} after {duration(took)}')
    return code, result


def deciding_phase(phases: list[tuple[str, str]]) -> str:
    """The phase whose exit code is the test's: the check if set, else
    the wait, else the submit."""
    return phases[-1][0]


def run_test(config: Config, dry_run: bool = False, again: bool = False,
             only: str | None = None) -> int:
    """Run the phases of the test of the release (TEST_COMMAND, TEST_WAIT,
    TEST_CHECK); the exit code of the test."""
    path = srt_status.series_dir(os.getcwd())
    if not config.get('TEST_COMMAND', '').strip():
        sys.exit('TEST_COMMAND is not set: add the commands your test lab '
                 'tests a release with to srt.conf (see the user guide)')
    tag, old = release_to_test(path, config)
    phases = release_test_phases(config, tag, old, path)
    events = srt_status.test_phase_events(path, tag)
    run, skipped = phases_to_run(phases, events, again, only)
    print(f'testing {tag}' + (f' (after {old})' if old else '') +
          f' in {path}')
    for line in skipped:
        print(line)
    if not run:
        # submit and wait done, no check: the test is over
        last = srt_status.test_phase_events(path, tag)[deciding_phase(phases)]
        print(f'the test of {tag} ran already, exit {last.get("exit")} '
              '(srt test --again tests again)')
        return int(last.get('exit') or 0)
    print_test(phases_text(run, label=len(phases) > 1))
    if dry_run:
        return 0
    if not confirm('OK to run?'):
        sys.exit('not run')
    values = release_test_values(tag, old, path)
    env = dict(os.environ, **{TEST_ENV[k]: v for k, v in values.items()})
    have = [p for p, _ in phases]
    decides = deciding_phase(phases)
    code, result = 0, None
    ran: list[str] = []
    tmp = tempfile.mkdtemp(prefix='srt-test-')
    try:
        env['SRT_RELEASE'] = os.path.join(tmp, 'release.json')
        with open(env['SRT_RELEASE'], 'w') as f:
            json.dump(release_json(config, values), f, indent=2)
            f.write('\n')
        env['SRT_TEST_RESULT'] = os.path.join(tmp, 'result.json')
        for phase, text in run:
            code, result = run_phase(phase, text, path, env, tag, old)
            ran.append(phase)
            if code == 130:
                break
            if phase == 'submit':
                if code:
                    break
                if 'wait' not in have and 'check' in have:
                    print('submitted: run srt test again when the tests '
                          'are done, it goes on with the check')
                    break
            elif phase == 'wait' and code and 'check' in have:
                print(f'wait exited with {code}: the check decides')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if decides in ran or code:
        print(f'the test of {tag} exited with {code}')
    if result:
        print_result(result)
    return code


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser(
        'test', help='test the release in your lab (TEST_COMMAND)',
        description='Test the release with your test lab, in phases: '
        'submit the tests (TEST_COMMAND of srt.conf), wait for them '
        '(TEST_WAIT) and check the outcome (TEST_CHECK); the last two are '
        'optional. Each runs with sh in the worktree of the series, the '
        'placeholders ({tag}, {old_tag}, {upstream}, {series}, {worktree}) '
        'filled in and as SRT_TAG, SRT_OLD_TAG, SRT_UPSTREAM, SRT_SERIES '
        'and SRT_WORKTREE in the environment. The release is a release '
        'candidate tagged at HEAD (git workflow), else the one srt status '
        'shows. srt shows the commands and asks first, notes each phase '
        'in the history and exits with the exit code of the last phase '
        'set (the check, else the wait, else the submit). Run again, srt '
        'test goes on where it stopped: a submit or wait which succeeded '
        'is not run again. Whether the release passed is for you to '
        'judge. Between srt quilt release (or srt tag -r N) and srt '
        'create; optional, srt create doesn\'t need it.')
    prs.add_argument('--dry-run', action='store_true',
                     help='show the commands, run nothing')
    phase = prs.add_mutually_exclusive_group()
    phase.add_argument('--again', action='store_true',
                       help='start anew: submit again, also if it was '
                       'submitted already')
    phase.add_argument('--wait', dest='only', action='store_const',
                       const='wait', help='only wait and check (TEST_WAIT, '
                       'TEST_CHECK)')
    phase.add_argument('--check', dest='only', action='store_const',
                       const='check', help='only check (TEST_CHECK), e.g. '
                       'after a job was run again')
    return prs


def execute(args: argparse.Namespace) -> None:
    path = srt_status.series_dir(os.getcwd())
    code = run_test(get_config(path), dry_run=args.dry_run,
                    again=getattr(args, 'again', False),
                    only=getattr(args, 'only', None))
    if code:
        sys.exit(code)
