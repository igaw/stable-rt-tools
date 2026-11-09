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


"""Quilt workflow release steps.

All steps read the release prepared by 'srt prep' (OLD_TAG, NEW_TAG and
the worktree paths) and work on the sibling worktrees, so they can be
run from any of them:

  refresh  refresh the RT series on top of the new stable release
  queue    commit and tag the patch queue with the announcement (-patches)
  rebase   import the queue on top of the stable release (-rebase)
  merge    merge the stable release and apply added patches (-rt)
  release  commit and tag the release on -rt, its tree must match -rebase
  undo     undo the steps above as long as nothing is pushed

This follows the linux-6.18.y-rt releases: the tags are created in the
order -patches, -rebase, release, and the -rt tree is identical to the
-rebase tree.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from subprocess import CalledProcessError
from time import gmtime, strftime

from stable_rt_tools.srt_announce import cover_letter_replacements
from stable_rt_tools.srt_commit import localversion_set
from stable_rt_tools.srt_prep import worktree_dirs
from stable_rt_tools.srt_util import (
    Config,
    SrtState,
    SubParsers,
    Worktrees,
    cmd,
    confirm,
    get_config,
    get_gpg_env,
    get_template_path,
    read_srt_state,
    update_srt_state,
)
from stable_rt_tools.srt_util_context import SrtContext
from stable_rt_tools.srt_util_tag import Tag

# The RT patch queue format. quilt must not pick it up from the user's
# quiltrc, otherwise a refresh rewrites every patch header (Index: lines,
# v6.12.orig/ prefixes, different function context).
QUILT_REFRESH_ARGS = ['-p', 'ab', '--no-index', '--no-timestamps']
QUILT_DIFF_OPTS = '-F ^[[:alpha:]$_].*[^:]$'

STEPS = ['refresh', 'queue', 'rebase', 'merge', 'release']


#
# helpers without git/quilt access
#

def parse_series(text: str) -> list[str]:
    """Return the patch names of a quilt series file."""
    patches = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        patches.append(line.split()[0])
    return patches


def series_changes(old: list[str],
                   new: list[str]) -> tuple[list[str], list[str]]:
    """Return (dropped, added) patch names between two series."""
    dropped = [p for p in old if p not in new]
    added = [p for p in new if p not in old]
    return dropped, added


def patch_subject(text: str) -> str | None:
    """Return the commit subject of a patch, as git am would."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('---') or line.startswith('diff '):
            break
        if line.lower().startswith('subject:'):
            subject = line[len('subject:'):].strip()
            for cont in lines[i + 1:]:
                if cont[:1] not in (' ', '\t'):
                    break
                subject += ' ' + cont.strip()
            return re.sub(r'^(\[[^\]]*\]\s*)+', '', subject).strip()
    return None


def rt_localversion(tag: object) -> str:
    """'v6.12.116-rt22' -> '-rt22'"""
    return '-' + str(tag).split('-', 1)[1]


def drop_from_series(patches_dir: str, name: str) -> None:
    series = os.path.join(patches_dir, 'series')
    with open(series) as f:
        lines = f.readlines()
    with open(series, 'w') as f:
        for line in lines:
            if line.split() and line.split()[0] == name:
                continue
            f.write(line)
    path = os.path.join(patches_dir, name)
    if os.path.exists(path):
        os.remove(path)


#
# git helpers
#

def git(path: str, *args: str, env: Mapping[str, str] | None = None,
        cwd: str | None = None) -> str:
    return cmd(['git', '-C', path, *args], env=env, cwd=cwd)


def rev(path: str, ref: str) -> str | None:
    try:
        return git(path, 'rev-parse', '--verify', '--quiet',
                   ref + '^{commit}')
    except CalledProcessError:
        return None


def is_ancestor(path: str, ancestor: str, ref: str = 'HEAD') -> bool:
    try:
        git(path, 'merge-base', '--is-ancestor', ancestor, ref)
        return True
    except CalledProcessError:
        return False


def dirty_files(path: str, ignore: Sequence[str] = ()) -> list[str]:
    out = git(path, 'status', '--porcelain', '--untracked-files=no')
    files = [line[3:] for line in out.splitlines() if line]
    return [f for f in files if f not in ignore]


def require_clean(path: str, ignore: Sequence[str] = ()) -> None:
    files = dirty_files(path, ignore)
    if files:
        sys.exit('{} has uncommitted changes: {}'.format(
            path, ', '.join(files)))


def in_progress(path: str) -> str | None:
    """Return the name of a git operation in progress, if any."""
    if rev(path, 'MERGE_HEAD'):
        return 'merge'
    p = git(path, 'rev-parse', '--git-path', 'rebase-apply')
    if not os.path.isabs(p):
        p = os.path.join(path, p)
    if os.path.exists(p):
        return 'am'
    return None


#
# release state
#

class Release:
    def __init__(self, state: SrtState | None = None) -> None:
        state = state if state is not None else read_srt_state()
        if not state or not state.get('new_tag'):
            sys.exit('No release prepared: run "srt prep" in the -rt '
                     'worktree first')
        if not state.get('quilt_workflow'):
            sys.exit('srt quilt: quilt_workflow is not enabled for {}'
                     .format(state.get('workflow_branch')))
        self.state = state
        if 'rt_dir' in state:
            dirs = Worktrees(rt_dir=state['rt_dir'],
                             stable_dir=state['stable_dir'],
                             patches_dir=state['patches_dir'],
                             rebase_dir=state['rebase_dir'])
        else:
            # state written by an older srt prep
            patches_dir = os.path.dirname(state['quilt_patches'])
            dirs = worktree_dirs(patches_dir[:-len('-patches')],
                                 state.get('suffix', 'rt'))
        self.rt_dir = dirs['rt_dir']
        self.stable_dir = dirs['stable_dir']
        self.patches_dir = dirs['patches_dir']
        self.rebase_dir = dirs['rebase_dir']
        self.quilt_patches = state['quilt_patches']
        self.workflow_branch = state['workflow_branch']

        self.old = Tag(state['old_tag'])
        self.new = Tag(state['new_tag'])
        if self.new.is_rc:
            sys.exit('release candidates are not supported by the quilt '
                     'workflow')
        self.base = self.new.base
        self.release_tag = str(self.new)
        self.rebase_tag = self.new.rebase
        self.queue_tag = str(self.new) + '-patches'
        self.old_queue_tag = str(self.old) + '-patches'
        self._config: Config | None = None

    @property
    def config(self) -> Config:
        # the configuration group of the -rt branch
        if self._config is None:
            cwd = os.getcwd()
            os.chdir(self.rt_dir)
            try:
                self._config = get_config()
            finally:
                os.chdir(cwd)
        return self._config

    @property
    def localversion(self) -> str:
        return self.config.get('LOCALVERSION', 'localversion-rt')

    def old_series(self) -> list[str]:
        return parse_series(git(self.rt_dir, 'show',
                                self.old_queue_tag + ':patches/series'))

    def new_series(self) -> list[str]:
        with open(os.path.join(self.quilt_patches, 'series')) as f:
            return parse_series(f.read())

    def series_changes(self) -> tuple[list[str], list[str]]:
        return series_changes(self.old_series(), self.new_series())

    def has_tag(self, path: str, tag: str) -> bool:
        return rev(path, 'refs/tags/' + tag) is not None

    def tag(self, path: str, tag: str, msg: str) -> None:
        existing = rev(path, 'refs/tags/' + tag)
        if existing:
            if existing == rev(path, 'HEAD'):
                print(f'{tag} already tagged')
                return
            sys.exit(f'tag {tag} exists but is not HEAD of {path}; delete it '
                     f'with "git tag -d {tag}" and rerun')
        print(f'tagging HEAD of {path} as {tag}')
        if not confirm('OK to tag?'):
            sys.exit('not tagged, rerun to tag')
        git(path, 'tag', '-s', '-u', self.config['GPG_KEY_ID'],
            '-m', msg, tag, env=get_gpg_env(self.config))

    def done(self, step: str) -> bool:
        if step == 'refresh':
            return self.state.get('refreshed') == self.release_tag
        if step == 'queue':
            return self.has_tag(self.patches_dir, self.queue_tag)
        if step == 'rebase':
            return self.has_tag(self.rebase_dir, self.rebase_tag)
        if step == 'merge':
            return is_ancestor(self.rt_dir, self.base) and \
                not self.missing_patches()
        if step == 'release':
            return self.has_tag(self.rt_dir, self.release_tag)
        raise ValueError(step)

    def subjects(self) -> list[str]:
        out = git(self.rt_dir, 'log', '--format=%s',
                  f'{self.old}..HEAD')
        return out.splitlines()

    def missing_patches(self) -> list[str]:
        """Added patches which are not applied on -rt yet."""
        subjects = self.subjects()
        missing = []
        for name in self.series_changes()[1]:
            with open(os.path.join(self.quilt_patches, name)) as f:
                if patch_subject(f.read()) not in subjects:
                    missing.append(name)
        return missing


#
# refresh
#

def _quilt_env(rel: Release) -> dict[str, str]:
    env = os.environ.copy()
    env['QUILT_DIFF_OPTS'] = QUILT_DIFF_OPTS
    env['QUILT_PATCHES'] = rel.quilt_patches
    return env


def _quilt(rel: Release, args: list[str], env: Mapping[str, str]) -> str:
    # '--quiltrc -' makes quilt ignore ~/.quiltrc and /etc/quilt.quiltrc
    return cmd(['quilt', '--quiltrc', '-'] + args, env=env,
               cwd=rel.stable_dir)


def _refresh(rel: Release, env: Mapping[str, str]) -> None:
    _quilt(rel, ['refresh'] + QUILT_REFRESH_ARGS, env)


def _already_applied(rel: Release, name: str) -> bool:
    """True if the patch reverse-applies, i.e. stable already has it."""
    try:
        cmd(['patch', '-p1', '-R', '--dry-run', '-s', '-f', '-i',
             os.path.join(rel.quilt_patches, name)], cwd=rel.stable_dir)
        return True
    except CalledProcessError:
        return False


def refresh(rel: Release) -> None:
    if rev(rel.stable_dir, 'HEAD') != rev(rel.stable_dir, rel.base):
        sys.exit(f'{rel.stable_dir} is not at {rel.base}; run "srt prep" '
                 'to update it')
    if rel.has_tag(rel.patches_dir, rel.queue_tag):
        sys.exit(f'{rel.queue_tag} is already tagged')
    env = _quilt_env(rel)
    while True:
        try:
            name = _quilt(rel, ['next'], env)
        except CalledProcessError:
            break
        try:
            _quilt(rel, ['push'], env)
        except CalledProcessError as e:
            if _already_applied(rel, name):
                print(f'{name} is already in {rel.base}')
                if confirm('Drop it from the series?'):
                    drop_from_series(rel.quilt_patches, name)
                    continue
            elif e.stdout:
                print(e.stdout.decode('utf-8'))
            sys.exit(f'quilt push of {name} failed. Fix it in '
                     f'{rel.stable_dir} (quilt push -f, edit, quilt refresh) '
                     'and rerun '
                     '"srt quilt refresh"')
        _refresh(rel, env)

    localversion_set(os.path.join(rel.stable_dir, rel.localversion),
                     rt_localversion(rel.new))
    _refresh(rel, env)
    _quilt(rel, ['pop', '-a'], env)
    update_srt_state({'refreshed': rel.release_tag})

    dropped, added = rel.series_changes()
    for p in dropped:
        print(f'dropped: {p}')
    for p in added:
        print(f'added:   {p}')
    print(f'review: git -C {rel.patches_dir} diff')
    print('next: srt quilt queue')


#
# queue
#

def queue(rel: Release) -> None:
    if rel.done('queue'):
        print(f'{rel.queue_tag} already tagged')
        return
    if not rel.done('refresh'):
        sys.exit('run "srt quilt refresh" first')

    git(rel.patches_dir, 'add', '-A', '--', 'patches')
    subject = git(rel.patches_dir, 'log', '-1', '--format=%s')
    committed = subject.endswith(str(rel.new)[1:])
    if committed and git(rel.patches_dir, 'diff', '--cached', '--name-only'):
        # tagging HEAD would leave the staged changes out of the release
        sys.exit(f'{rel.patches_dir}: the queue commit for {rel.new} exists '
                 'and patches/ changed since. Undo the release with "srt '
                 'quilt undo" (or the commit with "git reset --soft '
                 'HEAD~1") and rerun from "srt quilt refresh"')
    if not committed:
        cwd = os.getcwd()
        os.chdir(rel.rt_dir)
        try:
            ctx = SrtContext(None, path=rel.rt_dir)
        finally:
            os.chdir(cwd)
        r = cover_letter_replacements(rel.config, ctx)
        r['date'] = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())
        r['branch_name'] = rel.workflow_branch
        r['release_tag'] = rel.release_tag
        dropped, added = rel.series_changes()
        r['series_changes'] = ''.join(
            [f'  - dropped {p}\n' for p in dropped] +
            [f'  - added {p}\n' for p in added]) or '  - none\n'
        with open(get_template_path(rel.config, 'COMMIT_TMPL',
                                    'commit-tmpl.txt')) as f:
            text = f.read().format(**r)
        with tempfile.NamedTemporaryFile('w', delete=False) as msg:
            msg.write(text)
        try:
            p = subprocess.run(['git', 'commit', '-s', '--edit', '-F',
                                msg.name], cwd=rel.patches_dir)
        finally:
            os.remove(msg.name)
        if p.returncode:
            sys.exit('git commit failed')

    rel.tag(rel.patches_dir, rel.queue_tag,
            'Patch queue for ' + str(rel.new))
    print('next: srt quilt rebase')


#
# rebase
#

def rebase(rel: Release) -> None:
    if rel.done('rebase'):
        print(f'{rel.rebase_tag} already tagged')
        return
    queue_head = rev(rel.patches_dir, 'refs/tags/' + rel.queue_tag)
    if not queue_head:
        sys.exit('run "srt quilt queue" first')
    if rev(rel.patches_dir, 'HEAD') != queue_head or \
            dirty_files(rel.patches_dir):
        sys.exit(f'{rel.patches_dir} is not at {rel.queue_tag}')
    require_clean(rel.rebase_dir)
    print(f'reset {rel.rebase_dir} to {rel.base} and import the '
          f'{len(rel.new_series())} patches of {rel.queue_tag}')
    if not confirm('OK to reset?'):
        sys.exit('aborted')
    git(rel.rebase_dir, 'reset', '--hard', rel.base)
    git(rel.rebase_dir, 'quiltimport', '--patches', rel.quilt_patches)
    rel.tag(rel.rebase_dir, rel.rebase_tag, rel.rebase_tag)
    print('next: srt quilt merge')


#
# merge
#

def merge(rel: Release) -> None:
    if not rel.done('rebase'):
        sys.exit('run "srt quilt rebase" first')
    op = in_progress(rel.rt_dir)
    if op:
        sys.exit(f'{rel.rt_dir}: {op} in progress, finish it first')
    require_clean(rel.rt_dir)

    if not is_ancestor(rel.rt_dir, rel.base):
        print(f'merge {rel.base}')
        try:
            git(rel.rt_dir, 'merge', '--no-edit', rel.base,
                env=get_gpg_env(rel.config))
        except CalledProcessError:
            sys.exit('merge conflict: resolve it (the result has to match '
                     f'{rel.rebase_tag}), "git commit" and rerun '
                     '"srt quilt merge"')
    for name in rel.missing_patches():
        print(f'apply {name}')
        try:
            git(rel.rt_dir, 'am', '-3', '-s',
                os.path.join(rel.quilt_patches, name),
                env=get_gpg_env(rel.config))
        except CalledProcessError:
            sys.exit(f'git am {name} failed: resolve it, "git am --continue" '
                     'and rerun "srt quilt merge"')
    print('next: srt quilt release')


#
# release
#

def release(rel: Release) -> None:
    if rel.done('release'):
        print(f'{rel.release_tag} already tagged')
        return
    if not rel.done('merge'):
        sys.exit('run "srt quilt merge" first')

    head_subject = git(rel.rt_dir, 'log', '-1', '--format=%s')
    if head_subject != rel.release_tag:
        require_clean(rel.rt_dir, ignore=(rel.localversion,))
        localversion_set(os.path.join(rel.rt_dir, rel.localversion),
                         rt_localversion(rel.new))
        git(rel.rt_dir, 'add', rel.localversion)

    tree = git(rel.rt_dir, 'write-tree')
    if tree != git(rel.rt_dir, 'rev-parse', rel.rebase_tag + '^{tree}'):
        print(git(rel.rt_dir, 'diff', '--cached', '--stat', rel.rebase_tag))
        if head_subject != rel.release_tag:
            # don't let the fixup commit pick up the localversion bump
            git(rel.rt_dir, 'reset', '-q', 'HEAD', '--', rel.localversion)
            git(rel.rt_dir, 'checkout', '-q', '--', rel.localversion)
        sys.exit(f'{rel.rt_dir} differs from {rel.rebase_tag}: commit a '
                 f'fixup (see "git diff --cached {rel.rebase_tag}") and '
                 'rerun "srt quilt release"')

    if head_subject != rel.release_tag:
        git(rel.rt_dir, 'commit', '-s', '-m', rel.release_tag,
            env=get_gpg_env(rel.config))
    rel.tag(rel.rt_dir, rel.release_tag, rel.release_tag)
    print('next: srt create')


#
# undo
#

def _upstream(path: str) -> str | None:
    try:
        return git(path, 'rev-parse', '--abbrev-ref', '--symbolic-full-name',
                   '@{u}')
    except CalledProcessError:
        return None


def _pushed(path: str, ref: str) -> bool:
    upstream = _upstream(path)
    return upstream is not None and is_ancestor(path, ref, upstream)


def undo(rel: Release) -> None:
    """Undo srt quilt queue..release, keep the refreshed patches."""
    tags = [(rel.rt_dir, rel.release_tag), (rel.rebase_dir, rel.rebase_tag),
            (rel.patches_dir, rel.queue_tag)]
    for path, tag in tags:
        ref = rev(path, 'refs/tags/' + tag)
        if ref and _pushed(path, ref):
            sys.exit(f'{tag} is pushed already, it cannot be undone')
    op = in_progress(rel.rt_dir)
    if op:
        sys.exit(f'{rel.rt_dir}: {op} in progress, abort it first')
    require_clean(rel.rt_dir)

    rt_upstream = _upstream(rel.rt_dir)
    if not rt_upstream:
        sys.exit(f'{rel.rt_dir} has no upstream branch')
    dropped = git(rel.rt_dir, 'log', '--oneline', '--first-parent',
                  f'{rt_upstream}..HEAD')
    queue_commit = git(rel.patches_dir, 'log', '-1', '--format=%s') \
        .endswith(str(rel.new)[1:])
    if queue_commit and _pushed(rel.patches_dir, 'HEAD'):
        sys.exit(f'the queue commit of {rel.new} is pushed already')
    existing = [tag for path, tag in tags
                if rev(path, 'refs/tags/' + tag)]

    if not existing and not dropped and not queue_commit:
        print('nothing to undo')
        return
    print(f'undo the {rel.new} release:')
    for tag in existing:
        print(f'  delete tag {tag}')
    if dropped:
        print(f'  reset {rel.rt_dir} to {rt_upstream}, dropping:')
        for line in dropped.splitlines():
            print(f'    {line}')
    if queue_commit:
        print(f'  undo the queue commit in {rel.patches_dir}, '
              'keeping the patches')
    if not confirm('OK to undo?'):
        sys.exit('aborted')

    for tag in existing:
        git(rel.rt_dir, 'tag', '-d', tag)
    if dropped:
        git(rel.rt_dir, 'reset', '-q', '--hard', rt_upstream)
    if queue_commit:
        git(rel.patches_dir, 'reset', '-q', '--soft', 'HEAD~1')
    update_srt_state({'refreshed': None})
    print('next: fix the patch queue, then srt quilt refresh')


#
# status
#

def status(rel: Release) -> None:
    print(f'{rel.old} -> {rel.new}')
    dropped, added = rel.series_changes()
    for p in dropped:
        print(f'  dropped: {p}')
    for p in added:
        print(f'  added:   {p}')
    nxt = None
    for step in STEPS:
        done = rel.done(step)
        if not done and nxt is None:
            nxt = step
        print('  [{}] srt quilt {}'.format('x' if done else ' ', step))
    if nxt:
        print(f'next: srt quilt {nxt}')
    else:
        print('next: srt create, srt sign, srt upload, srt push, '
              'srt announce')


COMMANDS = {
    'refresh': refresh,
    'queue': queue,
    'rebase': rebase,
    'merge': merge,
    'release': release,
    'undo': undo,
}


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('quilt', help='quilt workflow release steps')
    sub = prs.add_subparsers(dest='quilt_cmd', metavar='STEP')
    sub.add_parser('refresh',
                   help='refresh the RT series on the new stable release '
                   '(default)')
    sub.add_parser('queue',
                   help='commit and tag the patch queue with the '
                   'announcement')
    sub.add_parser('rebase',
                   help='import the queue on top of stable in -rebase')
    sub.add_parser('merge',
                   help='merge stable and apply added patches in -rt')
    sub.add_parser('release', help='commit and tag the release in -rt')
    sub.add_parser('undo',
                   help='undo queue..release as long as nothing is pushed, '
                   'keep the refreshed patches')
    return prs


def execute(args: argparse.Namespace) -> None:
    step = getattr(args, 'quilt_cmd', None) or 'refresh'
    COMMANDS[step](Release())
