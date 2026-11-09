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
import os
import tempfile
import unittest
from shutil import rmtree
from unittest.mock import patch

from stable_rt_tools import srt_quilt
from stable_rt_tools.srt_prep import worktree_dirs
from stable_rt_tools.srt_quilt import (
    drop_from_series,
    parse_series,
    patch_subject,
    rt_localversion,
    series_changes,
)
from stable_rt_tools.srt_util import SrtState

SERIES = """\
# Applied upstream

###########################################################################
# Posted
###########################################################################
0001-hrtimer-Use-__raise_softirq_irqoff.patch
0002-timers-Use-__raise_softirq_irqoff.patch  -p1

# RT release version
Add_localversion_for_-RT_release.patch
"""


class TestHelpers(unittest.TestCase):
    def test_parse_series(self):
        self.assertEqual(parse_series(SERIES), [
            '0001-hrtimer-Use-__raise_softirq_irqoff.patch',
            '0002-timers-Use-__raise_softirq_irqoff.patch',
            'Add_localversion_for_-RT_release.patch'])

    def test_series_changes(self):
        old = ['a.patch', 'b.patch', 'lv.patch']
        new = ['a.patch', 'c.patch', 'lv.patch']
        self.assertEqual(series_changes(old, new), (['b.patch'],
                                                    ['c.patch']))
        self.assertEqual(series_changes(old, old), ([], []))

    def test_patch_subject(self):
        self.assertEqual(patch_subject(
            'From: A <a@b>\nSubject: [PATCH] printk: Postpone kthread '
            'startup\n\nbody\n'), 'printk: Postpone kthread startup')
        self.assertEqual(patch_subject(
            'Subject: [PATCH v2 1/3] [RT] sched: A very long subject\n'
            ' which is folded\n\n---\n'),
            'sched: A very long subject which is folded')
        self.assertEqual(patch_subject(
            'Subject: no prefix\n'), 'no prefix')
        # quilt patch without mail headers
        self.assertIsNone(patch_subject(
            '--- a/x\n+++ b/x\nSubject: in the diff\n'))

    def test_rt_localversion(self):
        self.assertEqual(rt_localversion('v6.12.116-rt22'), '-rt22')

    def test_drop_from_series(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, 'series'), 'w') as f:
                f.write(SERIES)
            name = '0002-timers-Use-__raise_softirq_irqoff.patch'
            with open(os.path.join(d, name), 'w') as f:
                f.write('patch')
            drop_from_series(d, name)
            with open(os.path.join(d, 'series')) as f:
                text = f.read()
            self.assertNotIn(name, text)
            self.assertIn('# Posted', text)
            self.assertEqual(len(parse_series(text)), 2)
            self.assertFalse(os.path.exists(os.path.join(d, name)))
        finally:
            rmtree(d)

    def test_worktree_dirs_rt_devel_names(self):
        # a series taken over in the shared tree with its branch names
        self.assertEqual(worktree_dirs('/w/linux-6.18.y-rt'), {
            'rt_dir': '/w/linux-6.18.y-rt',
            'stable_dir': '/w/linux-6.18.y',
            'patches_dir': '/w/linux-6.18.y-rt-patches',
            'rebase_dir': '/w/linux-6.18.y-rt-rebase'})

    def test_worktree_dirs_other_suffix(self):
        self.assertEqual(worktree_dirs('/w/v6.1-foo', 'foo'), {
            'rt_dir': '/w/v6.1-foo',
            'stable_dir': '/w/v6.1',
            'patches_dir': '/w/v6.1-foo-patches',
            'rebase_dir': '/w/v6.1-foo-rebase'})

    def test_localversion_inc(self):
        from stable_rt_tools.srt_commit import localversion_inc

        d = tempfile.mkdtemp()
        try:
            for old, new in (('-rt21\n', '-rt22\n'), ('-foo9\n', '-foo10\n')):
                path = os.path.join(d, 'localversion')
                with open(path, 'w') as f:
                    f.write(old)
                localversion_inc(path)
                with open(path) as f:
                    self.assertEqual(f.read(), new)
        finally:
            rmtree(d)

    def test_worktree_dirs(self):
        self.assertEqual(worktree_dirs('/rt/v6.12-rt'), {
            'rt_dir': '/rt/v6.12-rt',
            'stable_dir': '/rt/v6.12',
            'patches_dir': '/rt/v6.12-rt-patches',
            'rebase_dir': '/rt/v6.12-rt-rebase'})


STATE: SrtState = {
    'old_tag': 'v6.12.111-rt21',
    'new_tag': 'v6.12.116-rt22',
    'quilt_patches': '/rt/v6.12-rt-patches/patches',
    'workflow_branch': 'v6.12-rt',
    'quilt_workflow': True,
}


class TestRelease(unittest.TestCase):
    def test_tags(self):
        rel = srt_quilt.Release(STATE.copy())
        self.assertEqual(rel.base, 'v6.12.116')
        self.assertEqual(rel.release_tag, 'v6.12.116-rt22')
        self.assertEqual(rel.rebase_tag, 'v6.12.116-rt22-rebase')
        self.assertEqual(rel.queue_tag, 'v6.12.116-rt22-patches')
        self.assertEqual(rel.old_queue_tag, 'v6.12.111-rt21-patches')

    def test_dirs_from_old_state(self):
        # state written before srt prep recorded the worktrees
        rel = srt_quilt.Release(STATE.copy())
        self.assertEqual(rel.rt_dir, '/rt/v6.12-rt')
        self.assertEqual(rel.stable_dir, '/rt/v6.12')
        self.assertEqual(rel.rebase_dir, '/rt/v6.12-rt-rebase')

    def test_requires_prep(self):
        with self.assertRaises(SystemExit):
            srt_quilt.Release({})

    def test_requires_quilt_workflow(self):
        with self.assertRaises(SystemExit):
            srt_quilt.Release({**STATE, 'quilt_workflow': False})

    def test_rejects_release_candidate(self):
        with self.assertRaises(SystemExit):
            srt_quilt.Release({**STATE, 'new_tag': 'v6.12.116-rt22-rc1'})


class TestQuiltCmd(unittest.TestCase):
    def test_quilt_ignores_quiltrc(self):
        rel = srt_quilt.Release(STATE.copy())
        with patch('stable_rt_tools.srt_quilt.cmd') as c:
            env = srt_quilt._quilt_env(rel)
            srt_quilt._refresh(rel, env)
        args = c.call_args
        self.assertEqual(args.args[0], [
            'quilt', '--quiltrc', '-', 'refresh', '-p', 'ab',
            '--no-index', '--no-timestamps'])
        self.assertEqual(args.kwargs['cwd'], '/rt/v6.12')
        self.assertEqual(args.kwargs['env']['QUILT_PATCHES'],
                         '/rt/v6.12-rt-patches/patches')
        self.assertEqual(args.kwargs['env']['QUILT_DIFF_OPTS'],
                         srt_quilt.QUILT_DIFF_OPTS)

    def test_execute_defaults_to_refresh(self):
        with patch('stable_rt_tools.srt_quilt.Release'), \
                patch.dict(srt_quilt.COMMANDS,
                           {'refresh': unittest.mock.Mock()}) as cmds:
            srt_quilt.execute(argparse.Namespace(quilt_cmd=None))
            cmds['refresh'].assert_called_once()


class TestSetupHelpers(unittest.TestCase):
    def test_repo_name(self):
        from stable_rt_tools.srt_setup import _repo_name
        for url in ('https://git.kernel.org/pub/scm/linux/kernel/git/'
                    'stable/linux.git', 'git@example.com:foo/linux',
                    '/srv/git/linux/'):
            self.assertEqual(_repo_name(url), 'linux', url)


if __name__ == '__main__':
    unittest.main()
