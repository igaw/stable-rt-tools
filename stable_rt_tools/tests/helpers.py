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


"""Helpers shared by the tests."""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import cast
from unittest import mock

from stable_rt_tools.srt_util import cmd


def sort_steps(names):
    """The steps of a test (step1_..., step2_..., step10_..., step8b_...)
    in their natural order, the order a test_ method runs them."""
    def key(name):
        return [int(c) if c.isdigit() else c
                for c in re.split('([0-9]+)', name)]
    return sorted((n for n in names if n.startswith('step')), key=key)


def make_args(old_tag=None, new_tag=None):
    """The command line arguments OLD_TAG and NEW_TAG of a step."""
    return argparse.Namespace(OLD_TAG=old_tag, NEW_TAG=new_tag)


def temp_dir(test: unittest.TestCase) -> str:
    """A temporary directory, removed when the test is done."""
    path = tempfile.mkdtemp(prefix='srt-test-')
    test.addCleanup(shutil.rmtree, path, ignore_errors=True)
    return path


def stub_stdin(test: unittest.TestCase, answers: str) -> None:
    """Let srt read answers from stdin, e.g. 'y' to its question."""
    patcher = mock.patch('sys.stdin', io.StringIO(answers))
    patcher.start()
    test.addCleanup(patcher.stop)


def stub_stdouts(test: unittest.TestCase) -> None:
    """Capture what srt prints, until the test is done or the next
    stub_stdouts(): see stdout_text() and stderr_text()."""
    for name in ('sys.stdout', 'sys.stderr'):
        patcher = mock.patch(name, io.StringIO())
        patcher.start()
        test.addCleanup(patcher.stop)


def stdout_text() -> str:
    """The output captured since stub_stdouts()."""
    return cast(io.StringIO, sys.stdout).getvalue()


def stderr_text() -> str:
    """The error output captured since stub_stdouts()."""
    return cast(io.StringIO, sys.stderr).getvalue()


def find_string(lines, token):
    """Whether one of the lines is token, but for white space."""
    return any(line.strip() == token for line in lines.splitlines())


def git(path, *args):
    return cmd(['git', '-C', path] + list(args))


def identity(path):
    """Commit in the repository at path as the owner of the test key.
    The environment of the tests says so too, but srt reads it from the
    git configuration (srt log, the defaults of srt.conf)."""
    git(path, 'config', 'user.name', 'Mighty Eagle')
    git(path, 'config', 'user.email', 'me@incredible.com')


def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


def replace_line(path, old, new):
    write(path, read(path).replace(old + '\n', new + '\n', 1))


def kernel_makefile(version):
    """The top of a kernel Makefile, the version srt commit reads."""
    major, minor, patch = version.split('.')
    return ('# SPDX-License-Identifier: GPL-2.0\n'
            f'VERSION = {major}\n'
            f'PATCHLEVEL = {minor}\n'
            f'SUBLEVEL = {patch}\n'
            'EXTRAVERSION =\n'
            'NAME = Fake Kernel\n'
            '\n'
            '# *DOCUMENTATION*\n'
            '# no build, only the version\n'
            '\n')


def set_sublevel(version):
    """A new stable release: SUBLEVEL of the Makefile in the cwd."""
    write('Makefile', re.sub(r'(?m)^SUBLEVEL = .*$',
                             f'SUBLEVEL = {version.split(".")[2]}',
                             read('Makefile')))

gnupg_config = """
Key-Type: eddsa
Key-Curve: ed25519
Key-Usage: sign
Name-Real: Mighty Eagle
Name-Email: me@incredible.com
Expire-Date: 0
%no-protection
%commit
%echo done
"""

# the keyring with the test key, made once per test session: (GNUPGHOME,
# key id)
_gnupg_template: tuple[str, str] | None = None


def generate_key(gnupghome: str, batch: str = gnupg_config) -> None:
    """Add a key to the keyring at gnupghome, as batch describes it."""
    path = os.path.join(gnupghome, 'gpg.batch')
    with open(path, 'w') as f:
        f.write(batch)
    cmd(['gpg', '--batch', '--generate-key', path],
        env=dict(os.environ, GNUPGHOME=gnupghome))
    os.remove(path)


def stop_gpg_agent(gnupghome: str) -> None:
    """Stop the gpg-agent of the keyring and remove its socket directory
    (in /run/user/<uid>/gnupg, for a keyring which is not ~/.gnupg)."""
    for args in (['--kill', 'all'], ['--remove-socketdir']):
        subprocess.run(['gpgconf', '--homedir', gnupghome, *args],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _template() -> tuple[str, str]:
    global _gnupg_template
    if _gnupg_template is None:
        home = tempfile.mkdtemp(prefix='srt-test-gnupg-')
        generate_key(home)
        lines = cmd(['gpg', '--list-secret-keys', '--with-colons'],
                    env=dict(os.environ, GNUPGHOME=home))
        fpr = next(line.split(':')[-2] for line in lines.splitlines()
                   if line.startswith('fpr:'))
        _gnupg_template = (home, fpr)
    return _gnupg_template


def remove_gnupg_template() -> None:
    """At the end of the test session: stop the agent of the keyring the
    copies were made of, remove it."""
    global _gnupg_template
    if _gnupg_template is not None:
        stop_gpg_agent(_gnupg_template[0])
        shutil.rmtree(_gnupg_template[0], ignore_errors=True)
        _gnupg_template = None


def gnupg_home(test: unittest.TestCase) -> tuple[str, str]:
    """A keyring of the test's own with the test key: (GNUPGHOME, key
    id). Generating a key is slow, it is generated once per session and
    every test gets a copy, removed again (and its gpg-agent stopped)
    when the test is done."""
    template, key = _template()
    home = tempfile.mkdtemp(prefix='srt-test-gnupg-')
    # without the sockets of the agent of the template
    shutil.copytree(template, home, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('S.*', '*.lock'))
    os.chmod(home, 0o700)
    test.addCleanup(shutil.rmtree, home, ignore_errors=True)
    test.addCleanup(stop_gpg_agent, home)
    return home, key
