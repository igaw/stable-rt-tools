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
import sys
import unittest
from subprocess import CalledProcessError
from unittest import mock

from stable_rt_tools import srt_util
from stable_rt_tools.srt import srt_get_argparser
from stable_rt_tools.srt_tag import tag_next_step


def parse(*argv):
    return srt_get_argparser().parse_args(list(argv))


class TestYes(unittest.TestCase):

    def test_default_no(self):
        self.assertFalse(getattr(parse('push'), 'yes', False))
        self.assertFalse(getattr(parse('quilt', 'queue'), 'yes', False))

    def test_before_and_after_the_command(self):
        for argv in (('-y', 'push'), ('push', '-y'), ('--yes', 'upload'),
                     ('-y', 'quilt', 'undo'), ('quilt', 'undo', '--yes'),
                     ('quilt', '-y', 'rebase')):
            self.assertTrue(getattr(parse(*argv), 'yes', False), argv)

    def test_confirm(self):
        self.addCleanup(srt_util.set_assume_yes, False)
        srt_util.set_assume_yes(True)
        out = io.StringIO()
        # stdin is not read at all
        with mock.patch('sys.stdin', io.StringIO('n\n')), \
                mock.patch('sys.stdout', out):
            self.assertTrue(srt_util.confirm('OK to push?'))
        self.assertEqual(out.getvalue(), 'OK to push? (y/n): y (--yes)\n')


class TestCmd(unittest.TestCase):

    def test_keeps_the_indentation(self):
        out = srt_util.cmd([sys.executable, '-c',
                            'print(" a | 1 +"); print(" 1 file")'])
        self.assertEqual(out, ' a | 1 +\n 1 file')

    def test_stderr_of_a_failed_command(self):
        with self.assertRaises(CalledProcessError) as cm:
            srt_util.cmd([sys.executable, '-c',
                          'import sys; sys.exit("fatal: bad ref")'])
        self.assertEqual(cm.exception.returncode, 1)
        self.assertIn(b'fatal: bad ref', cm.exception.stderr)

    def test_dirty_files(self):
        import os
        import tempfile

        from stable_rt_tools.srt_quilt import dirty_files, git

        with tempfile.TemporaryDirectory() as path:
            git(path, 'init', '-q')
            with open(os.path.join(path, 'localversion-rt'), 'w') as f:
                f.write('-rt1\n')
            git(path, 'add', 'localversion-rt')
            git(path, '-c', 'user.name=a', '-c', 'user.email=a@b',
                'commit', '-q', '-m', 'x')
            with open(os.path.join(path, 'localversion-rt'), 'w') as f:
                f.write('-rt2\n')
            # ' M localversion-rt', the first column is a space
            self.assertEqual(dirty_files(path), ['localversion-rt'])


class TestMain(unittest.TestCase):

    def run_main(self, *argv, error=None):
        from stable_rt_tools import srt

        error = error or CalledProcessError(
            128, ['git', 'describe'], stderr=b'fatal: No names found\n')
        err = io.StringIO()
        with mock.patch('sys.argv', ['srt', *argv]), \
                mock.patch('sys.stderr', err), \
                mock.patch.object(srt, 'convert_config_files'), \
                mock.patch('stable_rt_tools.srt_status.execute',
                           side_effect=error):
            srt.main()
        return err.getvalue()

    def test_failed_command(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main('status')
        # sys.exit(message): on stderr, exit code 1
        self.assertEqual(cm.exception.code,
                         'srt: git describe failed (exit 128)\n'
                         'fatal: No names found')

    def test_failed_command_debug(self):
        with self.assertRaises(CalledProcessError):
            self.run_main('-d', 'status')

    def test_interrupt(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main('status', error=KeyboardInterrupt())
        self.assertEqual(cm.exception.code, 130)


class TestNextStep(unittest.TestCase):

    def test_git_workflow_tags(self):
        self.assertIn('srt announce',
                      tag_next_step('v4.19.291-rt127-rc1'))
        self.assertIn('srt create', tag_next_step('v4.19.291-rt127-rebase'))
        self.assertIn('-rebase worktree', tag_next_step('v4.19.291-rt127'))


class TestWithoutOffsets(unittest.TestCase):

    def test_offsets_and_git_lines(self):
        from stable_rt_tools.srt_check import without_offsets

        git = ('Subject: x\n---\n'
               'diff --git a/k.c b/k.c\nindex 5d1b880..4e6fb9b 100644\n'
               '--- a/k.c\n+++ b/k.c\n'
               '@@ -1873,7 +1873,7 @@ void hrtimer_interrupt(struct clock)\n'
               ' a\n-b\n+c\n')
        quilt = ('Subject: x\n---\n--- a/k.c\n+++ b/k.c\n'
                 '@@ -1880,7 +1880,7 @@ void hrtimer_interrupt(struct clo\n'
                 ' a\n-b\n+c\n')
        self.assertEqual(without_offsets(git), without_offsets(quilt))
        self.assertNotEqual(without_offsets(quilt),
                            without_offsets(quilt.replace('+c', '+d')))
