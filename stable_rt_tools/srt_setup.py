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

The settings can be given as options; srt setup adds the group to
srt.conf if there is none. In an existing work area the URLs default to
the ones of its remotes.

The repository <repo> and the worktrees are created next to each other
in the setup directory; existing ones are checked, so a series can be
added to the work area of another one. --from starts a series which
does not exist yet from other branches, e.g. of another maintainer.
"""

import argparse
import os
import sys
from collections import ChainMap
from collections.abc import Mapping
from subprocess import CalledProcessError

from stable_rt_tools.srt_prep import worktree_dirs
from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    cmd,
    get_suffix,
    is_quilt_workflow,
    read_config,
    with_defaults,
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
        option = {k: o for o, k in OPTIONS.items()}[key].replace('_', '-')
        raise SetupError(f'{key} is not set, add it to srt.conf or use '
                         f'--{option}')
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


def _has_remote_branch(repo: str, remote: str, branch: str) -> bool:
    return _query(repo, 'rev-parse', '--verify', '--quiet',
                  f'refs/remotes/{remote}/{branch}') is not None


def setup_series_worktree(repo: str, path: str, branch: str, remote: str,
                          source: str | None) -> bool:
    """A worktree for a branch of the series, started from source if
    the branch is not on remote yet. Return True if it still needs to be
    published."""
    upstream = f'{remote}/{branch}'
    if _has_remote_branch(repo, remote, branch):
        setup_worktree(repo, path, branch, upstream)
        return False
    if os.path.isdir(path):
        head = _query(path, 'rev-parse', '--abbrev-ref', 'HEAD')
        if head != branch:
            raise SetupError(f'{path} is on {head}, expected {branch}')
        print(f'ok    {path} ({branch}, not published yet)')
        return True
    if source is None:
        raise SetupError(f'{upstream} does not exist; use --from BRANCH '
                         'to start it from another branch')
    if _query(repo, 'rev-parse', '--verify', '--quiet', source) is None:
        raise SetupError(f'{upstream} does not exist and neither does the '
                         f'branch {source} to start it from')
    if _query(repo, 'rev-parse', '--verify', '--quiet',
              f'refs/heads/{branch}') is not None:
        raise SetupError(f'the branch {branch} exists already, but not on '
                         f'{remote}; publish or delete it')
    print(f'new   {path} ({branch} from {source})')
    _git(repo, 'worktree', 'add', '--no-track', '-b', branch, path, source)
    return True


def _split_source(repo: str, remote: str, source_branch: str,
                    source_url: str | None) -> tuple[str, str]:
    """[REMOTE/]BRANCH -> (remote, branch), the series' remote by default."""
    if '/' in source_branch:
        name, branch = source_branch.split('/', 1)
        if source_url or _query(repo, 'config', '--get',
                                  f'remote.{name}.url') is not None:
            return name, branch
    if source_url:
        raise SetupError('--from-url needs --from REMOTE/BRANCH')
    return remote, source_branch


def setup(group: str, config: Mapping[str, str], parent: str,
          source_branch: str | None = None,
          source_url: str | None = None) -> None:
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
    source_remote = remote
    if source_branch:
        source_remote, source_branch = _split_source(
            repo, remote, source_branch, source_url)
        if source_url:
            setup_remote(repo, source_remote, source_url)
    print('fetch')
    for name in dict.fromkeys(('origin', upstream_remote, remote,
                               source_remote if source_branch else remote)):
        _git(repo, 'fetch', '--tags', name)

    def source(branch: str) -> str | None:
        if not source_branch:
            return None
        return f'{source_remote}/{source_branch}{branch.removeprefix(series)}'

    def exists(branch: str) -> bool:
        src = source(branch)
        return _has_remote_branch(repo, remote, branch) or (
            src is not None and _query(repo, 'rev-parse', '--verify',
                                       '--quiet', src) is not None)

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
                    if b == series or exists(b)
                    or os.path.isdir(os.path.join(parent, b))]
    unpublished = [branch for branch in branches
                   if setup_series_worktree(repo, os.path.join(parent, branch),
                                            branch, remote, source(branch))]
    if unpublished:
        print(f'publish the series on {remote} (srt setup pushes nothing):')
        for branch in unpublished:
            path = os.path.join(parent, branch)
            print(f'  git -C {path} push -u --follow-tags {remote} {branch}')
    print(f'next: cd {os.path.join(parent, series)} && srt prep')


# options of srt setup and the settings they stand for
OPTIONS = {
    'workflow': 'WORKFLOW',
    'suffix': 'SUFFIX',
    'upstream_branch': 'UPSTREAM_BRANCH',
    'upstream_url': 'UPSTREAM_GIT_URL',
    'upstream_remote': 'UPSTREAM_REMOTE',
    'origin_url': 'ORIGIN_GIT_URL',
    'prj_url': 'PRJ_GIT_URL',
    'push_url': 'PRJ_GIT_TREE',
    'prj_dir': 'PRJ_DIR',
}


def derive_settings(group: str, config: Mapping[str, str],
                    parent: str) -> dict[str, str]:
    """The URLs of an existing work area, from its remotes."""
    repo_name, remote, _ = group.split('/', 2)
    repo = os.path.join(os.path.abspath(parent), repo_name)
    if not os.path.isdir(repo):
        return {}
    upstream_remote = config.get('UPSTREAM_REMOTE', 'upstream')
    derived = {}
    for key, git_key in (('ORIGIN_GIT_URL', 'remote.origin.url'),
                         ('PRJ_GIT_URL', f'remote.{remote}.url'),
                         ('PRJ_GIT_TREE', f'remote.{remote}.pushurl'),
                         ('UPSTREAM_GIT_URL',
                          f'remote.{upstream_remote}.url')):
        value = _query(repo, 'config', '--get', git_key)
        if value:
            derived[key] = value
    return derived


def config_path() -> str:
    """The srt.conf srt setup adds groups to."""
    if 'SRT_CONF' in os.environ:
        return os.path.join(os.environ['SRT_CONF'], 'srt.conf')
    return os.path.expanduser('~/.config/srt.conf')


def add_group(path: str, group: str, settings: Mapping[str, str]) -> None:
    """Append the group to srt.conf, keeping what is there."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = ''
    if os.path.exists(path):
        with open(path) as f:
            text = f.read()
    with open(path, 'a') as f:
        if text and not text.endswith('\n\n'):
            f.write('\n' if text.endswith('\n') else '\n\n')
        f.write(f'[{group}]\n')
        for key, value in settings.items():
            f.write(f'{key} = {value}\n')
    print(f'added [{group}] to {path}')


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser(
        'setup', help='create or check the work area of a patch series')
    prs.add_argument('group',
                     help='srt.conf group <repo>/<remote>/<series>, e.g. '
                     'linux/stable-rt/v6.12-rt')
    prs.add_argument('--dir', default='.',
                     help='directory for the repository and the worktrees '
                     '(default: the current directory)')
    opt = prs.add_argument_group(
        'settings', 'written to srt.conf for a new group; the URLs default '
        'to the remotes of an existing work area')
    opt.add_argument('--workflow', choices=('quilt', 'git'))
    opt.add_argument('--suffix', help='release suffix (default: rt)')
    opt.add_argument('--upstream-branch', metavar='BRANCH',
                     help='upstream branch, e.g. linux-6.12.y')
    opt.add_argument('--upstream-url', metavar='URL')
    opt.add_argument('--upstream-remote', metavar='NAME',
                     help='default: upstream')
    opt.add_argument('--origin-url', metavar='URL',
                     help='default: the upstream URL')
    opt.add_argument('--prj-url', metavar='URL',
                     help='URL to fetch the series from')
    opt.add_argument('--push-url', metavar='URL',
                     help='URL to push the series to')
    opt.add_argument('--prj-dir', metavar='DIR',
                     help='kup directory to upload releases to')
    start = prs.add_argument_group(
        'start a series from other branches, e.g. to publish a series of '
        'another maintainer under a new name')
    start.add_argument('--from', dest='source_branch',
                       metavar='[REMOTE/]BRANCH',
                       help='start the series from this branch and its '
                       '-patches, -rebase and -next branches if it does not '
                       'exist yet; not stored in srt.conf')
    start.add_argument('--from-url', dest='source_url', metavar='URL',
                      help='URL of REMOTE if it does not exist yet')
    return prs


def execute(args: argparse.Namespace) -> None:
    options = {key: getattr(args, opt) for opt, key in OPTIONS.items()
               if getattr(args, opt, None) is not None}
    config = read_config()
    try:
        if config.has_section(args.group):
            group = with_defaults(config[args.group])
            for key, value in options.items():
                if group.get(key) != value:
                    print(f'{key} = {value} differs from srt.conf, edit '
                          f'{config_path()} to keep it', file=sys.stderr)
        else:
            group = with_defaults(config[config.default_section])
        settings: Config = ChainMap(options, group)  # type: ignore[arg-type]
        derived = derive_settings(args.group, settings, args.dir)
        settings = ChainMap(options, group, derived)  # type: ignore[arg-type]
        if not config.has_section(args.group):
            new = {**{k: v for k, v in derived.items()
                      if k not in group}, **options}
            add_group(config_path(), args.group, new)
        setup(args.group, settings, args.dir, args.source_branch,
              args.source_url)
    except SetupError as e:
        sys.exit(f'srt setup: {e}')
    except CalledProcessError as e:
        sys.exit(f'srt setup: {" ".join(e.cmd)} failed')
