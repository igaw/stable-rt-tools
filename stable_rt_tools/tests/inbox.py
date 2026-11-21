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


"""A fake public inbox for the tests, as lore.kernel.org has it: epoch
0 is a git repository with one commit per mail, the subject of the mail
as commit subject, its sender and date as author, the raw message as
blob m."""

import os
import subprocess


def add_mail(inbox: str, subject: str, msgid: str,
             sender: str = 'Mighty Eagle <me@incredible.com>',
             date: str = '2026-11-21T13:57:47+01:00') -> None:
    """Add a mail to the fake inbox (the directory INBOX names)."""
    repo = os.path.join(inbox, '0')
    if not os.path.isdir(repo):
        os.makedirs(repo)
        subprocess.run(['git', 'init', '-q', '-b', 'master', repo],
                       check=True)
    name, _, addr = sender.partition(' <')
    with open(os.path.join(repo, 'm'), 'w') as f:
        f.write(f'From: {sender}\nSubject: {subject}\nDate: {date}\n'
                f'Message-ID: {msgid}\n\nbody\n')
    env = dict(os.environ, GIT_AUTHOR_NAME=name,
               GIT_AUTHOR_EMAIL=addr.rstrip('>'), GIT_AUTHOR_DATE=date,
               GIT_COMMITTER_NAME='inbox', GIT_COMMITTER_EMAIL='inbox@x')
    subprocess.run(['git', '-C', repo, 'add', 'm'], check=True)
    subprocess.run(['git', '-C', repo, 'commit', '-q', '--no-gpg-sign',
                    '-m', subject], check=True, env=env)
