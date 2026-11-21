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


"""The parts of srt status without git: kup ls and the next step."""

import subprocess
import unittest
from typing import Any
from unittest import mock

from stable_rt_tools import srt_status

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
        self.assertEqual(srt_status.release_next(
            tag, [('srt push', True)], [], {}), 'srt announce')
        self.assertEqual(srt_status.release_next(
            tag, steps, [f'{tag} is published already'], {}),
            'srt prep --clear, then srt prep')


if __name__ == '__main__':
    unittest.main()
