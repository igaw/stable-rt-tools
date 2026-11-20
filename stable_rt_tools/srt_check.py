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

"""srt check: sanity checks between the trees of a release.

The reviews the documentation asks for (git diff of the refreshed queue,
the -rebase tree against the release, the files srt create made), as
checks. A check runs once the step it checks is done.
"""

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from subprocess import CalledProcessError

from stable_rt_tools import srt_quilt
from stable_rt_tools.srt_announce import delta_base
from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    cmd,
    get_config,
    get_gnupghome,
    is_quilt_workflow,
    read_srt_state,
)
from stable_rt_tools.srt_util_context import SrtContext, release_files

OK, WARN, FAIL, SKIP = 'ok', 'warn', 'fail', 'skip'

# a hunk header, the line numbers change with every refresh
_HUNK = re.compile(r'^@@ -\d+(,\d+)? \+\d+(,\d+)? @@.*$', re.MULTILINE)
# the lines git adds to a diff and quilt refresh doesn't write
_GIT_LINES = re.compile(r'^(diff --git |index [0-9a-f]+\.\.[0-9a-f]+|'
                        r'(new|deleted) file mode ).*\n', re.MULTILINE)


@dataclass
class Check:
    name: str
    result: str
    text: str
    details: list[str] = field(default_factory=list)


@contextlib.contextmanager
def _cwd(path: str) -> Iterator[None]:
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _git(path: str, *args: str) -> str:
    return cmd(['git', '-C', path, *args])


def _show(path: str, ref: str, name: str) -> str | None:
    try:
        return _git(path, 'show', f'{ref}:{name}')
    except CalledProcessError:
        return None


def without_offsets(patch: str) -> str:
    """The patch without the line numbers of its hunks, and without the
    lines git adds, a refresh of a patch from git format-patch drops them."""
    return _HUNK.sub('@@', _GIT_LINES.sub('', patch))


#
# quilt workflow
#

def check_upstream(rel: srt_quilt.Release) -> Check:
    if rel.done('refresh'):
        return Check('upstream', SKIP, 'the queue is refreshed already')
    head = srt_quilt.rev(rel.stable_dir, 'HEAD')
    if head != srt_quilt.rev(rel.stable_dir, rel.base):
        return Check('upstream', FAIL,
                     f'{rel.stable_dir} is not at {rel.base}: srt prep')
    return Check('upstream', OK, f'{rel.stable_dir} is at {rel.base}')


def check_queue(rel: srt_quilt.Release) -> Check:
    """The refreshed queue against the queue of the last release: patches
    added and dropped, and the ones which changed beyond hunk offsets."""
    if not rel.done('refresh'):
        return Check('queue', SKIP, 'the queue is not refreshed yet')
    queued = rel.done('queue')
    old_lv = srt_quilt.rt_localversion(rel.old)
    new_lv = srt_quilt.rt_localversion(rel.new)
    dropped, added = rel.series_changes()
    changed = []
    for name in rel.new_series():
        old = _show(rel.patches_dir, rel.old_queue_tag, f'patches/{name}')
        if old is None:
            continue
        if queued:
            new = _show(rel.patches_dir, rel.queue_tag, f'patches/{name}')
        else:
            with open(os.path.join(rel.quilt_patches, name)) as f:
                new = f.read().strip()
        # the localversion patch changes with every release
        old = old.replace(f'+{old_lv}\n', f'+{new_lv}\n')
        if old.endswith(f'+{old_lv}'):
            old = old[:-len(old_lv)] + new_lv
        if without_offsets(old) != without_offsets(new or ''):
            changed.append(name)
    ref = rel.queue_tag if queued else ''
    review = (f'git -C {rel.patches_dir} diff {rel.old_queue_tag} {ref}'
              .rstrip() + ' -- ' +
              ' '.join(f'patches/{n}' for n in changed + ['series']))
    details = [f'dropped {p}' for p in dropped] + \
        [f'added {p}' for p in added] + \
        [f'changed {p}' for p in changed]
    summary = (f'{len(added)} added, {len(dropped)} dropped, '
               f'{len(changed)} changed beyond hunk offsets')
    if changed or added or dropped:
        return Check('queue', WARN, f'{summary}; review: {review}', details)
    return Check('queue', OK, f'{summary} against {rel.old_queue_tag}')


def check_rebase(rel: srt_quilt.Release) -> Check:
    """-rebase is upstream with the patches of the queue, in order."""
    if not rel.done('rebase'):
        return Check('rebase', SKIP, f'{rel.rebase_tag} is not tagged yet')
    log = _git(rel.rebase_dir, 'log', '--reverse', '--format=%s',
               f'{rel.base}..{rel.rebase_tag}').splitlines()
    want = []
    for name in rel.new_series():
        text = _show(rel.patches_dir, rel.queue_tag, f'patches/{name}')
        want.append(srt_quilt.patch_subject(text or '') or name)
    if not srt_quilt.is_ancestor(rel.rebase_dir, rel.base, rel.rebase_tag):
        return Check('rebase', FAIL,
                     f'{rel.rebase_tag} is not based on {rel.base}')
    if log != want:
        diff = [f'- {s}' for s in want if s not in log] + \
            [f'+ {s}' for s in log if s not in want]
        return Check('rebase', FAIL,
                     f'{rel.rebase_tag} is not {rel.base} with the patches '
                     f'of {rel.queue_tag}', diff)
    return Check('rebase', OK, f'{rel.rebase_tag} is {rel.base} with the '
                 f'{len(want)} patches of {rel.queue_tag}')


def check_merge(rel: srt_quilt.Release) -> Check:
    """The stable merge on the series: a clean message, as committed by
    srt quilt merge."""
    if not srt_quilt.is_ancestor(rel.rt_dir, rel.base):
        return Check('merge', SKIP, f'{rel.base} is not merged yet')
    merges = _git(rel.rt_dir, 'log', '--merges', '--first-parent',
                  '--format=%H', f'{rel.old}..HEAD').splitlines()
    for m in merges:
        body = _git(rel.rt_dir, 'log', '-1', '--format=%B', m)
        comments = [line for line in body.splitlines()
                    if line.startswith('#')]
        if comments:
            return Check('merge', WARN,
                         f'the message of {m[:12]} has comment lines (the '
                         'signature of the tag?)', comments[:3])
    return Check('merge', OK, f'{rel.base} is merged')


def check_release(rel: srt_quilt.Release) -> Check:
    if not rel.done('release'):
        return Check('release', SKIP, f'{rel.release_tag} is not tagged yet')
    return check_trees(rel.rt_dir, rel.release_tag, rel.rebase_tag)


#
# both workflows
#

def check_trees(path: str, release: str, rebase: str) -> Check:
    """The release and its -rebase have the same tree."""
    try:
        a = _git(path, 'rev-parse', release + '^{tree}')
        b = _git(path, 'rev-parse', rebase + '^{tree}')
    except CalledProcessError:
        return Check('release', SKIP, f'{release} or {rebase} is missing')
    if a != b:
        stat = _git(path, 'diff', '--stat', rebase, release)
        return Check('release', FAIL, f'{release} differs from {rebase}',
                     stat.splitlines())
    return Check('release', OK, f'{release} has the tree of {rebase}')


def check_delta(path: str, ctx: SrtContext) -> Check:
    """The change of the release itself, as the announcement shows it."""
    new = str(ctx.new_tag)
    if srt_quilt.rev(path, 'refs/tags/' + new) is None:
        return Check('delta', SKIP, f'{new} is not tagged yet')
    with _cwd(path):
        base = delta_base(ctx)
    stat = _git(path, 'diff', '--stat', base, new).splitlines()
    return Check('delta', OK, f'{ctx.old_tag}..{new} without the upstream '
                 f'update: {stat[-1].strip() if stat else "no change"}',
                 stat[:-1])


def _xz(path: str) -> bytes:
    return subprocess.run(['xz', '-dc', path], check=True,
                          stdout=subprocess.PIPE).stdout


def check_files(path: str, ctx: SrtContext, quilt: bool) -> Check:
    """The patch and the tarball of srt create match the tags."""
    new = str(ctx.new_tag)
    patch, tar = release_files(path, new)
    if not (os.path.isfile(patch) and os.path.isfile(tar)):
        return Check('files', SKIP, 'srt create has not run yet')
    errors = []
    diff = subprocess.run(['git', '-C', path, 'diff', ctx.new_tag.base, new],
                          check=True, stdout=subprocess.PIPE).stdout
    if _xz(patch) != diff:
        errors.append(f'{os.path.basename(patch)} is not git diff '
                      f'{ctx.new_tag.base} {new}')
    if quilt:
        listed = subprocess.run(['tar', '-tJf', tar], check=True,
                                stdout=subprocess.PIPE, encoding='utf-8')
        names = sorted(n for n in listed.stdout.splitlines()
                       if not n.endswith('/'))
        queue = sorted(_git(path, 'ls-tree', '-r', '--name-only',
                            f'{new}-patches', 'patches').splitlines())
        if names != queue:
            errors.append(f'{os.path.basename(tar)} is not the queue of '
                          f'{new}-patches')
    if errors:
        return Check('files', FAIL, 'srt create made other files than the '
                     'tags: rerun srt create', errors)
    return Check('files', OK, f'the patch and the tarball match {new}')


def check_signatures(path: str, ctx: SrtContext, config: Config) -> Check:
    new = str(ctx.new_tag)
    files = release_files(path, new)
    sigs = [os.path.splitext(f)[0] + '.sign' for f in files]
    if not all(os.path.isfile(s) for s in sigs):
        return Check('signatures', SKIP, 'srt sign has not run yet')
    env = dict(os.environ, GNUPGHOME=get_gnupghome(config))
    bad = []
    for f, sig in zip(files, sigs, strict=True):
        xz = subprocess.run(['xz', '-dc', f], check=True,
                            stdout=subprocess.PIPE)
        p = subprocess.run(['gpg', '--batch', '--verify', sig, '-'],
                           input=xz.stdout, env=env,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        if p.returncode:
            bad.append(os.path.basename(sig))
    if bad:
        return Check('signatures', FAIL, 'bad signature, rerun srt sign',
                     bad)
    return Check('signatures', OK, 'the signatures are good')


def run_checks(state_path: str | None = None) -> list[Check]:
    state = read_srt_state(state_path)
    if not state or not state.get('new_tag'):
        sys.exit('No release prepared: run "srt prep" in the worktree of '
                 'the series first')
    if state.get('quilt_workflow'):
        rel = srt_quilt.Release(state)
        path = rel.rt_dir
        config = rel.config
        checks: list[Callable[[], Check]] = [
            lambda: check_upstream(rel), lambda: check_queue(rel),
            lambda: check_rebase(rel), lambda: check_merge(rel),
            lambda: check_release(rel)]
    else:
        path = os.getcwd()
        config = get_config()
        new = state['new_tag']
        checks = [lambda: check_trees(path, new, new + '-rebase')]
    with _cwd(path):
        ctx = SrtContext(None, path=path)
    quilt = is_quilt_workflow(config)
    checks += [lambda: check_delta(path, ctx),
               lambda: check_files(path, ctx, quilt),
               lambda: check_signatures(path, ctx, config)]
    return [c() for c in checks]


def print_checks(checks: list[Check]) -> None:
    for c in checks:
        print(f'{c.result:5} {c.name}: {c.text}')
        for d in c.details:
            print(f'        {d}')


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('check',
                            help='sanity checks between the trees of the '
                            'prepared release')
    prs.add_argument('--json', action='store_true',
                     help='print the checks as JSON, for scripts')
    return prs


def execute(args: argparse.Namespace) -> None:
    checks = run_checks()
    if args.json:
        print(json.dumps([asdict(c) for c in checks], indent=2))
    else:
        print_checks(checks)
    if any(c.result == FAIL for c in checks):
        sys.exit(1)
