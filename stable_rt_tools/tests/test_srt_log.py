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

import io
import json
import os
import tempfile
import unittest
from shutil import rmtree
from types import SimpleNamespace
from unittest import mock

from stable_rt_tools import about, srt, srt_log, srt_review
from stable_rt_tools.srt_util import cmd, write_srt_state

COMMIT = 'a' * 40


class TestLog(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(rmtree, self.repo)
        cmd(['git', 'init', '-q', '--initial-branch=v6.12-rt-patches',
             self.repo])
        cmd(['git', '-C', self.repo, 'config', 'user.name', 'Mighty Eagle'])
        cmd(['git', '-C', self.repo, 'config', 'user.email',
             'me@incredible.com'])
        os.chdir(self.repo)
        cmd(['git', 'commit', '-q', '--allow-empty', '-m', 'x'])
        self.log = os.path.join(self.repo, '.git', 'srt', 'v6.12-rt.log')

    def output(self, *argv):
        out = io.StringIO()
        with mock.patch('sys.argv', ['srt', *argv]), \
                mock.patch('sys.stdout', out), \
                mock.patch.object(srt, 'convert_config_files'):
            srt.main()
        return out.getvalue()

    def test_log_step(self):
        srt_log.log_step('quilt queue', 'v6.12.118-rt24', 'v6.12.117-rt23',
                         tag='v6.12.118-rt24-patches', commit=COMMIT,
                         dropped=[], skipped=None)
        with open(self.log) as f:
            event = json.loads(f.read())
        time = event.pop('time')
        self.assertRegex(time, r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$')
        # the common fields first, None values left out
        self.assertEqual(list(event.items()), [
            ('series', 'v6.12-rt'), ('step', 'quilt queue'),
            ('release', 'v6.12.118-rt24'), ('old', 'v6.12.117-rt23'),
            ('srt', about.__version__), ('user', 'Mighty Eagle'),
            ('tag', 'v6.12.118-rt24-patches'), ('commit', COMMIT),
            ('dropped', [])])

    def test_old_from_the_prepared_release(self):
        write_srt_state({'old_tag': 'v6.12.117-rt23',
                         'new_tag': 'v6.12.118-rt24'})
        srt_log.log_step('tag', 'v6.12.118-rt24')
        srt_log.log_step('tag', 'v6.12.119-rt25')
        first, second = srt_log.read_log()
        self.assertEqual(first['old'], 'v6.12.117-rt23')
        self.assertNotIn('old', second)

    def test_failure_is_a_warning(self):
        os.makedirs(self.log)
        err = io.StringIO()
        with mock.patch('sys.stderr', err):
            srt_log.log_step('sign', 'v6.12.118-rt24')
        self.assertIn('srt: warning: srt sign is not in the log',
                      err.getvalue())
        # a broken context neither
        with mock.patch('sys.stderr', err):
            srt_log.log_step('create', ctx=SimpleNamespace())  # type: ignore
        self.assertIn('srt create is not in the log', err.getvalue())

    def test_detached_head(self):
        cmd(['git', 'checkout', '-q', '--detach'])
        srt_log.log_step('prep')
        self.assertFalse(os.path.exists(os.path.dirname(self.log)))
        with self.assertRaises(SystemExit):
            srt_log.read_log()

    def test_srt_log(self):
        self.assertEqual(self.output('log'), 'no history of v6.12-rt yet\n')
        self.assertEqual(json.loads(self.output('log', '--json')), [])
        srt_log.log_step('prep', 'v6.12.118-rt24', 'v6.12.117-rt23',
                         workflow='quilt')
        with open(self.log, 'a') as f:
            f.write('{"cut off\n')
        srt_log.log_step('quilt release', 'v6.12.118-rt24',
                         tag='v6.12.118-rt24', commit=COMMIT)
        lines = self.output('log').splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r'^\d{4}-\d\d-\d\d \d\d:\d\d  prep  ')
        self.assertIn('prep           v6.12.118-rt24 (from v6.12.117-rt23)'
                      '  workflow=quilt  by Mighty Eagle', lines[0])
        self.assertIn('quilt release  v6.12.118-rt24  tag=v6.12.118-rt24  '
                      f'commit={COMMIT[:12]}  by Mighty Eagle', lines[1])
        last = self.output('log', '-n', '1')
        self.assertEqual(last.splitlines(), lines[1:])
        events = json.loads(self.output('log', '--json', '-n', '1'))
        self.assertEqual([e['step'] for e in events], ['quilt release'])
        self.assertEqual(events[0]['commit'], COMMIT)


class TestReviewMails(unittest.TestCase):
    def test_sent_mails_are_logged(self):
        mails = tempfile.mkdtemp()
        self.addCleanup(rmtree, mails)
        for name in ('0000-cover-letter.patch', '0001-Add-file1.patch'):
            open(os.path.join(mails, name), 'w').close()
        ctx = SimpleNamespace(new=SimpleNamespace(mails_dir=mails))
        sent = ('OK. Log says:\nSendmail: /usr/sbin/sendmail\n'
                'Subject: [PATCH RT 0/1] Linux v4.4.14-rt5-rc1\n'
                'Message-ID: <cover@example.org>\n\nResult: OK\n'
                'OK. Log says:\nMessage-ID: <patch1@example.org>\n')
        with mock.patch.object(srt_review, 'cmd', return_value=sent), \
                mock.patch.object(srt_review, 'confirm', return_value=True), \
                mock.patch.object(srt_review, 'log_step') as log, \
                mock.patch('sys.stdout', io.StringIO()):
            srt_review.send_rc_patches(
                {'MAIL_TO': 'Foo <foo@bar>'}, ctx,  # type: ignore
                SimpleNamespace(suppress_cc=True))  # type: ignore
        log.assert_called_once_with(
            'announce', ctx=ctx, result='review mails sent', mails=2,
            to='Foo <foo@bar>', message_id='<cover@example.org>')


if __name__ == '__main__':
    unittest.main()
