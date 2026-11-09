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


import os
import sys
from subprocess import CalledProcessError
from stable_rt_tools.srt_util import (
    get_remote_branch_name, get_old_tag, get_config, get_last_rt_tag, cmd,
    write_srt_state, clear_srt_state, get_workflow_branch, is_quilt_workflow
)


def get_next_stable_version(branch_name, tree_dir):
    branch = cmd([
        'git', '-C', tree_dir, 'rev-parse', '--abbrev-ref', 'HEAD']
    ).strip()
    tags = cmd([
        'git', '-C', tree_dir, 'tag', '--merged', branch, '--sort=-v:refname'
    ]).splitlines()
    for tag in tags:
        if tag.startswith('v') and '-rt' not in tag:
            return tag
    return None


def worktree_dirs(rt_dir):
    """The quilt workflow worktrees, which are siblings of the -rt one.

    For rt_dir .../v6.12-rt: .../v6.12, .../v6.12-rt-patches and
    .../v6.12-rt-rebase.
    """
    rt_dir = os.path.abspath(rt_dir)
    parent, name = os.path.split(rt_dir)
    return {
        'rt_dir': rt_dir,
        'stable_dir': os.path.join(parent, name.split('-rt')[0]),
        'patches_dir': os.path.join(parent, name + '-patches'),
        'rebase_dir': os.path.join(parent, name + '-rebase'),
    }


def pull_stable(stable_dir):
    print('Updating {0} (git pull --ff-only)'.format(stable_dir))
    try:
        cmd(['git', '-C', stable_dir, 'pull', '--ff-only'], verbose=True)
    except CalledProcessError:
        sys.exit('git pull in {0} failed, fix it or use '
                 '"srt prep --no-pull"'.format(stable_dir))


def prep(config, pull=True):
    quilt_workflow = is_quilt_workflow(config)
    dirs = worktree_dirs(os.getcwd())

    # quilt patches
    quilt_patches = os.path.join(dirs['patches_dir'], 'patches')

    if quilt_workflow:
        missing = [d for d in dirs.values() if not os.path.isdir(d)]
        if missing:
            sys.exit('quilt workflow worktree(s) missing: {0}'.format(
                ', '.join(missing)))
        if pull:
            pull_stable(dirs['stable_dir'])

    # old tag
    old_tag = get_old_tag()

    # new tag
    branch_name = get_remote_branch_name()
    rt = get_last_rt_tag(branch_name, '')
    rt_ver = rt[3:]
    rt_ver = int(rt_ver) + 1
    next_stable = get_next_stable_version(branch_name, dirs['stable_dir'])
    new_tag = f"{next_stable}-rt{rt_ver}"

    state = {
        'old_tag': old_tag,
        'new_tag': new_tag,
        'quilt_patches': quilt_patches,
        'branch': branch_name,
        'workflow_branch': get_workflow_branch(branch_name),
        'quilt_workflow': quilt_workflow,
    }
    if quilt_workflow:
        state.update(dirs)
    write_srt_state(state)

    print(f"OLD_TAG={old_tag}")
    print(f"NEW_TAG={new_tag}")
    if quilt_workflow:
        print('next: srt quilt refresh')


def add_argparser(parser):
    prs = parser.add_parser('prep')
    prs.add_argument('--clear', action='store_true',
                     help='Clear saved srt prep state')
    prs.add_argument('--no-pull', action='store_true',
                     help='Do not update the stable worktree (quilt '
                     'workflow)')
    return prs


def execute(args):
    if getattr(args, 'clear', False):
        clear_srt_state()
        return
    prep(get_config(), pull=not getattr(args, 'no_pull', False))
