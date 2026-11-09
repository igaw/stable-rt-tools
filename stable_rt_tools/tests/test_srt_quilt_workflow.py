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

import os
import subprocess
import tempfile
import unittest
from shutil import rmtree
from unittest import mock

from stable_rt_tools import srt_quilt, srt_setup
from stable_rt_tools.srt_create import create
from stable_rt_tools.srt_prep import prep
from stable_rt_tools.srt_sign import sign
from stable_rt_tools.srt_util import cmd, read_srt_state
from stable_rt_tools.srt_util_context import SrtContext
from stable_rt_tools.tests.test_srt import (
    gnupg_config,
    makefile,
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
        write(self.stable_repo + '/Makefile', makefile)
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
        git(self.stable_repo, 'tag', '-a', '-m', 'v6.1.2', 'v6.1.2')

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

        patcher = mock.patch('stable_rt_tools.srt_quilt.get_config',
                             return_value=self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
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

    def run_setup(self, config, group=None, parent=None):
        stub_stdouts(self)
        srt_setup.setup(group or self.group, config, parent or self.rt)
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

    def step6_release(self):
        self.run_step('release')
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
        srt_quilt.status(srt_quilt.Release())
        out = stdout_text()
        self.assertIn(f'{self.old_tag} -> {self.new_tag}', out)
        self.assertNotIn('[ ]', out)
        self.assertIn('next: srt create', out)

    def step8_create_sign(self):
        ctx = SrtContext(None, path=self.rt_dir)
        create(self.config, ctx)
        sign(self.config, ctx)
        d = self.rt_dir + '/patches/' + self.new_tag + '/'
        v = self.new_tag[1:]
        for f in (f'patch-{v}.patch.xz', f'patches-{v}.tar.xz',
                  f'patch-{v}.patch.sign', f'patches-{v}.tar.sign'):
            self.assertTrue(os.path.isfile(d + f), f)

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


class TestTakeover(TestQuiltBase):
    """Take over linux-6.2.y-rt, published by another maintainer, as
    v6.2-rt next to the existing v6.1-rt work area."""

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
                               UPSTREAM_BRANCH='linux-6.2.y',
                               TAKEOVER_BRANCH='linux-6.2.y-rt')
        self.series_v62 = 'v6.2-rt'

    def publish(self, out):
        for line in out.splitlines():
            if line.startswith('  git -C '):
                cmd(line.split())

    def test_takeover_on_the_same_remote(self):
        out = self.run_setup(self.config_v62,
                             group='linux/stable-rt/v6.2-rt')
        for b in ('', '-patches', '-rebase'):
            path = f'{self.rt}/v6.2-rt{b}'
            self.assertIn(f'take  {path} (v6.2-rt{b} from '
                          f'stable-rt/linux-6.2.y-rt{b})', out)
            self.assertEqual(git(path, 'rev-parse', 'HEAD'),
                             git(self.rt_repo, 'rev-parse',
                                 f'linux-6.2.y-rt{b}'))
        self.assertIn(f'ok    {self.rt}/linux ', out)
        self.assertIn(f'add   worktree {self.rt}/v6.2 (linux-6.2.y', out)
        self.assertIn('srt setup pushes nothing', out)
        self.assertNotIn('v6.2-rt', git(self.rt_repo, 'branch'))

        # rerun before publishing
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

    def test_takeover_from_another_remote(self):
        config = dict(self.config_v62, TAKEOVER_REMOTE='rt-devel',
                      TAKEOVER_GIT_URL=self.rt_repo)
        out = self.run_setup(config, group='linux/stable-rt/v6.2-rt')
        self.assertIn(f'add   remote rt-devel {self.rt_repo}', out)
        self.assertIn('from rt-devel/linux-6.2.y-rt-rebase)', out)

    def test_missing_series_without_takeover(self):
        config = dict(self.config_v62)
        del config['TAKEOVER_BRANCH']
        with self.assertRaises(srt_setup.SetupError) as e:
            self.run_setup(config, group='linux/stable-rt/v6.2-rt')
        self.assertIn('set TAKEOVER_BRANCH', str(e.exception))


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
