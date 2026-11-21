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

from stable_rt_tools import srt_log


def _git_common_dir(path: str) -> str | None:
    p = subprocess.run(['git', '-C', path, 'rev-parse',
                        '--path-format=absolute', '--git-common-dir'],
                       capture_output=True, encoding='utf-8')
    return p.stdout.strip() if p.returncode == 0 else None


# the repository of srt itself, if the tests run in one
SOURCE_GIT_DIR = _git_common_dir(os.path.dirname(os.path.abspath(__file__)))


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
