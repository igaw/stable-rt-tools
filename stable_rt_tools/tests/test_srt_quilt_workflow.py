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


"""End to end test of the quilt workflow (see docs/quilt-workflow.rst).

Layout created by setUp, mirroring kernel.org:

  upstream/linux  stable tree, v6.1.1 and later v6.1.2
  rt-repo         stable-rt: v6.1-rt, v6.1-rt-patches and v6.1-rt-rebase
                  with the v6.1.1-rt1 release
  rt/linux        work area clone with the worktrees
  rt/v6.1         tracks stable/master
  rt/v6.1-rt, rt/v6.1-rt-patches, rt/v6.1-rt-rebase

The RT series of v6.1.1-rt1 has three patches: rt-feature.patch,
upstreamed.patch (picked up by stable v6.1.2, so it has to be dropped)
and the localversion patch. The release v6.1.2-rt2 adds new-fix.patch.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from shutil import rmtree
from typing import cast
from unittest import mock

from stable_rt_tools import (
    srt_check,
    srt_inbox,
    srt_log,
    srt_quilt,
    srt_setup,
    srt_status,
)
from stable_rt_tools.srt_announce import announce
from stable_rt_tools.srt_create import create
from stable_rt_tools.srt_prep import prep
from stable_rt_tools.srt_sign import sign
from stable_rt_tools.srt_util import (
    clear_srt_state,
    cmd,
    read_srt_state,
    write_srt_state,
)
from stable_rt_tools.srt_util_context import SrtContext
from stable_rt_tools.tests.inbox import add_mail
from stable_rt_tools.tests.test_srt import (
    gnupg_config,
    kernel_makefile,
    sort_steps,
    stdout_text,
    stub_stdin,
    stub_stdouts,
)

KERNEL_C = ''.join(f'line{i}\n' for i in range(1, 31))


def git(path, *args):
    return cmd(['git', '-C', path] + list(args))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


def replace_line(path, old, new):
    write(path, read(path).replace(old + '\n', new + '\n', 1))


def identity(path):
    git(path, 'config', 'user.name', 'Mighty Eagle')
    git(path, 'config', 'user.email', 'me@incredible.com')


@unittest.skipIf(subprocess.run(['which', 'quilt'],
                                stdout=subprocess.DEVNULL).returncode,
                 'quilt is not installed')
class TestQuiltBase(unittest.TestCase):
    def setup_gpg(self):
        self.gnupghome = tempfile.mkdtemp()
        os.chmod(self.gnupghome, 0o700)
        batch = os.path.join(self.gnupghome, 'gpg.batch')
        write(batch, gnupg_config)
        env = {'GNUPGHOME': self.gnupghome}
        cmd(['gpg', '--batch', '--generate-key', batch], env=env)
        lines = cmd(['gpg', '--list-secret-keys', '--with-colons'], env=env)
        for line in lines.splitlines():
            c = line.split(':')
            if c[0] == 'fpr':
                self.config['GPG_KEY_ID'] = c[-2]
                break
        self.config['GNUPGHOME'] = self.gnupghome

    def setup_stable_repo(self):
        os.makedirs(self.stable_repo)
        git(self.stable_repo, 'init', '--initial-branch=master')
        identity(self.stable_repo)
        write(self.stable_repo + '/version', '6.1.1\n\n')
        write(self.stable_repo + '/Makefile', kernel_makefile('6.1.1'))
        write(self.stable_repo + '/kernel.c', KERNEL_C)
        git(self.stable_repo, 'add', '.')
        git(self.stable_repo, 'commit', '-m', 'Linux 6.1.1')
        git(self.stable_repo, 'tag', '-a', '-m', 'v6.1.1', 'v6.1.1')

    def make_patch(self, repo, name, subject, change):
        """Commit change() and return it as patch in the RT format."""
        change(repo)
        git(repo, 'add', '-A')
        git(repo, 'commit', '-m', subject)
        text = git(repo, 'format-patch', '-1', '--stdout', '--no-signature',
                   '--zero-commit', '--no-numbered')
        self.patches[name] = text.split('\n', 1)[1] + '\n'

    def setup_rt_repo(self):
        repo = self.rt_repo
        git(self.tdir, 'clone', '-q', self.stable_repo, repo)
        identity(repo)
        self.patches: dict[str, str] = {}

        def rt_feature(r):
            replace_line(r + '/kernel.c', 'line3', 'line3\nrt_feature();')

        def upstreamed(r):
            replace_line(r + '/kernel.c', 'line10', 'fixed_line10')

        def localversion(r):
            write(r + '/' + self.localversion, f'-{self.suffix}1\n')

        # -rt: the RT commits on top of stable, tagged v6.1.1-rt1
        git(repo, 'checkout', '-q', '-b', self.series, 'v6.1.1')
        self.make_patch(repo, 'rt-feature.patch', 'rt: Add the feature',
                        rt_feature)
        self.make_patch(repo, 'upstreamed.patch', 'fix: line10 is broken',
                        upstreamed)
        self.make_patch(repo, 'Add_localversion_for_-RT_release.patch',
                        'Add localversion for -RT release', localversion)
        git(repo, 'tag', '-a', '-m', self.old_tag, self.old_tag)

        # -rebase: the same patches as own commits on top of stable, made
        # with git quiltimport normally. Its tag must not be on the -rt
        # commit, git describe would pick either of them.
        git(repo, 'checkout', '-q', '-b', self.series + '-rebase', 'v6.1.1')
        later = dict(os.environ, GIT_COMMITTER_DATE='2030-01-01T00:00:00')
        for name in ('rt-feature.patch', 'upstreamed.patch',
                     'Add_localversion_for_-RT_release.patch'):
            path = os.path.join(self.tdir, name)
            write(path, self.patches[name])
            cmd(['git', '-C', repo, 'am', '-q', path], env=later)
        git(repo, 'tag', '-a', '-m', self.old_tag + '-rebase',
            self.old_tag + '-rebase')
        assert git(repo, 'rev-parse', 'HEAD') != \
            git(repo, 'rev-parse', self.series)
        git(repo, 'checkout', '-q', self.series)

        # -patches: the quilt queue
        git(repo, 'checkout', '-q', '--orphan', self.series + '-patches')
        git(repo, 'rm', '-q', '-rf', '.')
        for name, text in self.patches.items():
            write(repo + '/patches/' + name, text)
        write(repo + '/patches/series',
              '# RT series\n'
              'rt-feature.patch\n'
              'upstreamed.patch\n'
              '\n# RT release version\n'
              'Add_localversion_for_-RT_release.patch\n')
        git(repo, 'add', 'patches')
        git(repo, 'commit', '-q', '-m', '[ANNOUNCE] ' + self.old_tag[1:])
        git(repo, 'tag', '-a', '-m', 'Patch queue for ' + self.old_tag,
            self.old_tag + '-patches')
        git(repo, 'checkout', '-q', 'master')

    def setup_config(self) -> dict[str, str]:
        """The srt.conf group of the series, for srt setup."""
        return dict(self.config,
                    UPSTREAM_GIT_URL=self.stable_repo,
                    UPSTREAM_BRANCH='master',
                    UPSTREAM_REMOTE='stable',
                    PRJ_GIT_URL=self.rt_repo)

    def setup_work_area(self):
        os.mkdir(self.rt)
        with mock.patch('sys.stdout'):
            srt_setup.setup(self.group, self.setup_config(), self.rt)
        identity(self.rt + '/linux')

    def setup_stable_new_release(self):
        replace_line(self.stable_repo + '/kernel.c', 'line10',
                     'fixed_line10')
        git(self.stable_repo, 'commit', '-q', '-am', 'fix: line10 is broken')
        replace_line(self.stable_repo + '/kernel.c', 'line28',
                     'stable_line28')
        write(self.stable_repo + '/version', '6.1.2\n\n')
        git(self.stable_repo, 'commit', '-q', '-am', 'Linux 6.1.2')
        # stable tags are signed: git merge puts the signature into the
        # merge message as comment lines
        cmd(['git', '-C', self.stable_repo, 'tag', '-s',
             '-u', self.config['GPG_KEY_ID'],
             '-m', 'This is the 6.1.2 stable release', 'v6.1.2'],
            env=dict(os.environ, GNUPGHOME=self.gnupghome))

    # the release suffix: tags vX.Y.Z-<suffix>N, series v6.1-<suffix>
    suffix = 'rt'

    def setUp(self):
        self.series = f'v6.1-{self.suffix}'
        self.group = f'linux/stable-rt/{self.series}'
        self.old_tag = f'v6.1.1-{self.suffix}1'
        self.new_tag = f'v6.1.2-{self.suffix}2'
        self.localversion = f'localversion-{self.suffix}'
        self.cwd = tempfile.gettempdir()
        self.tdir = tempfile.mkdtemp()
        self.stable_repo = self.tdir + '/upstream/linux'
        self.rt_repo = self.tdir + '/rt-repo'
        self.rt = self.tdir + '/rt'
        self.stable_dir = self.rt + '/v6.1'
        self.rt_dir = self.rt + '/' + self.series
        self.patches_dir = self.rt + '/' + self.series + '-patches'
        self.rebase_dir = self.rt + '/' + self.series + '-rebase'
        self.config = {
            'WORKFLOW': 'quilt',
            'LOCALVERSION': self.localversion,
            'SUFFIX': self.suffix,
            'PRJ_GIT_TREE': self.rt_repo,
            'PRJ_DIR': '/pub/linux/kernel/projects/rt/6.1',
            'MAIL_TO': 'Foo Bar <foo@bar.barf>',
            'SENDER': 'Mighty Eagle <me@incredible.com>',
            'NAME': 'Mighty Eagle',
        }
        self.setup_gpg()
        self.setup_stable_repo()
        self.setup_rt_repo()
        self.setup_work_area()
        self.setup_stable_new_release()

        for module in ('srt_quilt', 'srt_check', 'srt_status'):
            patcher = mock.patch(f'stable_rt_tools.{module}.get_config',
                                 return_value=self.config)
            patcher.start()
            self.addCleanup(patcher.stop)
        # kup ls needs kernel.org: unknown, unless a test says otherwise
        self.kup_ls = mock.patch(
            'stable_rt_tools.srt_status.kup_ls',
            return_value=(None, 'kup is not installed')).start()
        self.addCleanup(mock.patch.stopall)
        env = mock.patch.dict(os.environ, {'GIT_EDITOR': 'true'})
        env.start()
        self.addCleanup(env.stop)
        os.chdir(self.rt_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        rmtree(self.tdir)
        rmtree(self.gnupghome)

    def run_step(self, step, answers='y\ny\n'):
        stub_stdin(self, answers)
        stub_stdouts(self)
        srt_quilt.COMMANDS[step](srt_quilt.Release())
        return stdout_text()

    def run_setup(self, config, group=None, parent=None, source_branch=None,
                  source_url=None):
        stub_stdouts(self)
        srt_setup.setup(group or self.group, config, parent or self.rt,
                        source_branch, source_url)
        return stdout_text()

    def add_new_patch(self):
        """Add new-fix.patch to the series, as done by hand."""
        tmp = self.tdir + '/new-fix'
        git(self.tdir, 'clone', '-q', self.stable_repo, tmp)
        identity(tmp)
        git(tmp, 'checkout', '-q', 'v6.1.2')
        self.make_patch(tmp, 'new-fix.patch', 'rt: Fix line15',
                        lambda r: replace_line(r + '/kernel.c', 'line15',
                                               'rt_line15'))
        write(self.patches_dir + '/patches/new-fix.patch',
              self.patches['new-fix.patch'])
        series = self.patches_dir + '/patches/series'
        write(series, read(series).replace(
            'upstreamed.patch\n', 'upstreamed.patch\nnew-fix.patch\n'))

    def prepare(self):
        stub_stdouts(self)
        prep(self.config)

    def kup_names(self, tag=None):
        """What kup ls lists in PRJ_DIR/older after srt upload of tag."""
        v = (tag or self.new_tag)[1:]
        return {f'patch-{v}.patch.xz', f'patch-{v}.patch.sign',
                f'patches-{v}.tar.xz', f'patches-{v}.tar.sign'}

    def release_until(self, last):
        self.prepare()
        self.add_new_patch()
        for step in srt_quilt.STEPS:
            self.run_step(step)
            if step == last:
                return


class TestQuiltRelease(TestQuiltBase):
    def step1_prep(self):
        self.prepare()
        state = read_srt_state()
        assert state is not None
        self.assertEqual(state['old_tag'], self.old_tag)
        self.assertEqual(state['new_tag'], self.new_tag)
        self.assertEqual(state['patches_dir'], self.patches_dir)
        # srt prep pulled the stable worktree
        self.assertEqual(git(self.stable_dir, 'describe'), 'v6.1.2')

    def step2_refresh(self):
        self.add_new_patch()
        out = self.run_step('refresh', 'y\n')
        self.assertIn('upstreamed.patch is already in v6.1.2', out)
        self.assertIn('dropped: upstreamed.patch', out)
        self.assertIn('added:   new-fix.patch', out)
        patches = self.patches_dir + '/patches/'
        self.assertNotIn('upstreamed', read(patches + 'series'))
        self.assertFalse(os.path.exists(patches + 'upstreamed.patch'))
        lv = read(patches + 'Add_localversion_for_-RT_release.patch')
        self.assertIn(f'+-{self.suffix}2', lv)
        # the RT series format is kept
        self.assertIn('--- a/kernel.c', read(patches + 'rt-feature.patch'))
        self.assertNotIn('Index:', read(patches + 'rt-feature.patch'))
        # the stable tree is left clean
        self.assertEqual(git(self.stable_dir, 'status', '--porcelain',
                             '--untracked-files=no'), '')

    def step3_queue(self):
        self.run_step('queue')
        msg = git(self.patches_dir, 'log', '-1', '--format=%B')
        self.assertTrue(msg.startswith('[ANNOUNCE] ' + self.new_tag[1:]))
        self.assertIn('dropped upstreamed.patch', msg)
        self.assertIn('added new-fix.patch', msg)
        self.assertIn('linux-stable-rt.git ' + self.new_tag, msg)
        self.assertEqual(git(self.patches_dir, 'status', '--porcelain'), '')
        self.assertTrue(srt_quilt.Release().done('queue'))

    def step4_rebase(self):
        self.run_step('rebase')
        log = git(self.rebase_dir, 'log', '--format=%s', 'v6.1.2..HEAD')
        self.assertEqual(log.splitlines(), [
            'Add localversion for -RT release', 'rt: Fix line15',
            'rt: Add the feature'])
        self.assertTrue(srt_quilt.Release().done('rebase'))

    def step5_merge(self):
        out = self.run_step('merge')
        self.assertIn('apply new-fix.patch', out)
        log = git(self.rt_dir, 'log', '--first-parent', '--format=%s',
                  self.old_tag + '..HEAD')
        self.assertEqual(log.splitlines(), [
            'rt: Fix line15', f"Merge tag 'v6.1.2' into {self.series}"])
        body = git(self.rt_dir, 'log', '-1', '--format=%b')
        self.assertIn('Signed-off-by: Mighty Eagle', body)
        # like linux-6.18.y-rt: the tag message and a sign-off, no
        # signature lines of the stable tag
        merge = git(self.rt_dir, 'log', '-1', '--format=%B', 'HEAD^')
        self.assertEqual(merge.strip(),
                         f"Merge tag 'v6.1.2' into {self.series}\n\n"
                         'This is the 6.1.2 stable release\n\n'
                         'Signed-off-by: Mighty Eagle <me@incredible.com>')

    def step6_release(self):
        out = self.run_step('release')
        self.assertIn('next: test the release, then srt create', out)
        self.assertEqual(git(self.rt_dir, 'log', '-1', '--format=%s'),
                         self.new_tag)
        self.assertEqual(read(f'{self.rt_dir}/{self.localversion}'),
                         f'-{self.suffix}2\n')
        self.assertEqual(
            git(self.rt_dir, 'diff', f'{self.new_tag}-rebase'), '')
        for t in (self.new_tag, f'{self.new_tag}-rebase',
                  f'{self.new_tag}-patches'):
            cmd(['git', 'tag', '-v', t],
                env=dict(os.environ, GNUPGHOME=self.gnupghome))

    def step7_status(self):
        stub_stdouts(self)
        srt_status.status()
        out = stdout_text()
        self.assertIn(f'{self.old_tag} -> {self.new_tag}', out)
        for step in srt_quilt.STEPS:
            self.assertIn(f'  [x] srt quilt {step}\n', out)
        self.assertIn('  [ ] srt create\n  [ ] srt sign\n', out)
        self.assertIn('next: test the release, then srt create', out)
        self.assertNotIn('warning', out)

    def step8_create_sign(self):
        ctx = SrtContext(None, path=self.rt_dir)
        stub_stdouts(self)
        create(self.config, ctx)
        sign(self.config, ctx)
        out = stdout_text()
        self.assertIn('next: srt sign', out)
        self.assertIn('.tar.sign\nnext: srt upload', out)
        info = srt_status.status_info()
        steps = cast(list[dict[str, bool]], info['steps'])
        # kup can't tell whether it is uploaded
        self.assertEqual([s['done'] for s in steps],
                         [True] * 7 + [None, False, False])
        self.assertEqual(steps[7], {'step': 'srt upload', 'done': None,
                                    'unknown': 'kup is not installed'})
        self.assertEqual(info['next'], 'srt upload (unless done already)')
        self.kup_ls.return_value = (self.kup_names(), '')
        info = srt_status.status_info()
        self.kup_ls.assert_called_with(self.config['PRJ_DIR'] + '/older')
        self.assertEqual([s['done'] for s in
                          cast(list[dict[str, bool]], info['steps'])],
                         [True] * 8 + [False, False])
        self.assertEqual(info['next'], 'srt push')
        # offline, kup isn't asked
        self.kup_ls.reset_mock()
        info = srt_status.status_info(offline=True)
        self.kup_ls.assert_not_called()
        self.assertEqual(cast(list[dict[str, object]], info['steps'])[7],
                         {'step': 'srt upload', 'done': None,
                          'unknown': 'offline'})
        d = self.rt_dir + '/patches/' + self.new_tag + '/'
        v = self.new_tag[1:]
        for f in (f'patch-{v}.patch.xz', f'patches-{v}.tar.xz',
                  f'patch-{v}.patch.sign', f'patches-{v}.tar.sign'):
            self.assertTrue(os.path.isfile(d + f), f)
        # like linux-6.18.y-rt: the tarball is the queue of the -patches
        # tag, with its series file and patch names
        tar = cmd(['tar', '-tJf', d + f'patches-{v}.tar.xz'])
        queue = git(self.rt_dir, 'ls-tree', '-r', '--name-only',
                    f'{self.new_tag}-patches', 'patches')
        self.assertEqual(sorted(n for n in tar.splitlines()
                                if not n.endswith('/')),
                         sorted(queue.splitlines()))
        self.assertEqual(read(d + 'patches/series'),
                         git(self.rt_dir, 'show',
                             f'{self.new_tag}-patches:patches/series')
                         + '\n')

    def step8b_check(self):
        checks = {c.name: c for c in srt_check.run_checks()}
        self.assertEqual(
            {n: c.result for n, c in checks.items()},
            {'upstream': 'skip', 'queue': 'warn', 'rebase': 'ok',
             'merge': 'ok', 'release': 'ok', 'delta': 'ok', 'files': 'ok',
             'signatures': 'ok'})
        # the patches added and dropped need a review, the refreshed ones
        # only changed their hunk offsets
        self.assertEqual(checks['queue'].details,
                         ['dropped upstreamed.patch', 'added new-fix.patch'])
        self.assertIn('0 changed beyond hunk offsets', checks['queue'].text)

    def step8c_check_without_state(self):
        # like after srt push, which clears the state: the release is
        # found in the history, or given as OLD_TAG NEW_TAG
        with_state = {n: c.result for n, c in
                      self.checks_of(path=self.rt_dir).items()}
        clear_srt_state(self.rt_dir)
        self.assertEqual({n: c.result for n, c in
                          self.checks_of(path=self.rt_dir).items()},
                         with_state)
        tags = Namespace(OLD_TAG=self.old_tag, NEW_TAG=self.new_tag)
        self.assertEqual({n: c.result for n, c in
                          self.checks_of(tags, self.rt_dir).items()},
                         with_state)

    @staticmethod
    def checks_of(args=None, path=None):
        return {c.name: c for c in srt_check.run_checks(args, path)}

    def step9_announce(self):
        ctx = SrtContext(None, path=self.rt_dir)
        stub_stdouts(self)
        announce(self.config, ctx, Namespace(suppress_cc=False))
        out = stdout_text()
        headers, _, body = out.partition('\n\n')
        self.assertIn(f'Subject: [ANNOUNCE] {self.new_tag[1:]}\n', headers)
        self.assertIn('Message-ID: <', headers)
        self.assertIn('To: Foo Bar <foo@bar.barf>', headers)
        # the announcement of the queue commit, without its trailers
        self.assertIn(f'\nChanges from {self.old_tag}:\n---\n', body)
        text, _, changes = body.partition('\n---\n')
        self.assertIn('added new-fix.patch', text)
        self.assertIn(f'The delta patch against {self.old_tag[1:]} is '
                      'appended below', text)
        self.assertNotIn('Signed-off-by', text)
        # the series' own commits and delta, not the stable update
        self.assertIn('rt: Fix line15', changes)
        self.assertIn(f"Merge tag 'v6.1.2' into {self.series}", changes)
        self.assertNotIn('Linux 6.1.2', changes)
        self.assertIn('+rt_line15\n', changes)
        self.assertIn(f'+-{self.suffix}2\n', changes)
        self.assertNotIn('stable_line28', changes)

    def step10_log(self):
        events = srt_log.read_log(self.rt_dir)
        # srt announce only printed the mail: not in the log
        self.assertEqual([e['step'] for e in events], [
            'prep', 'quilt refresh', 'quilt queue', 'quilt rebase',
            'quilt merge', 'quilt release', 'create', 'sign'])
        for e in events:
            self.assertEqual(e['series'], self.series)
            self.assertEqual(e['release'], self.new_tag)
            self.assertEqual(e['old'], self.old_tag)
            self.assertEqual(e['user'], 'Mighty Eagle')
            self.assertTrue(e['time'].endswith('+00:00'))
        steps = {e['step']: e for e in events}
        self.assertEqual(steps['prep']['upstream'], 'v6.1.2')
        self.assertEqual(steps['quilt refresh']['dropped'],
                         ['upstreamed.patch'])
        self.assertEqual(steps['quilt refresh']['added'], ['new-fix.patch'])
        for step, tag, path in (
                ('quilt queue', f'{self.new_tag}-patches', self.patches_dir),
                ('quilt rebase', f'{self.new_tag}-rebase', self.rebase_dir),
                ('quilt release', self.new_tag, self.rt_dir)):
            self.assertEqual(steps[step]['tag'], tag)
            self.assertEqual(steps[step]['commit'],
                             git(path, 'rev-parse', tag + '^{commit}'))
        self.assertEqual(steps['quilt merge']['merged'], 'v6.1.2')
        self.assertEqual(steps['quilt merge']['applied'], ['new-fix.patch'])
        v = self.new_tag[1:]
        self.assertEqual(steps['sign']['files'],
                         [f'patch-{v}.patch.sign', f'patches-{v}.tar.sign'])
        # one log for all worktrees of the series, next to the state
        log = srt_log.get_log_path(self.patches_dir)
        self.assertEqual(log, srt_log.get_log_path(self.rt_dir))
        self.assertEqual(log, os.path.join(
            git(self.rt_dir, 'rev-parse', '--path-format=absolute',
                '--git-common-dir'), 'srt', self.series + '.log'))

        stub_stdouts(self)
        srt_log.show_log(2)
        lines = stdout_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn(f'create         {self.new_tag} (from {self.old_tag})',
                      lines[0])
        self.assertIn(f'files=patch-{v}.patch.sign,patches-{v}.tar.sign',
                      lines[1])
        self.assertTrue(lines[1].endswith('by Mighty Eagle'))

    def test_release(self):
        for step in sort_steps(dir(self)):
            getattr(self, step)()


class TestQuiltReleaseOtherSuffix(TestQuiltRelease):
    """The same release for a series which is not -rt."""

    suffix = 'foo'


class TestSetup(TestQuiltBase):
    def test_rerun_checks(self):
        out = self.run_setup(self.setup_config())
        self.assertNotIn('add ', out)
        for d in (self.stable_dir, self.rt_dir, self.patches_dir,
                  self.rebase_dir):
            self.assertIn(f'ok    {d} ', out)

    def test_wrong_remote_url(self):
        config = dict(self.setup_config(), PRJ_GIT_URL='/elsewhere')
        with self.assertRaises(srt_setup.SetupError) as e:
            self.run_setup(config)
        self.assertIn('remote stable-rt is', str(e.exception))

    def test_origin_must_match_the_group(self):
        with self.assertRaises(srt_setup.SetupError) as e:
            self.run_setup(self.setup_config(),
                           group=f'other/stable-rt/{self.series}')
        self.assertIn('does not match the repository name other',
                      str(e.exception))

    def test_git_workflow(self):
        config = self.setup_config()
        config['WORKFLOW'] = 'git'
        parent = self.tdir + '/git-workflow'
        os.mkdir(parent)
        self.run_setup(config, parent=parent)
        # no stable and -patches worktrees, -rebase exists on the remote
        self.assertEqual(sorted(os.listdir(parent)),
                         sorted(['linux', self.series,
                                 f'{self.series}-rebase']))
        self.assertEqual(
            git(f'{parent}/{self.series}', 'rev-parse', '--abbrev-ref',
                '--symbolic-full-name', '@{u}'),
            f'stable-rt/{self.series}')


class TestFromBranch(TestQuiltBase):
    """Start v6.2-rt from linux-6.2.y-rt of another maintainer, next to
    the existing v6.1-rt work area."""

    def setUp(self):
        super().setUp()
        git(self.stable_repo, 'branch', 'linux-6.2.y', 'v6.1.1')
        for b in ('', '-patches', '-rebase'):
            git(self.rt_repo, 'branch', f'linux-6.2.y-rt{b}',
                f'{self.series}{b}')
        # a release of the other maintainer, to be published along
        git(self.rt_repo, 'tag', '-a', '-m', 'v6.2.0-rt1', 'v6.2.0-rt1',
            'linux-6.2.y-rt')
        self.config_v62 = dict(self.setup_config(),
                               UPSTREAM_BRANCH='linux-6.2.y')
        self.series_v62 = 'v6.2-rt'

    def publish(self, out):
        for line in out.splitlines():
            if line.startswith('  git -C '):
                cmd(line.split())

    def test_from_the_same_remote(self):
        out = self.run_setup(self.config_v62,
                             group='linux/stable-rt/v6.2-rt',
                             source_branch='linux-6.2.y-rt')
        for b in ('', '-patches', '-rebase'):
            path = f'{self.rt}/v6.2-rt{b}'
            self.assertIn(f'new   {path} (v6.2-rt{b} from '
                          f'stable-rt/linux-6.2.y-rt{b})', out)
            self.assertEqual(git(path, 'rev-parse', 'HEAD'),
                             git(self.rt_repo, 'rev-parse',
                                 f'linux-6.2.y-rt{b}'))
        self.assertIn(f'ok    {self.rt}/linux ', out)
        self.assertIn(f'add   worktree {self.rt}/v6.2 (linux-6.2.y', out)
        self.assertIn('srt setup pushes nothing', out)
        self.assertNotIn('v6.2-rt', git(self.rt_repo, 'branch'))

        # rerun before publishing, --from is not needed anymore
        out = self.run_setup(self.config_v62,
                             group='linux/stable-rt/v6.2-rt')
        self.assertIn(f'ok    {self.rt}/v6.2-rt-patches (v6.2-rt-patches, '
                      'not published yet)', out)

        # publish as told, then the series is set up like any other
        self.publish(out)
        out = self.run_setup(self.config_v62,
                             group='linux/stable-rt/v6.2-rt')
        self.assertIn(f'ok    {self.rt}/v6.2-rt (v6.2-rt tracking '
                      'stable-rt/v6.2-rt)', out)
        self.assertNotIn('publish', out)
        self.assertIn('v6.2.0-rt1', git(self.rt_repo, 'tag'))
        # the existing series is untouched
        self.assertIn(f'ok    {self.rt_dir} ', self.run_setup(
            self.setup_config()))

    def test_from_another_remote(self):
        out = self.run_setup(self.config_v62, group='linux/stable-rt/v6.2-rt',
                             source_branch='rt-devel/linux-6.2.y-rt',
                             source_url=self.rt_repo)
        self.assertIn(f'add   remote rt-devel {self.rt_repo}', out)
        self.assertIn('from rt-devel/linux-6.2.y-rt-rebase)', out)

    def test_missing_series_without_from(self):
        with self.assertRaises(srt_setup.SetupError) as e:
            self.run_setup(self.config_v62, group='linux/stable-rt/v6.2-rt')
        self.assertIn('use --from BRANCH', str(e.exception))

    def srt_setup_cli(self, *argv):
        """Run 'srt setup' with its own srt.conf in self.tdir/conf."""
        from stable_rt_tools import srt

        env = {'SRT_CONF': self.tdir + '/conf', 'HOME': self.tdir}
        os.makedirs(env['SRT_CONF'], exist_ok=True)
        stub_stdouts(self)
        with mock.patch.dict(os.environ, env), \
                mock.patch('sys.argv', ['srt', 'setup', *argv]):
            srt.main()
        return stdout_text()

    def test_cli_from_in_existing_area(self):
        conf = self.tdir + '/conf/srt.conf'
        os.makedirs(self.tdir + '/conf')
        write(conf, '# my srt.conf\n[DEFAULT]\nMAIL_TO = a@b\n')
        out = self.srt_setup_cli(
            'linux/stable-rt/v6.2-rt', '--dir', self.rt,
            '--workflow', 'quilt', '--upstream-branch', 'linux-6.2.y',
            '--upstream-remote', 'stable', '--from', 'linux-6.2.y-rt')
        self.assertIn('added [linux/stable-rt/v6.2-rt]', out)
        self.assertIn(f'new   {self.rt}/v6.2-rt ', out)
        text = read(conf)
        self.assertTrue(text.startswith('# my srt.conf\n[DEFAULT]\n'))
        # the URLs come from the work area, --from is not stored
        self.assertIn(f'PRJ_GIT_URL = {self.rt_repo}', text)
        self.assertIn(f'UPSTREAM_GIT_URL = {self.stable_repo}', text)
        self.assertIn('WORKFLOW = quilt', text)
        self.assertNotIn('linux-6.2.y-rt', text)
        # a valid configuration, used by the next run without options
        out = self.srt_setup_cli('linux/stable-rt/v6.2-rt', '--dir', self.rt)
        self.assertIn('not published yet', out)
        self.assertNotIn('added', out)
        self.assertEqual(read(conf).count('[linux/stable-rt/v6.2-rt]'), 1)

    def test_cli_new_group_needs_settings(self):
        with self.assertRaises(SystemExit) as e:
            self.srt_setup_cli('linux/stable-rt/v6.2-rt', '--dir',
                               self.tdir + '/new')
        self.assertIn('--upstream-url', str(e.exception))

    def test_cli_options_differ_from_config(self):
        conf = self.tdir + '/conf/srt.conf'
        os.makedirs(self.tdir + '/conf')
        write(conf, '[linux/stable-rt/v6.2-rt]\nWORKFLOW = quilt\n'
              'UPSTREAM_BRANCH = linux-6.2.y\nUPSTREAM_REMOTE = stable\n')
        self.srt_setup_cli('linux/stable-rt/v6.2-rt', '--dir', self.rt,
                           '--from', 'linux-6.2.y-rt', '--prj-dir', '/x')
        # the StringIO stub_stdouts() installed
        err = cast(io.StringIO, sys.stderr).getvalue()
        self.assertIn('PRJ_DIR = /x differs from srt.conf', err)
        self.assertNotIn('PRJ_DIR', read(conf))


class TestQuiltChecks(TestQuiltBase):
    def test_steps_in_order(self):
        self.prepare()
        for step in ('queue', 'rebase', 'merge', 'release'):
            with self.assertRaises(SystemExit):
                self.run_step(step)

    def test_release_refuses_tree_mismatch(self):
        self.release_until('merge')
        replace_line(self.rt_dir + '/kernel.c', 'line20', 'unexpected')
        git(self.rt_dir, 'commit', '-q', '-am', 'stray change')
        with self.assertRaises(SystemExit) as e:
            self.run_step('release')
        self.assertIn(f'differs from {self.new_tag}-rebase',
                      str(e.exception))
        self.assertIsNone(
            srt_quilt.rev(self.rt_dir, f'refs/tags/{self.new_tag}'))
        # a fixup commit makes the trees match again
        replace_line(self.rt_dir + '/kernel.c', 'unexpected', 'line20')
        git(self.rt_dir, 'commit', '-q', '-am', 'fixup the stable merge')
        self.run_step('release')
        self.assertTrue(srt_quilt.Release().done('release'))

    def test_steps_are_idempotent(self):
        self.release_until('release')
        head = git(self.rt_dir, 'rev-parse', 'HEAD')
        for step in ('queue', 'rebase', 'merge', 'release'):
            self.run_step(step, '')
        self.assertEqual(git(self.rt_dir, 'rev-parse', 'HEAD'), head)
        with self.assertRaises(SystemExit):
            self.run_step('refresh')
        # the reruns changed nothing, the log has each step once
        self.assertEqual([e['step'] for e in srt_log.read_log()],
                         ['prep'] + [f'quilt {s}' for s in srt_quilt.STEPS])

    def test_log_failure_does_not_fail_the_step(self):
        os.makedirs(srt_log.get_log_path() or '')
        self.prepare()
        state = read_srt_state()
        assert state is not None
        self.assertEqual(state['new_tag'], self.new_tag)
        self.assertIn('srt: warning: srt prep is not in the log',
                      cast(io.StringIO, sys.stderr).getvalue())

    def test_queue_refuses_changes_after_commit(self):
        self.release_until('refresh')
        with self.assertRaises(SystemExit):
            self.run_step('queue', 'n\n')  # commit, but don't tag
        series = self.patches_dir + '/patches/series'
        write(series, read(series) + '# a late change\n')
        with self.assertRaises(SystemExit) as e:
            self.run_step('queue')
        self.assertIn('git reset --soft HEAD~1', str(e.exception))
        self.assertFalse(srt_quilt.Release().done('queue'))
        # undoing the commit picks up the change
        git(self.patches_dir, 'reset', '-q', '--soft', 'HEAD~1')
        self.run_step('queue')
        self.assertIn('# a late change', git(
            self.patches_dir, 'show',
            f'{self.new_tag}-patches:patches/series'))

    def test_queue_draft_and_file(self):
        self.release_until('refresh')
        head = git(self.patches_dir, 'rev-parse', 'HEAD')
        stub_stdouts(self)
        srt_quilt.queue(srt_quilt.Release(), draft=True)
        draft = stdout_text()
        self.assertTrue(draft.startswith('[ANNOUNCE] ' + self.new_tag[1:]))
        self.assertIn('added new-fix.patch', draft)
        self.assertEqual(git(self.patches_dir, 'rev-parse', 'HEAD'), head)
        # the completed announcement is committed as it is, no editor
        msg = self.tdir + '/announce.txt'
        write(msg, draft.replace('Changes since',
                                 'A fix for line15.\n\nChanges since'))
        stub_stdin(self, 'y\n')
        stub_stdouts(self)
        with mock.patch.dict(os.environ, {'GIT_EDITOR': 'false'}):
            srt_quilt.queue(srt_quilt.Release(), message_file=msg)
        body = git(self.patches_dir, 'log', '-1', '--format=%B')
        self.assertTrue(body.startswith(read(msg).rstrip('\n')))
        self.assertIn('A fix for line15.', body)
        self.assertTrue(srt_quilt.Release().done('queue'))

    def test_queue_no_edit(self):
        self.release_until('refresh')
        stub_stdin(self, 'y\n')
        stub_stdouts(self)
        with mock.patch.dict(os.environ, {'GIT_EDITOR': 'false'}):
            srt_quilt.queue(srt_quilt.Release(), edit=False)
        self.assertIn('added new-fix.patch', git(
            self.patches_dir, 'log', '-1', '--format=%B'))

    def status_json(self):
        stub_stdouts(self)
        srt_status.status(as_json=True)
        return json.loads(stdout_text())

    def fake_fetch(self, ref, tag, parent):
        """Let the remote-tracking branch ref point to a new commit on
        parent, tagged tag, as if it was fetched."""
        linux = self.rt + '/linux'
        tree = git(linux, 'rev-parse', parent + '^{tree}')
        commit = git(linux, 'commit-tree', '-p', parent, '-m', tag, tree)
        git(linux, 'tag', '-a', '-m', tag, tag, commit)
        git(linux, 'update-ref', ref, commit)

    def test_status_json(self):
        self.prepare()
        info = self.status_json()
        self.assertEqual(info['old_tag'], self.old_tag)
        self.assertEqual(info['new_tag'], self.new_tag)
        self.assertEqual(info['workflow'], 'quilt')
        self.assertEqual(info['steps'][0],
                         {'step': 'srt quilt refresh', 'done': False})
        self.assertEqual(info['next'], 'srt quilt refresh')
        self.assertEqual(info['warnings'], [])

    def assert_status_without_state(self):
        """srt status finds the same in the trees as with the state."""
        with_state = srt_status.status_info()
        self.assertEqual(with_state['source'], 'state')
        state = read_srt_state()
        assert state is not None
        clear_srt_state()
        try:
            without = srt_status.status_info()
        finally:
            write_srt_state(state)
        self.assertEqual(without['source'], 'trees')
        for key in ('prepared', 'workflow', 'old_tag', 'new_tag', 'dropped',
                    'added', 'steps', 'warnings', 'next'):
            self.assertEqual(without[key], with_state[key], key)
        return without

    def test_status_without_state(self):
        self.prepare()
        self.add_new_patch()
        for step in srt_quilt.STEPS:
            self.run_step(step)
            info = self.assert_status_without_state()
            self.assertTrue(info['prepared'])
            self.assertEqual(info['new_tag'], self.new_tag)
        ctx = SrtContext(None, path=self.rt_dir)
        stub_stdouts(self)
        create(self.config, ctx)
        sign(self.config, ctx)
        self.assert_status_without_state()
        self.kup_ls.return_value = (self.kup_names(), '')
        info = self.assert_status_without_state()
        self.assertEqual(info['next'], 'srt push')
        # from the other worktrees of the series too
        os.chdir(self.patches_dir)
        clear_srt_state()
        self.assertEqual(srt_status.status_info(), info)

        # srt push pushes and clears the state, the fetch shows it
        git(self.rt_dir, 'push', '-q', 'stable-rt', 'HEAD:' + self.series)
        git(self.rt_dir, 'fetch', '-q', 'stable-rt')
        info = self.status_json()
        self.assertTrue(info['prepared'])
        self.assertEqual(info['new_tag'], self.new_tag)
        self.assertEqual([s['done'] for s in info['steps']],
                         [True] * 9 + [None])
        self.assertEqual(info['steps'][-2], {'step': 'srt push',
                                             'done': True})
        # the archive of the mailing list isn't reachable
        self.assertEqual(info['steps'][-1],
                         {'step': 'srt announce', 'done': None,
                          'unknown': 'no network in the tests'})
        self.assertEqual(info['warnings'], [])
        self.assertEqual(info['next'], 'srt announce (unless done already)')
        # an inbox without the announcement
        inbox = self.tdir + '/inbox'
        add_mail(inbox, f'Re: [ANNOUNCE] {self.new_tag}', '<re@x>')
        self.config['INBOX'] = inbox
        info = self.status_json()
        self.assertTrue(info['prepared'])
        self.assertEqual(info['steps'][-1],
                         {'step': 'srt announce', 'done': False})
        self.assertEqual(info['next'], 'srt announce')
        # announced, the next fetch shows it
        add_mail(inbox, f'[ANNOUNCE] {self.new_tag}', '<a@x>')
        stamp = srt_inbox.stamp_path(srt_inbox.clone_dir(inbox))
        os.utime(stamp, (0, 0))
        info = self.status_json()
        self.assertFalse(info['prepared'])
        self.assertEqual([s['done'] for s in info['steps']], [True] * 10)
        self.assertEqual(info['steps'][-1]['mail']['message_id'], '<a@x>')
        self.assertEqual(info['warnings'], [])
        self.assertEqual(info['next'],
                         'srt prep, once upstream has a release after '
                         'v6.1.2')
        self.assertEqual(srt_log.read_log()[-1]['step'], 'announced')
        stub_stdouts(self)
        srt_status.status()
        out = stdout_text()
        self.assertIn('No release in progress, the last one:\n'
                      f'{self.old_tag} -> {self.new_tag}\n', out)
        self.assertIn('  [x] srt push\n  [x] srt announce\n'
                      '      2026-11-21T13:57:47+01:00 Mighty Eagle '
                      '<me@incredible.com>\n      <a@x>\n', out)
        # a newer upstream release is fetched
        self.fake_fetch('refs/remotes/stable/master', 'v6.1.3', 'v6.1.2^{}')
        self.assertEqual(self.status_json()['next'], 'srt prep')

    def test_status_refresh_from_the_queue(self):
        """The refresh is done when the localversion patch of the queue
        has the localversion of the release."""
        self.prepare()
        self.add_new_patch()
        clear_srt_state()
        self.assertFalse(self.status_json()['prepared'])
        self.prepare()
        self.run_step('refresh')
        clear_srt_state()
        info = self.status_json()
        self.assertTrue(info['prepared'])
        self.assertEqual((info['old_tag'], info['new_tag']),
                         (self.old_tag, self.new_tag))
        self.assertEqual(info['steps'][0],
                         {'step': 'srt quilt refresh', 'done': True})
        self.assertEqual(info['next'], 'srt quilt queue')

    def test_status_after_undo(self):
        self.release_until('release')
        self.run_step('undo')
        # the state says the kept patches need a refresh again
        info = self.status_json()
        self.assertEqual([s['done'] for s in info['steps'][:5]],
                         [False] * 5)
        self.assertEqual(info['next'], 'srt quilt refresh')

    def test_status_without_release(self):
        stub_stdouts(self)
        srt_status.status(as_json=True)
        self.assertFalse(json.loads(stdout_text())['prepared'])

    def test_status_release_published_elsewhere(self):
        self.release_until('release')
        # e.g. another maintainer pushed the release, and it was fetched
        git(self.rt + '/linux', 'update-ref',
            f'refs/remotes/stable-rt/{self.series}', self.new_tag + '^{}')
        info = self.status_json()
        self.assertIn(f'{self.new_tag} is published already',
                      info['warnings'][0])
        self.assertEqual(info['next'], 'srt prep --clear, then srt prep')

    def test_status_newer_release_upstream(self):
        self.prepare()
        self.fake_fetch(f'refs/remotes/stable-rt/{self.series}',
                        f'v6.1.1-{self.suffix}5', self.old_tag + '^{}')
        info = self.status_json()
        self.assertIn(f'stable-rt/{self.series} is at '
                      f'v6.1.1-{self.suffix}5', info['warnings'][0])
        stub_stdouts(self)
        srt_status.status()
        self.assertIn('warning: stable-rt/', stdout_text())

    def test_status_newer_upstream_release(self):
        self.prepare()
        self.fake_fetch('refs/remotes/stable/master', 'v6.1.3', 'v6.1.2^{}')
        info = self.status_json()
        self.assertEqual(info['warnings'],
                         ['upstream is at v6.1.3, the release was prepared '
                          'for v6.1.2: run "srt prep" again'])
        # once the queue is refreshed, the release goes on as prepared
        self.run_step('refresh')
        self.assertEqual(self.status_json()['warnings'], [])

    def checks(self):
        return {c.name: c for c in srt_check.run_checks()}

    def test_check_before_refresh(self):
        self.prepare()
        checks = self.checks()
        self.assertEqual(checks['upstream'].result, 'ok')
        self.assertEqual(
            [c.result for n, c in checks.items() if n != 'upstream'],
            ['skip'] * 7)

    def test_check_patch_changed(self):
        self.release_until('refresh')
        patch = self.patches_dir + '/patches/rt-feature.patch'
        write(patch, read(patch).replace('+rt_feature();',
                                         '+rt_feature(1);'))
        queue = self.checks()['queue']
        self.assertEqual(queue.result, 'warn')
        self.assertIn('changed rt-feature.patch', queue.details)
        self.assertIn(f'diff {self.old_tag}-patches -- '
                      'patches/rt-feature.patch', queue.text)

    def test_check_merge_message(self):
        self.release_until('merge')
        # the message as srt 2.1 committed it
        msg = git(self.rt_dir, 'log', '-1', '--format=%B', 'HEAD^')
        git(self.rt_dir, 'reset', '-q', '--hard', 'HEAD^')
        git(self.rt_dir, 'commit', '-q', '--amend', '--cleanup=verbatim',
            '-m', msg + '\n# -----BEGIN PGP SIGNATURE-----')
        self.run_step('merge')
        self.assertEqual(self.checks()['merge'].result, 'warn')

    def test_check_files(self):
        self.release_until('release')
        ctx = SrtContext(None, path=self.rt_dir)
        stub_stdouts(self)
        create(self.config, ctx)
        sign(self.config, ctx)
        self.assertEqual(self.checks()['files'].result, 'ok')
        # a file of another release
        patch = self.rt_dir + f'/patches/{self.new_tag}/' \
            f'patch-{self.new_tag[1:]}.patch.xz'
        with open(patch, 'wb') as f:
            subprocess.run(['xz'], input=b'other', stdout=f, check=True)
        checks = self.checks()
        self.assertEqual(checks['files'].result, 'fail')
        self.assertEqual(checks['signatures'].result, 'fail')
        stub_stdouts(self)
        with self.assertRaises(SystemExit) as e:
            srt_check.execute(Namespace(json=True))
        self.assertEqual(e.exception.code, 1)
        results = {c['name']: c['result']
                   for c in json.loads(stdout_text())}
        self.assertEqual(results['files'], 'fail')

    def test_undo_removes_the_files(self):
        self.release_until('release')
        ctx = SrtContext(None, path=self.rt_dir)
        stub_stdouts(self)
        create(self.config, ctx)
        sign(self.config, ctx)
        d = f'{self.rt_dir}/patches/{self.new_tag}'
        out = self.run_step('undo')
        self.assertIn(f'remove {d}', out)
        self.assertFalse(os.path.exists(d))

    def test_leftover_files(self):
        """Files of a release made and undone by srt 2.1, which kept them."""
        self.prepare()
        d = f'{self.rt_dir}/patches/{self.new_tag}'
        os.makedirs(d)
        v = self.new_tag[1:]
        for f in (f'patch-{v}.patch.xz', f'patches-{v}.tar.xz',
                  f'patch-{v}.patch.sign', f'patches-{v}.tar.sign'):
            write(f'{d}/{f}', 'old')
        info = self.status_json()
        self.assertEqual([s['done'] for s in info['steps']][-2:],
                         [False, False])
        self.assertIn(f'{d} holds files but {self.new_tag} is not tagged',
                      info['warnings'][0])
        checks = self.checks()
        self.assertEqual(checks['files'].result, 'fail')
        self.assertEqual(checks['signatures'].result, 'skip')
        # undo cleans them up as well
        self.assertIn(f'remove {d}', self.run_step('undo'))
        self.assertFalse(os.path.exists(d))

    def test_undo_and_redo(self):
        self.release_until('release')
        old_queue = git(self.patches_dir, 'rev-parse',
                        f'{self.old_tag}-patches^{{}}')
        out = self.run_step('undo')
        self.assertIn('delete tag ' + self.new_tag, out)
        self.assertIn(f"Merge tag 'v6.1.2' into {self.series}", out)
        rel = srt_quilt.Release()
        for step in ('refresh', 'queue', 'rebase', 'merge', 'release'):
            self.assertFalse(rel.done(step), step)
        self.assertEqual(git(self.rt_dir, 'rev-parse', 'HEAD'),
                         git(self.rt_dir, 'rev-parse', self.old_tag + '^{}'))
        self.assertEqual(git(self.patches_dir, 'rev-parse', 'HEAD'),
                         old_queue)
        # the refreshed patches are kept, staged
        self.assertIn('new-fix.patch', git(
            self.patches_dir, 'diff', '--cached', '--name-only'))
        self.assertIn('nothing to undo', self.run_step('undo', ''))
        undo = srt_log.read_log()[-1]
        self.assertEqual(undo['step'], 'quilt undo')
        self.assertEqual(undo['deleted'], [
            self.new_tag, f'{self.new_tag}-rebase', f'{self.new_tag}-patches'])
        self.assertEqual(undo['reset'], f'stable-rt/{self.series}')
        self.assertEqual(undo['queue_commit'], 'undone')
        for step in srt_quilt.STEPS:
            self.run_step(step)
        self.assertTrue(srt_quilt.Release().done('release'))

    def test_undo_refuses_pushed_release(self):
        self.release_until('release')
        git(self.rt_dir, 'push', '-q', 'stable-rt', 'HEAD:' + self.series)
        git(self.rt_dir, 'fetch', '-q', 'stable-rt')
        with self.assertRaises(SystemExit) as e:
            self.run_step('undo')
        self.assertIn('pushed already', str(e.exception))
        self.assertTrue(srt_quilt.Release().done('release'))

    def test_refresh_keeps_patch_when_not_dropped(self):
        self.prepare()
        with self.assertRaises(SystemExit) as e:
            self.run_step('refresh', 'n\n')
        self.assertIn('quilt push of upstreamed.patch failed',
                      str(e.exception))


if __name__ == '__main__':
    unittest.main()
