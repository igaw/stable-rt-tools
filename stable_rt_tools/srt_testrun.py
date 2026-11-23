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

srt doesn't know how a lab tests a kernel: TEST_COMMAND says it, with
placeholders for the release ({tag}, {old_tag}, {upstream}, {series},
{worktree}). srt test fills them in, shows the command, asks, and runs it
with sh in the worktree of the series. Whether the release passed is
for the maintainer to judge: srt only records that the test ran and its
exit code.

A small contract next to the shell command, for scripts: SRT_RELEASE is
a JSON file with the release, SRT_TEST_RESULT an empty file the command
may write its result to as JSON (status, summary, url and any other
keys). srt keeps the result in the history and srt status shows it; the
exit code still decides.
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
    Config,
    SubParsers,
    confirm,
    get_config,
    get_last_release,
    get_suffix,
    is_quilt_workflow,
    print_test,
    release_test_values,
    release_testing_command,
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


def run_test(config: Config, dry_run: bool = False) -> int:
    """Run TEST_COMMAND for the release; its exit code."""
    path = srt_status.series_dir(os.getcwd())
    if not config.get('TEST_COMMAND', '').strip():
        sys.exit('TEST_COMMAND is not set: add the commands your test lab '
                 'tests a release with to srt.conf (see the user guide)')
    tag, old = release_to_test(path, config)
    text = release_testing_command(config, tag, old, path)
    assert text is not None
    print(f'testing {tag}' + (f' (after {old})' if old else '') +
          f' in {path}')
    print_test(text)
    if dry_run:
        return 0
    if not confirm('OK to run?'):
        sys.exit('not run')
    values = release_test_values(tag, old, path)
    env = dict(os.environ, **{TEST_ENV[k]: v for k, v in values.items()})
    tmp = tempfile.mkdtemp(prefix='srt-test-')
    try:
        env['SRT_RELEASE'] = os.path.join(tmp, 'release.json')
        with open(env['SRT_RELEASE'], 'w') as f:
            json.dump(release_json(config, values), f, indent=2)
            f.write('\n')
        env['SRT_TEST_RESULT'] = os.path.join(tmp, 'result.json')
        open(env['SRT_TEST_RESULT'], 'w').close()
        print(f'started {datetime.now().strftime("%Y-%m-%d %H:%M")}: '
              'srt test runs as long as the command does, Ctrl-C stops '
              'both')
        sys.stdout.flush()
        start = time.monotonic()
        try:
            code = subprocess.run(['sh', '-c', text], cwd=path,
                                  env=env).returncode
        except KeyboardInterrupt:
            # sh got the Ctrl-C too: note that the test didn't finish
            code = 130
        took = time.monotonic() - start
        result = read_result(env['SRT_TEST_RESULT'], code)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log_step('test', tag, old, path=path, exit=code, command=text,
             seconds=round(took), result=result)
    print(f'the test of {tag} exited with {code} after {duration(took)}')
    if result:
        print_result(result)
    return code


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser(
        'test', help='test the release in your lab (TEST_COMMAND)',
        description='Test the release with your test lab: run TEST_COMMAND '
        'of srt.conf with sh in the worktree of the series, its '
        'placeholders ({tag}, {old_tag}, {upstream}, {series}, '
        '{worktree}) filled in and as SRT_TAG, SRT_OLD_TAG, SRT_UPSTREAM, '
        'SRT_SERIES and SRT_WORKTREE in the environment. The release is a '
        'release candidate tagged at HEAD (git workflow), else the one srt '
        'status shows. srt shows the command and asks first; it exits '
        'with the exit code of the command and notes in the history that '
        'the test ran. Whether the release passed is for you to judge. '
        'Between srt quilt release (or srt tag -r N) and srt create; '
        'optional, srt create doesn\'t need it.')
    prs.add_argument('--dry-run', action='store_true',
                     help='show the command, run nothing')
    return prs


def execute(args: argparse.Namespace) -> None:
    path = srt_status.series_dir(os.getcwd())
    code = run_test(get_config(path), dry_run=args.dry_run)
    if code:
        sys.exit(code)
