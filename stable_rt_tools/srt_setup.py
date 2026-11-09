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


"""srt setup: create or check the work area of a patch series.

The srt.conf group [<repo>/<remote>/<series>] describes it:

  PRJ_GIT_URL       the tree of the series, fetched as <remote>
  PRJ_GIT_TREE      where the series is pushed to (optional)
  UPSTREAM_GIT_URL  the tree the series is based on, e.g. stable
  UPSTREAM_BRANCH   its branch, e.g. linux-6.12.y
  UPSTREAM_REMOTE   the name of its remote (default: upstream)
  ORIGIN_GIT_URL    what <repo> is cloned from (default: UPSTREAM_GIT_URL)

The repository <repo> and the worktrees are created next to each other
in the setup directory; existing ones are checked.
"""

import argparse
import os
import sys
from collections.abc import Mapping
from subprocess import CalledProcessError

from stable_rt_tools.srt_prep import worktree_dirs
from stable_rt_tools.srt_util import (
    SubParsers,
    cmd,
    get_suffix,
    is_quilt_workflow,
    read_config,
)


class SetupError(Exception):
    pass


def _git(path: str, *args: str) -> str:
    return cmd(['git', '-C', path, *args], verbose=True)


def _query(path: str, *args: str) -> str | None:
    """Run a git query, None if it fails."""
    try:
        return cmd(['git', '-C', path, *args])
    except CalledProcessError:
        return None


def _repo_name(url: str) -> str:
    name = url.rstrip('/').rsplit('/', 1)[-1]
    return name.removesuffix('.git')


def _require(config: Mapping[str, str], key: str) -> str:
    value = config.get(key)
    if not value:
        raise SetupError(f'{key} is not set')
    return value


def setup_repo(path: str, origin_url: str) -> None:
    if not os.path.isdir(path):
        print(f'clone {origin_url} into {path}')
        cmd(['git', 'clone', origin_url, path], verbose=True)
        return
    url = _query(path, 'config', '--get', 'remote.origin.url')
    if url is None:
        raise SetupError(f'{path} is no git repository with an origin')
    print(f'ok    {path} (origin {url})')


def setup_remote(path: str, name: str, url: str,
                 push_url: str | None = None) -> None:
    current = _query(path, 'config', '--get', f'remote.{name}.url')
    if current is None:
        print(f'add   remote {name} {url}')
        _git(path, 'remote', 'add', name, url)
    elif current != url:
        raise SetupError(f'remote {name} is {current}, not {url}; fix it '
                         f'with "git remote set-url {name} {url}"')
    else:
        print(f'ok    remote {name} {url}')
    if push_url:
        current_push = _query(path, 'config', '--get',
                              f'remote.{name}.pushurl')
        if current_push != push_url:
            print(f'set   remote {name} push URL {push_url}')
            _git(path, 'remote', 'set-url', '--push', name, push_url)


def _checked_out(repo: str, branch: str) -> str | None:
    """The worktree which has branch checked out, if any."""
    path = None
    for line in cmd(['git', '-C', repo, 'worktree', 'list',
                     '--porcelain']).splitlines():
        if line.startswith('worktree '):
            path = line[len('worktree '):]
        elif line == f'branch refs/heads/{branch}':
            return path
    return None


def setup_worktree(repo: str, path: str, branch: str, upstream: str) -> None:
    """A worktree at path with branch tracking upstream."""
    if os.path.isdir(path):
        head = _query(path, 'rev-parse', '--abbrev-ref', 'HEAD')
        tracking = _query(path, 'rev-parse', '--abbrev-ref',
                          '--symbolic-full-name', '@{u}')
        if head != branch or tracking != upstream:
            raise SetupError(f'{path} is on {head} tracking {tracking}, '
                             f'expected {branch} tracking {upstream}')
        print(f'ok    {path} ({branch} tracking {upstream})')
        return
    holder = _checked_out(repo, branch)
    if holder is not None:
        if os.path.realpath(holder) != os.path.realpath(repo):
            raise SetupError(f'{branch} is checked out in {holder}')
        # the clone itself checked it out, it isn't used for work
        print(f'detach HEAD of {repo}, {branch} goes to {path}')
        _git(repo, 'checkout', '-q', '--detach')
    if _query(repo, 'rev-parse', '--verify', '--quiet',
              f'refs/heads/{branch}') is not None:
        print(f'add   worktree {path} for the existing branch {branch}')
        _git(repo, 'worktree', 'add', path, branch)
        _git(path, 'branch', '--set-upstream-to', upstream)
    else:
        print(f'add   worktree {path} ({branch} tracking {upstream})')
        _git(repo, 'worktree', 'add', '--track', '-b', branch, path,
             upstream)


def setup(group: str, config: Mapping[str, str], parent: str) -> None:
    try:
        repo_name, remote, series = group.split('/', 2)
    except ValueError:
        raise SetupError(f'{group} is not <repo>/<remote>/<series>') \
            from None
    upstream_url = _require(config, 'UPSTREAM_GIT_URL')
    upstream_branch = _require(config, 'UPSTREAM_BRANCH')
    upstream_remote = config.get('UPSTREAM_REMOTE', 'upstream')
    origin_url = config.get('ORIGIN_GIT_URL', upstream_url)
    if _repo_name(origin_url) != repo_name:
        # srt finds the configuration group by the name of origin
        raise SetupError(f'origin {origin_url} does not match the '
                         f'repository name {repo_name} of [{group}]')

    parent = os.path.abspath(parent)
    repo = os.path.join(parent, repo_name)
    setup_repo(repo, origin_url)
    if upstream_remote != 'origin':
        setup_remote(repo, upstream_remote, upstream_url)
    setup_remote(repo, remote, _require(config, 'PRJ_GIT_URL'),
                 config.get('PRJ_GIT_TREE'))
    print('fetch')
    for name in dict.fromkeys(('origin', upstream_remote, remote)):
        _git(repo, 'fetch', '--tags', name)

    if is_quilt_workflow(config):
        dirs = worktree_dirs(os.path.join(parent, series),
                             get_suffix(config))
        setup_worktree(repo, dirs['stable_dir'], upstream_branch,
                       f'{upstream_remote}/{upstream_branch}')
        branches = [series, series + '-patches', series + '-rebase']
    else:
        # the git workflow: the series and its -rebase and -next
        # branches, as far as they exist
        branches = [b for b in (series, series + '-rebase', series + '-next')
                    if b == series or _query(
                        repo, 'rev-parse', '--verify', '--quiet',
                        f'refs/remotes/{remote}/{b}') is not None]
    for branch in branches:
        setup_worktree(repo, os.path.join(parent, branch), branch,
                       f'{remote}/{branch}')
    print(f'next: cd {os.path.join(parent, series)} && srt prep')


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser(
        'setup', help='create or check the work area of a patch series')
    prs.add_argument('group',
                     help='srt.conf group <repo>/<remote>/<series>, e.g. '
                     'linux/stable-rt/v6.12-rt')
    prs.add_argument('--dir', default='.',
                     help='directory for the repository and the worktrees '
                     '(default: the current directory)')
    return prs


def execute(args: argparse.Namespace) -> None:
    config = read_config()
    if not config.has_section(args.group):
        sys.exit(f'no group [{args.group}] in srt.conf')
    try:
        setup(args.group, config[args.group], args.dir)
    except SetupError as e:
        sys.exit(f'srt setup: {e}')
    except CalledProcessError as e:
        sys.exit(f'srt setup: {" ".join(e.cmd)} failed')
