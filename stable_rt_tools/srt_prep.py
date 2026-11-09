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
import os
import re
import sys
from subprocess import CalledProcessError

from stable_rt_tools.srt_util import (
    Config,
    SrtState,
    SubParsers,
    Worktrees,
    clear_srt_state,
    cmd,
    get_config,
    get_last_release_number,
    get_old_tag,
    get_remote_branch_name,
    get_suffix,
    get_workflow_branch,
    is_quilt_workflow,
    write_srt_state,
)


def get_next_stable_version(branch_name: str, tree_dir: str) -> str | None:
    branch = cmd([
        'git', '-C', tree_dir, 'rev-parse', '--abbrev-ref', 'HEAD']
    ).strip()
    tags = cmd([
        'git', '-C', tree_dir, 'tag', '--merged', branch, '--sort=-v:refname'
    ]).splitlines()
    for tag in tags:
        # a stable release, not a -rc, -rt or other suffixed tag
        if re.fullmatch(r'v\d+\.\d+\.\d+', tag):
            return tag
    return None


def worktree_dirs(rt_dir: str, suffix: str = 'rt') -> Worktrees:
    """The quilt workflow worktrees, which are siblings of the -rt one.

    For rt_dir .../v6.12-rt: .../v6.12, .../v6.12-rt-patches and
    .../v6.12-rt-rebase.
    """
    rt_dir = os.path.abspath(rt_dir)
    parent, name = os.path.split(rt_dir)
    return Worktrees(
        rt_dir=rt_dir,
        stable_dir=os.path.join(parent, name.split(f'-{suffix}')[0]),
        patches_dir=os.path.join(parent, name + '-patches'),
        rebase_dir=os.path.join(parent, name + '-rebase'),
    )


def pull_stable(stable_dir: str) -> None:
    print(f'Updating {stable_dir} (git pull --ff-only)')
    try:
        cmd(['git', '-C', stable_dir, 'pull', '--ff-only'], verbose=True)
    except CalledProcessError:
        sys.exit(f'git pull in {stable_dir} failed, fix it or use '
                 '"srt prep --no-pull"')


def prep(config: Config, pull: bool = True) -> None:
    quilt_workflow = is_quilt_workflow(config)
    suffix = get_suffix(config)
    dirs = worktree_dirs(os.getcwd(), suffix)

    # quilt patches
    quilt_patches = os.path.join(dirs['patches_dir'], 'patches')

    if quilt_workflow:
        paths = (dirs['rt_dir'], dirs['stable_dir'], dirs['patches_dir'],
                 dirs['rebase_dir'])
        missing = [d for d in paths if not os.path.isdir(d)]
        if missing:
            sys.exit('quilt workflow worktree(s) missing: {}'.format(
                ', '.join(missing)))
        if pull:
            pull_stable(dirs['stable_dir'])

    # old tag
    old_tag = get_old_tag()

    # new tag
    branch_name = get_remote_branch_name()
    number = get_last_release_number(branch_name, suffix) + 1
    next_stable = get_next_stable_version(branch_name, dirs['stable_dir'])
    if next_stable is None:
        sys.exit(f'no stable release tag found in {dirs["stable_dir"]}')
    new_tag = f'{next_stable}-{suffix}{number}'

    state = SrtState(
        old_tag=old_tag,
        new_tag=new_tag,
        quilt_patches=quilt_patches,
        branch=branch_name,
        workflow_branch=get_workflow_branch(branch_name),
        suffix=suffix,
        quilt_workflow=quilt_workflow,
    )
    if quilt_workflow:
        state['rt_dir'] = dirs['rt_dir']
        state['stable_dir'] = dirs['stable_dir']
        state['patches_dir'] = dirs['patches_dir']
        state['rebase_dir'] = dirs['rebase_dir']
    write_srt_state(state)

    print(f"OLD_TAG={old_tag}")
    print(f"NEW_TAG={new_tag}")
    if quilt_workflow:
        print('next: srt quilt refresh')


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('prep')
    prs.add_argument('--clear', action='store_true',
                     help='Clear saved srt prep state')
    prs.add_argument('--no-pull', action='store_true',
                     help='Do not update the stable worktree (quilt '
                     'workflow)')
    return prs


def execute(args: argparse.Namespace) -> None:
    if getattr(args, 'clear', False):
        clear_srt_state()
        return
    prep(get_config(), pull=not getattr(args, 'no_pull', False))
