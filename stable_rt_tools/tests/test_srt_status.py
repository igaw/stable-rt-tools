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


"""The parts of srt status without the trees of a release: kup ls, the
archive of the mailing list and the next step."""

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from typing import Any, cast
from unittest import mock

from stable_rt_tools import srt_inbox, srt_log, srt_status
from stable_rt_tools.tests.inbox import add_mail

FILES = ('/rt/patches/v6.12.118-rt24/patch-6.12.118-rt24.patch.xz',
         '/rt/patches/v6.12.118-rt24/patches-6.12.118-rt24.tar.xz')

# NOT verified against the output of a real kup: the names, one per line
KUP_LS = '''\
patch-6.12.117-rt23.patch.sign
patch-6.12.117-rt23.patch.xz
patch-6.12.118-rt24.patch.sign
patch-6.12.118-rt24.patch.xz
patches-6.12.118-rt24.tar.sign
patches-6.12.118-rt24.tar.xz
sub/
'''

class TestKup(unittest.TestCase):
    def test_parse(self) -> None:
        names = srt_status.parse_kup_ls(KUP_LS)
        self.assertIn('patch-6.12.118-rt24.patch.xz', names)
        self.assertIn('sub', names)
        # a long format ends with the name as well
        self.assertEqual(srt_status.parse_kup_ls(
            '-rw-r--r-- 1 x y 12 2026-01-01 patch-1.patch.xz\n\n'),
            {'patch-1.patch.xz'})

    def test_uploaded(self) -> None:
        names = srt_status.parse_kup_ls(KUP_LS)
        self.assertTrue(srt_status.uploaded(names, FILES))
        names.discard('patches-6.12.118-rt24.tar.sign')
        self.assertFalse(srt_status.uploaded(names, FILES))
        # another compression of the same file counts
        other = {'patch-6.12.118-rt24.patch.gz',
                 'patch-6.12.118-rt24.patch.sign',
                 'patches-6.12.118-rt24.tar.gz',
                 'patches-6.12.118-rt24.tar.sign'}
        self.assertTrue(srt_status.uploaded(other, FILES))
        # a signature without the file doesn't
        self.assertFalse(srt_status.uploaded(
            {'patch-6.12.118-rt24.patch.sign',
             'patches-6.12.118-rt24.tar.sign'}, FILES))

    def test_kup_ls(self) -> None:
        done = subprocess.CompletedProcess([], 0, KUP_LS, '')
        with mock.patch('subprocess.run', return_value=done) as run:
            names, why = srt_status.kup_ls('/pub/rt/6.12/older')
        self.assertEqual(run.call_args.args[0],
                         ['kup', 'ls', '/pub/rt/6.12/older'])
        self.assertIn('patch-6.12.118-rt24.patch.sign', names or set())
        self.assertEqual(why, '')

    def test_kup_ls_fails(self) -> None:
        failed = subprocess.CompletedProcess([], 255, '',
                                             'ssh: connect: no route\n')
        cases: list[tuple[dict[str, Any], str]] = [
            ({'side_effect': FileNotFoundError()}, 'kup is not installed'),
            ({'side_effect': subprocess.TimeoutExpired('kup', 30)},
             'kup ls /x timed out'),
            ({'return_value': failed},
             'kup ls /x failed (255) ssh: connect: no route'),
        ]
        for kw, why in cases:
            with mock.patch('subprocess.run', **kw):
                self.assertEqual(srt_status.kup_ls('/x'), (None, why))

    def test_upload_step(self) -> None:
        config = {'PRJ_DIR': '/pub/rt/6.12'}
        tag = 'v6.12.118-rt24'
        with mock.patch('stable_rt_tools.srt_status.kup_ls') as kup:
            # not signed: nothing to upload, kup isn't asked
            self.assertEqual(
                srt_status.upload_step('/rt', tag, False, False, config),
                (('srt upload', False), None))
            self.assertEqual(
                srt_status.upload_step('/rt', tag, True, True, config),
                (('srt upload', None), 'offline'))
            self.assertEqual(
                srt_status.upload_step('/rt', tag, True, False, {}),
                (('srt upload', None), 'PRJ_DIR is not set'))
            kup.assert_not_called()
            kup.return_value = (srt_status.parse_kup_ls(KUP_LS), '')
            self.assertEqual(
                srt_status.upload_step('/rt', tag, True, False, config),
                (('srt upload', True), None))
            kup.assert_called_once_with('/pub/rt/6.12/older')


class TestNext(unittest.TestCase):
    def test_first_open(self) -> None:
        self.assertIsNone(srt_status.first_open([('a', True)]))
        self.assertEqual(srt_status.first_open(
            [('a', True), ('b', None), ('c', False)]), ('b', None))
        # srt upload unknown, srt push done: uploaded before
        self.assertIsNone(srt_status.first_open(
            [('srt upload', None), ('srt push', True)]))

    def test_release_next(self) -> None:
        tag = 'v6.12.118-rt24'
        steps: list[srt_status.Step] = [
            ('srt sign', True), ('srt upload', None), ('srt push', False)]
        self.assertEqual(srt_status.release_next(tag, steps, [], {}),
                         'srt upload (unless done already)')
        # all done, announced too: the next release
        self.assertEqual(srt_status.release_next(
            tag, [('srt push', True), ('srt announce', True)], [], {}),
            'srt prep')
        self.assertEqual(srt_status.release_next(
            tag, [('srt push', True), ('srt announce', False)], [], {}),
            'srt announce')
        # the archive can't tell
        self.assertEqual(srt_status.release_next(
            tag, [('srt upload', None), ('srt push', True),
                  ('srt announce', None)], [], {}),
            'srt announce (unless done already)')
        self.assertEqual(srt_status.release_next(
            tag, steps, [f'{tag} is published already'], {}),
            'srt prep --clear, then srt prep')


# A clone of https://lore.kernel.org/stable-rt/0 (git clone --mirror) to
# check the subjects of the real announcements against, optional: the
# tests never fetch from lore.
REAL_INBOX = os.environ.get('SRT_TEST_INBOX', '')


class TestInbox(unittest.TestCase):
    """srt announce: the announcement in the local clone of a fake
    inbox, a local repository as remote."""

    def setUp(self) -> None:
        self.tdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tdir)
        self.inbox = os.path.join(self.tdir, 'stable-rt')
        add_mail(self.inbox, '[ANNOUNCE] v6.12.117-rt23', '<rt23@x>',
                 date='2026-11-11T16:08:21+01:00')
        # other maintainers announce without the v
        add_mail(self.inbox, '[ANNOUNCE] 6.12.118-rt24', '<rt24@x>',
                 'Clark Kent <ck@example.org>', '2026-11-20T23:02:51+00:00')
        add_mail(self.inbox, 'Re: [ANNOUNCE] v6.12.119-rt25', '<re@x>')
        add_mail(self.inbox, '[PATCH RT 1/2] Linux v5.10.248-rt143-rc1',
                 '<p1@x>')
        add_mail(self.inbox, '[PATCH RT 0/2] Linux 5.10.249-rt144-rc1',
                 '<p0@x>')
        # a worktree of a series, for the log
        self.repo = os.path.join(self.tdir, 'v6.12-rt')
        subprocess.run(['git', 'init', '-q', '-b', 'v6.12-rt', self.repo],
                       check=True)
        subprocess.run(['git', '-C', self.repo, '-c', 'user.name=x', '-c',
                        'user.email=x@x', 'commit', '-q', '--allow-empty',
                        '-m', 'x'], check=True)
        self.config = {'INBOX': self.inbox}
        self.git_dir = srt_inbox.clone_dir(self.inbox)
        self.net = mock.patch.object(srt_inbox, 'network_git',
                                     wraps=srt_inbox.network_git).start()
        self.addCleanup(mock.patch.stopall)

    def step(self, tag: str, offline: bool = False, pushed: bool = True,
             config: dict[str, str] | None = None) \
            -> tuple[srt_status.Step, dict[str, object]]:
        return srt_status.announce_step(
            self.repo, tag, None, pushed, offline,
            self.config if config is None else config)

    def age_stamp(self) -> None:
        t = time.time() - srt_inbox.FETCH_INTERVAL - 1
        os.utime(srt_inbox.stamp_path(self.git_dir), (t, t))

    def test_is_announcement(self) -> None:
        def yes(subject: str, tag: str) -> bool:
            return srt_inbox.is_announcement(subject, tag)

        tag = 'v6.12.118-rt24'
        self.assertTrue(yes('[ANNOUNCE] v6.12.118-rt24', tag))
        self.assertTrue(yes('[ANNOUNCE] 6.12.118-rt24', tag))
        self.assertFalse(yes('Re: [ANNOUNCE] v6.12.118-rt24', tag))
        self.assertFalse(yes('[ANNOUNCE] v6.12.118-rt2', tag))
        rc = 'v5.10.248-rt143-rc1'
        self.assertTrue(yes('[PATCH RT 0/2] Linux v5.10.248-rt143-rc1', rc))
        self.assertTrue(yes('[PATCH RT 0/12] Linux 5.10.248-rt143-rc1', rc))
        self.assertFalse(yes('[PATCH RT 1/2] Linux v5.10.248-rt143-rc1',
                             rc))
        self.assertFalse(yes('Re: [PATCH RT 0/2] Linux '
                             'v5.10.248-rt143-rc1', rc))
        self.assertFalse(yes('[ANNOUNCE] v5.10.248-rt143-rc1x', rc))

    def test_clone_dir_and_link(self) -> None:
        self.assertEqual(
            srt_inbox.clone_dir('https://lore.kernel.org/stable-rt/'),
            os.path.join(os.environ['XDG_CACHE_HOME'], 'srt', 'inbox',
                         'stable-rt.git'))
        self.assertEqual(srt_inbox.clone_url(srt_inbox.DEFAULT_INBOX),
                         'https://lore.kernel.org/stable-rt/0')
        self.assertEqual(
            srt_inbox.link(srt_inbox.DEFAULT_INBOX, '<a.b@c>'),
            'https://lore.kernel.org/stable-rt/a.b@c/')
        self.assertIsNone(srt_inbox.link(self.inbox, '<a.b@c>'))

    def test_clone_then_fetch_every_10_minutes(self) -> None:
        step, details = self.step('v6.12.118-rt24')
        self.assertEqual(step, ('srt announce', True))
        self.assertEqual(details, {'mail': {
            'subject': '[ANNOUNCE] 6.12.118-rt24',
            'date': '2026-11-20T23:02:51Z',
            'sender': 'Clark Kent <ck@example.org>',
            'message_id': '<rt24@x>', 'link': None}})
        self.assertEqual(self.net.call_count, 1)
        self.assertIn('clone', self.net.call_args.args[0])
        self.assertTrue(os.path.isdir(self.git_dir))
        # a reply doesn't count, within 10 minutes no fetch
        self.assertEqual(self.step('v6.12.119-rt25'),
                         (('srt announce', False), {}))
        add_mail(self.inbox, '[ANNOUNCE] v6.12.119-rt25', '<rt25@x>')
        self.assertEqual(self.step('v6.12.119-rt25'),
                         (('srt announce', False), {}))
        self.assertEqual(self.net.call_count, 1)
        # after 10 minutes srt fetches
        self.age_stamp()
        step, details = self.step('v6.12.119-rt25')
        self.assertEqual(step, ('srt announce', True))
        self.assertEqual(self.net.call_count, 2)
        self.assertIn('fetch', self.net.call_args.args[0])
        # announced already: the clone has it, no fetch
        self.age_stamp()
        self.assertEqual(self.step('v6.12.117-rt23')[0],
                         ('srt announce', True))
        self.assertEqual(self.net.call_count, 2)

    def test_rc_cover_letter(self) -> None:
        self.assertEqual(self.step('v5.10.249-rt144-rc1')[0],
                         ('srt announce', True))
        self.assertEqual(self.step('v5.10.248-rt143-rc1')[0],
                         ('srt announce', False))

    def test_not_pushed(self) -> None:
        self.assertEqual(self.step('v6.12.118-rt24', pushed=False),
                         (('srt announce', False), {}))
        self.net.assert_not_called()

    def test_offline(self) -> None:
        self.assertEqual(self.step('v6.12.118-rt24', offline=True),
                         (('srt announce', None), {'unknown': 'offline'}))
        self.net.assert_not_called()
        self.step('v6.12.117-rt23')
        self.net.reset_mock()
        # the local clone is searched, never fetched
        self.age_stamp()
        self.assertEqual(self.step('v6.12.118-rt24', offline=True)[0],
                         ('srt announce', True))
        self.assertEqual(self.step('v6.12.119-rt25', offline=True),
                         (('srt announce', None), {'unknown': 'offline'}))
        self.net.assert_not_called()

    def test_fetch_fails(self) -> None:
        config = {'INBOX': os.path.join(self.tdir, 'gone')}
        step, details = self.step('v6.12.118-rt24', config=config)
        self.assertEqual(step, ('srt announce', None))
        self.assertIn('git clone of the inbox failed', str(details['unknown']))
        # tried again only after 10 minutes, unknown until then
        self.assertEqual(self.step('v6.12.118-rt24', config=config),
                         (step, details))
        self.assertEqual(self.net.call_count, 1)
        # a timeout
        with mock.patch('subprocess.run',
                        side_effect=subprocess.TimeoutExpired('git', 60)):
            self.assertEqual(srt_inbox.network_git(['fetch', 'x']),
                             'git fetch of the inbox timed out')

    def test_network_without_terminal(self) -> None:
        done = subprocess.CompletedProcess([], 0, '', '')
        with mock.patch('subprocess.run', return_value=done) as run:
            self.assertIsNone(srt_inbox.network_git(['fetch', 'x']))
        kw = run.call_args.kwargs
        self.assertTrue(kw['start_new_session'])
        self.assertEqual(kw['stdin'], subprocess.DEVNULL)
        self.assertEqual(kw['timeout'], srt_inbox.FETCH_TIMEOUT)
        self.assertEqual(kw['env']['GIT_TERMINAL_PROMPT'], '0')

    def test_found_is_logged(self) -> None:
        step, details = self.step('v6.12.118-rt24')
        event = srt_log.read_log(self.repo)[-1]
        self.assertEqual(event['step'], 'announced')
        self.assertEqual(event['release'], 'v6.12.118-rt24')
        self.assertEqual(event['message_id'], '<rt24@x>')
        self.assertEqual(event['sender'], 'Clark Kent <ck@example.org>')
        # the next srt status takes it from the log, no git, no network
        with mock.patch.object(srt_inbox, 'find',
                               side_effect=AssertionError), \
                mock.patch.object(srt_inbox, 'sync',
                                  side_effect=AssertionError):
            self.assertEqual(self.step('v6.12.118-rt24', offline=True),
                             (step, details))
        self.assertEqual(len(srt_log.read_log(self.repo)), 1)

    def test_inbox_empty(self) -> None:
        self.assertEqual(self.step('v6.12.118-rt24', config={'INBOX': ''}),
                         (('srt announce', None),
                          {'unknown': 'INBOX is empty'}))
        self.net.assert_not_called()

    @unittest.skipUnless(os.path.isdir(REAL_INBOX),
                         'no clone of lore.kernel.org/stable-rt')
    def test_real_inbox(self) -> None:
        """A copy of the real archive, as the remote: no network."""
        lore = os.path.join(self.tdir, 'lore', 'stable-rt')
        shutil.copytree(REAL_INBOX, os.path.join(lore, '0'))
        config = {'INBOX': lore}
        mails = {}
        for tag in ('v6.12.117-rt23', 'v6.12.118-rt24', 'v6.1.192-rt72'):
            step, details = self.step(tag, config=config)
            self.assertEqual(step, ('srt announce', True), tag)
            mails[tag] = details['mail']
        self.assertEqual(self.net.call_count, 1)
        self.assertEqual(mails['v6.12.118-rt24'], {
            'subject': '[ANNOUNCE] v6.12.118-rt24',
            'date': '2026-11-21T13:57:47+01:00',
            'sender': 'Daniel Wagner <wagi@monom.org>',
            'message_id': '<5f522636-3555-4694-ac55-923c981eab3f@kernel.org>',
            'link': None})
        # announced without the v
        self.assertEqual(cast(dict[str, str], mails['v6.1.192-rt72'])
                         ['subject'], '[ANNOUNCE] 6.1.192-rt72')
        self.assertEqual(self.step('v6.12.119-rt25', config=config),
                         (('srt announce', False), {}))
        # the link for people, with the real INBOX
        found = srt_inbox.find(srt_inbox.DEFAULT_INBOX, 'v6.12.118-rt24',
                               srt_inbox.clone_dir(lore))
        assert found is not None
        self.assertEqual(found.link, 'https://lore.kernel.org/stable-rt/'
                         '5f522636-3555-4694-ac55-923c981eab3f@kernel.org/')


if __name__ == '__main__':
    unittest.main()
