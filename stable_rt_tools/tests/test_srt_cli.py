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

import argparse
import io
import os
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


class TestUpload(unittest.TestCase):

    def test_missing_file(self):
        from stable_rt_tools.srt_upload import upload

        ctx = mock.Mock()
        ctx.new.files = ['/nonexistent/patch-6.12-rt1.patch.xz']
        out = io.StringIO()
        with mock.patch('sys.stdout', out), \
                self.assertRaises(SystemExit) as cm:
            upload({}, ctx)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('Unable to read /nonexistent/patch-6.12-rt1.patch.xz',
                      str(cm.exception.code))


class TestNextStep(unittest.TestCase):

    def test_git_workflow_tags(self):
        self.assertIn('srt announce',
                      tag_next_step('v4.19.291-rt127-rc1'))
        self.assertIn('srt create', tag_next_step('v4.19.291-rt127-rebase'))
        self.assertIn('-rebase worktree', tag_next_step('v4.19.291-rt127'))


class TestTag(unittest.TestCase):

    def run_tag(self, msg, rc, config=None):
        from stable_rt_tools import srt_tag

        calls = []
        self.out = io.StringIO()

        def fake_cmd(args, env=None):
            calls.append(args)
            return msg if args[:2] == ['git', 'log'] else ''

        with mock.patch.object(srt_tag, 'cmd', side_effect=fake_cmd), \
                mock.patch.object(srt_tag, 'confirm', return_value=True), \
                mock.patch.object(srt_tag, 'get_gpg_env', return_value={}), \
                mock.patch.object(srt_tag, 'get_last_release',
                                  return_value='v4.19.290-rt126'), \
                mock.patch('sys.stdout', self.out):
            srt_tag.tag(config or {'GPG_KEY_ID': 'KEY'}, rc)
        return [c for c in calls if c[:2] == ['git', 'tag']]

    def test_test_command(self):
        # the release candidate is the time to test: TEST_COMMAND
        config = {'GPG_KEY_ID': 'KEY',
                  'TEST_COMMAND': 'lab-test {tag} {old_tag} {series}'}
        self.run_tag('Linux 4.19.291-rt127', 1, config)
        self.assertIn('test with:\n'
                      '    lab-test v4.19.291-rt127-rc1 v4.19.290-rt126 '
                      'v4.19-rt\nnext: srt test, then srt announce',
                      self.out.getvalue())
        # the release itself: tested as release candidate already
        self.run_tag('Linux 4.19.291-rt127', None, config)
        self.assertNotIn('test with:', self.out.getvalue())

    def test_release(self):
        tags = self.run_tag('Linux 4.19.291-rt127\n\nSigned-off-by: x', None)
        self.assertEqual(tags, [['git', 'tag', '-s', '-u', 'KEY', '-m',
                                 'Linux 4.19.291-rt127', 'v4.19.291-rt127']])

    def test_rebase(self):
        tags = self.run_tag('Linux 4.19.291-rt127 REBASE', None)
        self.assertEqual(tags[0][-1], 'v4.19.291-rt127-rebase')

    def test_release_candidate(self):
        # srt commit and srt tag -r 1
        tags = self.run_tag('Linux 4.19.291-rt127', 1)
        self.assertEqual(tags[0][-1], 'v4.19.291-rt127-rc1')
        # srt commit -r 1 and srt tag -r 1: no -rc1-rc1
        tags = self.run_tag('Linux 4.19.291-rt127-rc1', 1)
        self.assertEqual(tags[0][-1], 'v4.19.291-rt127-rc1')
        with self.assertRaises(SystemExit):
            self.run_tag('Linux 4.19.291-rt127-rc1', 2)

    def test_no_release_commit(self):
        with self.assertRaises(SystemExit):
            self.run_tag('Linux 4.19.291', None)


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


class TestSrtTest(unittest.TestCase):

    def test_rc_at_head(self):
        from stable_rt_tools import srt_testrun

        with mock.patch.object(srt_testrun, 'git', return_value=(
                'v4.19.291-rt127-rc1\nv4.19.291-rt127-rc2\nv4.19.291\n'
                'v4.19.291-rt127-rebase\nv4.19.291-cip3-rc1')):
            self.assertEqual(srt_testrun.rc_at_head('.', 'rt'),
                             'v4.19.291-rt127-rc2')
        with mock.patch.object(srt_testrun, 'git',
                               return_value='v6.12.118-rt24'):
            self.assertIsNone(srt_testrun.rc_at_head('.', 'rt'))

    def test_exit_code(self):
        from stable_rt_tools import srt_testrun

        args = argparse.Namespace(dry_run=False)
        with mock.patch.object(srt_testrun, 'get_config', return_value={}), \
                mock.patch.object(srt_testrun, 'run_test', return_value=3):
            with self.assertRaises(SystemExit) as e:
                srt_testrun.execute(args)
        self.assertEqual(e.exception.code, 3)
        with mock.patch.object(srt_testrun, 'get_config', return_value={}), \
                mock.patch.object(srt_testrun, 'run_test', return_value=0):
            srt_testrun.execute(args)


class TestSrtTestResult(unittest.TestCase):
    """SRT_RELEASE in, SRT_TEST_RESULT out."""

    def setUp(self):
        import tempfile
        from shutil import rmtree

        self.dir = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(rmtree, self.dir)
        cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, cwd)

    def run_test(self, command, workflow='quilt'):
        from stable_rt_tools import srt_testrun

        config = {'TEST_COMMAND': command, 'WORKFLOW': workflow}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(srt_testrun, 'release_to_test', return_value=(
                'v6.12.119-rt25', 'v6.12.118-rt24')), \
                mock.patch.object(srt_testrun, 'confirm', return_value=True), \
                mock.patch.object(srt_testrun, 'log_step') as log, \
                mock.patch('sys.stdout', out), mock.patch('sys.stderr', err):
            code = srt_testrun.run_test(config)
        return code, log.call_args.kwargs['result'], out.getvalue(), \
            err.getvalue()

    def test_release_in_result_out(self):
        script = os.path.join(self.dir, 'lab.py')
        with open(script, 'w') as f:
            f.write(
                'import json, os\n'
                'r = json.load(open(os.environ["SRT_RELEASE"]))\n'
                'json.dump({"status": "pass", "summary": f"{r[\'tag\']} '
                '{r[\'old_tag\']} {r[\'upstream\']} {r[\'series\']} '
                '{r[\'workflow\']} {r[\'rc\']}", "url": "http://lab/1", '
                '"jobs": 54}, open(os.environ["SRT_TEST_RESULT"], "w"))\n'
                'open("paths", "w").write(os.environ["SRT_RELEASE"] + "\\n" '
                '+ os.environ["SRT_TEST_RESULT"])\n')
        code, result, out, err = self.run_test(
            f'{sys.executable} {script}')
        self.assertEqual(code, 0)
        self.assertEqual(result, {
            'status': 'pass',
            'summary': 'v6.12.119-rt25 v6.12.118-rt24 v6.12.119 v6.12-rt '
                       'quilt False',
            'url': 'http://lab/1', 'jobs': 54})
        self.assertIn('result: pass - v6.12.119-rt25', out)
        self.assertIn('        http://lab/1\n', out)
        self.assertEqual(err, '')
        # the temporary files are gone
        with open(os.path.join(self.dir, 'paths')) as f:
            for path in f.read().splitlines():
                self.assertFalse(os.path.exists(path), path)

    def test_no_result(self):
        code, result, out, err = self.run_test('exit 2', workflow='git')
        self.assertEqual((code, result, err), (2, None, ''))
        self.assertNotIn('result:', out)

    def test_invalid_result(self):
        for text in ('no json', '[1, 2]'):
            code, result, _, err = self.run_test(
                f"echo '{text}' > \"$SRT_TEST_RESULT\"")
            self.assertEqual((code, result), (0, None))
            self.assertIn('the exit code decides', err)

    def test_status_against_exit_code(self):
        _, result, _, err = self.run_test(
            'echo \'{"status": "fail"}\' > "$SRT_TEST_RESULT"')
        self.assertEqual(result, {'status': 'fail'})
        self.assertIn('the result says fail, the command exited with 0', err)
        code, _, _, err = self.run_test(
            'echo \'{"status": "pass"}\' > "$SRT_TEST_RESULT"; exit 1')
        self.assertEqual(code, 1)
        self.assertIn('the result says pass', err)
        # another status: no opinion about it
        _, _, _, err = self.run_test(
            'echo \'{"status": "flaky"}\' > "$SRT_TEST_RESULT"; exit 1')
        self.assertEqual(err, '')


class TestTestDuration(unittest.TestCase):

    def test_duration(self):
        from stable_rt_tools.srt_testrun import duration
        self.assertEqual(duration(12.7), '12s')
        self.assertEqual(duration(200), '3m20s')
        self.assertEqual(duration(5 * 3600 + 12 * 60 + 5), '5h12m')
