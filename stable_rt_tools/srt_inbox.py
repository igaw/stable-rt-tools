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


"""Whether a release is announced: its mail in a local clone of the
public inbox of the mailing list, e.g. https://lore.kernel.org/stable-rt.

The archive of a public-inbox (v2) is a git repository: one commit per
mail, the commit subject is the subject of the mail, the author its
sender and date, the tree holds the raw message as blob m. srt keeps a
bare mirror of it in $XDG_CACHE_HOME/srt/inbox/<name>.git, a cache
which can be removed any time.

No load on the archive: srt only clones and fetches the git repository,
never the search, feeds or pages of the web interface. It clones on the
first need and fetches at most every FETCH_INTERVAL seconds. The link
to the mail is only printed, for people.
"""

import email.parser
import email.policy
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass

DEFAULT_INBOX = 'https://lore.kernel.org/stable-rt'

# Epoch 0 of the public-inbox v2 archive. A new epoch (/1) only starts
# when one reaches about 1 GB, stable-rt has about 1 MB since 2023:
# epoch 0 is enough for a long time.
EPOCH = '0'

# fetch at most every 10 minutes, and don't let it hang srt status
FETCH_INTERVAL = 600
FETCH_TIMEOUT = 60


@dataclass(frozen=True)
class Mail:
    """The mail of an announcement, as the archive has it."""
    subject: str
    date: str
    sender: str
    message_id: str
    link: str | None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def clone_url(inbox: str) -> str:
    return inbox.rstrip('/') + '/' + EPOCH


def cache_dir() -> str:
    base = os.environ.get('XDG_CACHE_HOME') or \
        os.path.expanduser('~/.cache')
    return os.path.join(base, 'srt', 'inbox')


def clone_dir(inbox: str) -> str:
    """The local clone of the inbox, named after its last path
    component: ~/.cache/srt/inbox/stable-rt.git."""
    name = os.path.basename(inbox.rstrip('/'))
    if name.endswith('.git'):
        name = name[:-len('.git')]
    return os.path.join(cache_dir(), (name or 'inbox') + '.git')


def stamp_path(git_dir: str) -> str:
    """When srt last cloned or fetched, with why it failed if it did:
    next to the clone, so a failed clone counts too."""
    return git_dir + '.fetched'


def network_git(args: list[str]) -> str | None:
    """Run git with args, which clone or fetch the inbox: in its own
    session, without a terminal to ask for credentials, with a timeout.
    Returns why it failed, None when it worked."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    what = 'git clone' if 'clone' in args else 'git fetch'
    try:
        p = subprocess.run(['git', *args], capture_output=True,
                           encoding='utf-8', errors='replace',
                           stdin=subprocess.DEVNULL, timeout=FETCH_TIMEOUT,
                           start_new_session=True, env=env)
    except FileNotFoundError:
        return 'git is not installed'
    except subprocess.TimeoutExpired:
        return f'{what} of the inbox timed out'
    if p.returncode:
        err = (p.stderr.strip().splitlines() or [''])[-1]
        return f'{what} of the inbox failed ({p.returncode}) {err}'.strip()
    return None


def _clone(url: str, git_dir: str) -> str | None:
    parent = os.path.dirname(git_dir)
    os.makedirs(parent, exist_ok=True)
    # clone next to it and rename: a clone cut off isn't taken for one
    tmp = tempfile.mkdtemp(prefix='.clone-', dir=parent)
    try:
        why = network_git(['clone', '--quiet', '--mirror', url,
                           os.path.join(tmp, 'inbox.git')])
        if why is None:
            os.rename(os.path.join(tmp, 'inbox.git'), git_dir)
        return why
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sync(inbox: str, git_dir: str | None = None) -> str | None:
    """Clone the inbox if there is no clone yet, else fetch it, at most
    every FETCH_INTERVAL seconds. Returns why it failed, None when it
    worked; within the interval the result of the last try."""
    git_dir = git_dir or clone_dir(inbox)
    stamp = stamp_path(git_dir)
    try:
        if time.time() - os.path.getmtime(stamp) < FETCH_INTERVAL:
            with open(stamp) as f:
                return f.read().strip() or None
    except OSError:
        pass
    url = clone_url(inbox)
    if os.path.isdir(git_dir):
        # the URL each time, not the remote of the clone: INBOX may
        # have changed
        why = network_git(['--git-dir', git_dir, 'fetch', '--quiet',
                           '--prune', url, '+refs/heads/*:refs/heads/*'])
    else:
        why = _clone(url, git_dir)
    try:
        with open(stamp, 'w') as f:
            f.write(why or '')
    except OSError:
        pass
    return why


def is_announcement(subject: str, tag: str) -> bool:
    """True if subject is the one of the announcement of the release
    tag, with or without the v: [ANNOUNCE] v6.12.118-rt24, for a release
    candidate the cover letter of its review mails:
    [PATCH RT 0/N] Linux v5.10.248-rt143-rc1. Replies (Re: ...) and the
    patches of the series (1/N ...) don't count."""
    bare = tag[1:] if tag.startswith('v') else tag
    if '-rc' not in tag:
        return subject in (f'[ANNOUNCE] {tag}', f'[ANNOUNCE] {bare}')
    head, sep, rest = subject.partition('/')
    if not sep or head != '[PATCH RT 0':
        return False
    count, sep, title = rest.partition('] ')
    return bool(sep) and count.isdigit() and \
        title in (f'Linux {tag}', f'Linux {bare}')


def _git(git_dir: str, *args: str) -> bytes:
    return subprocess.run(['git', '--git-dir', git_dir, *args],
                          capture_output=True, check=True,
                          stdin=subprocess.DEVNULL).stdout


def message_id(git_dir: str, commit: str) -> str:
    """The Message-ID of the mail of commit, from its raw message m."""
    raw = _git(git_dir, 'cat-file', 'blob', f'{commit}:m')
    headers = email.parser.BytesHeaderParser(
        policy=email.policy.default).parsebytes(raw)
    return str(headers.get('Message-ID', '')).strip()


def link(inbox: str, msgid: str) -> str | None:
    """The link to the mail in the web interface, for people only."""
    if not msgid or not inbox.startswith(('https://', 'http://')):
        return None
    return f"{inbox.rstrip('/')}/{msgid.strip('<>')}/"


def find(inbox: str, tag: str, git_dir: str | None = None) -> Mail | None:
    """The announcement of tag in the local clone of inbox, the first
    one if it was sent more than once. None if there is none, or no
    clone."""
    git_dir = git_dir or clone_dir(inbox)
    if not os.path.isdir(git_dir):
        return None
    try:
        out = _git(git_dir, 'log', '--all', '--reverse',
                   '--format=%H%x00%aI%x00%an <%ae>%x00%s')
    except subprocess.CalledProcessError:
        # e.g. an empty clone
        return None
    for line in out.decode('utf-8', 'replace').splitlines():
        fields = line.split('\0')
        if len(fields) != 4 or not is_announcement(fields[3], tag):
            continue
        commit, date, sender, subject = fields
        try:
            msgid = message_id(git_dir, commit)
        except subprocess.CalledProcessError:
            msgid = ''
        return Mail(subject, date, sender, msgid, link(inbox, msgid))
    return None
