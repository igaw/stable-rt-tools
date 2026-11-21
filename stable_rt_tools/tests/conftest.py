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
import subprocess
from collections.abc import Iterator

import pytest

from stable_rt_tools import srt_inbox, srt_log
from stable_rt_tools.tests import helpers


def _git_common_dir(path: str) -> str | None:
    p = subprocess.run(['git', '-C', path, 'rev-parse',
                        '--path-format=absolute', '--git-common-dir'],
                       capture_output=True, encoding='utf-8')
    return p.stdout.strip() if p.returncode == 0 else None


# the repository of srt itself, if the tests run in one
SOURCE_GIT_DIR = _git_common_dir(os.path.dirname(os.path.abspath(__file__)))


# who commits and tags in the tests, the identity of the test GPG key
NAME = 'Mighty Eagle'
EMAIL = 'me@incredible.com'

# set by git for hooks, or by srt users: none of them may leak into a test
UNSET = ('GNUPGHOME', 'SRT_CONF', 'OLD_TAG', 'NEW_TAG', 'GIT_DIR',
         'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG',
         'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT')


@pytest.fixture(autouse=True, scope='session')
def _gnupg_template() -> Iterator[None]:
    """The tests copy the keyring with the test key made once per
    session (helpers.gnupg_home): remove it at the end, no gpg-agent is
    left running."""
    yield
    helpers.remove_gnupg_template()


@pytest.fixture(autouse=True)
def _isolated_from_the_developer(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory) -> None:
    """The tests must not depend on the machine they run on: no git
    configuration of the user or the system (commit.gpgsign,
    init.defaultBranch, hooks, a signing key), no GPG keyring, no
    srt.conf. HOME is an empty directory, git commits as the owner of
    the test key. A test which needs a setting sets it, e.g. in the
    configuration of its repository."""
    home = tmp_path_factory.mktemp('home')
    gitconfig = home / '.gitconfig'
    gitconfig.touch()
    for name in UNSET:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(gitconfig))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_EDITOR', 'true')
    for who in ('AUTHOR', 'COMMITTER'):
        monkeypatch.setenv(f'GIT_{who}_NAME', NAME)
        monkeypatch.setenv(f'GIT_{who}_EMAIL', EMAIL)


@pytest.fixture(autouse=True)
def _keep_cwd() -> Iterator[None]:
    """Many tests chdir into a temporary repository: go back afterwards,
    the next test must not start in a directory that is gone."""
    cwd = os.getcwd()
    yield
    os.chdir(cwd)


@pytest.fixture(autouse=True)
def _no_log_in_the_srt_repository(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests which mock git run srt steps in the repository of srt: they
    must not write a log into it."""
    log_path = srt_log.get_log_path

    def guarded(path: str | None = None) -> str | None:
        log = log_path(path)
        if log is not None and SOURCE_GIT_DIR is not None and \
                log.startswith(SOURCE_GIT_DIR + os.sep):
            return None
        return log

    monkeypatch.setattr(srt_log, 'get_log_path', guarded)


@pytest.fixture(autouse=True)
def _no_inbox_from_the_network(monkeypatch: pytest.MonkeyPatch,
                               tmp_path_factory: pytest.TempPathFactory) \
        -> None:
    """srt status clones the archive of the mailing list (INBOX, by
    default lore.kernel.org) once a release is pushed: the tests use a
    cache of their own and never clone or fetch over the network, only
    local fake inboxes."""
    monkeypatch.setenv('XDG_CACHE_HOME',
                       str(tmp_path_factory.mktemp('cache')))
    network_git = srt_inbox.network_git

    def guarded(args: list[str]) -> str | None:
        if any('://' in a for a in args):
            return 'no network in the tests'
        return network_git(args)

    monkeypatch.setattr(srt_inbox, 'network_git', guarded)
