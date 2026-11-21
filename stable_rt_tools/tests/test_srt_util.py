#!/usr/bin/env python3
#
# srt - stable rt tooling
#
# Copyright (c) Daniel Wagner, 2021
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

import os
import tempfile
from logging import debug
from shutil import rmtree
from unittest import TestCase

from stable_rt_tools.srt_util import cmd, get_gpg_fingerprint
from stable_rt_tools.tests.test_srt import gnupg_config


class TestUtil(TestCase):
    def setUp(self):
        self.tdir = tempfile.mkdtemp()
        self.stable_repo = self.tdir + '/stable-repo'
        self.rt_repo = self.tdir + '/rt-repo'
        self.work_tree = self.tdir + '/work-tree'

        self.branch_rt = 'v4.4-rt'
        self.branch_rt_rebase = 'v4.4-rt-rebase'
        self.branch_rt_next = 'v4.4-rt-next'

        self.config = {
            'LOCALVERSION': 'localversion-rt',
            'PRJ_GIT_TREE': self.rt_repo,
            'PRJ_DIR': '/pub/linux/kernel/people/wagi/test/4.4',
            'MAIL_TO': 'Foo Bar <foo@bar.barf>, <example@example.com>',
            'SENDER': 'Mighty Eagle <me@incredible.com>',
            'NAME': 'Mighty Eagle'}

        self.setup_gpg()

    def tearDown(self):
        # don't leave the next test in a deleted directory
        os.chdir(tempfile.gettempdir())
        rmtree(self.tdir)
        rmtree(self.gnupghome)

    def setup_gpg(self):
        self.gnupghome = tempfile.mkdtemp()
        os.chmod(self.gnupghome, 0o700)

        cfg_file = self.gnupghome + '/gpg.batch'
        with open(cfg_file, 'w') as f:
            f.write(gnupg_config)

        cmd(['gpg', '--batch', '--generate-key', cfg_file],
            env={'GNUPGHOME': self.gnupghome})
        lines = cmd(['gpg', '--list-secret-keys', '--with-colons'],
                    env={'GNUPGHOME': self.gnupghome})

        key = ''
        for line in lines.splitlines():
            c = line.split(':')
            if c[0] != 'fpr':
                continue
            key = c[-2]
            break

        self.config['GPG_KEY_ID'] = key
        self.config['GNUPGHOME'] = self.gnupghome

    def test_get_gpg_fingerprint(self):
        fingerprint = get_gpg_fingerprint(self.config)
        debug('GPG_KEY_ID:  ' + self.config['GPG_KEY_ID'])
        debug('fingerprint: ' + fingerprint)
        self.assertTrue(
            fingerprint.replace(' ', '') == self.config['GPG_KEY_ID']
        )

    def test_quilt_workflow_flag(self):
        from configparser import ConfigParser

        import stable_rt_tools.srt_util as srt_util
        from stable_rt_tools.srt_util import get_config, is_quilt_workflow

        config = ConfigParser()
        section = 'repo/branch'
        config.add_section(section)
        config.set(section, 'quilt_workflow', 'yes')

        def fake_read_config():
            return config

        def fake_get_remote_repo_name(path=None):
            return 'repo'

        def fake_get_remote_branch_name(short=False, path=None):
            return 'branch'

        old_read_config = srt_util.read_config
        old_get_remote_repo_name = srt_util.get_remote_repo_name
        old_get_remote_branch_name = srt_util.get_remote_branch_name
        srt_util.read_config = fake_read_config
        srt_util.get_remote_repo_name = fake_get_remote_repo_name
        srt_util.get_remote_branch_name = fake_get_remote_branch_name
        try:
            cfg = get_config()
            self.assertTrue(is_quilt_workflow(cfg))
        finally:
            srt_util.read_config = old_read_config
            srt_util.get_remote_repo_name = old_get_remote_repo_name
            srt_util.get_remote_branch_name = old_get_remote_branch_name

    def test_get_config_missing_section(self):
        from configparser import ConfigParser
        from unittest import mock

        import stable_rt_tools.srt_util as srt_util

        with mock.patch.object(srt_util, 'read_config',
                               return_value=ConfigParser()), \
                mock.patch.object(srt_util, 'get_remote_repo_name',
                                  return_value='linux'), \
                mock.patch.object(srt_util, 'get_remote_branch_name',
                                  return_value='stable-rt/v6.12-rt'), \
                self.assertRaises(SystemExit) as cm:
            srt_util.get_config()
        self.assertIn('[linux/stable-rt/v6.12-rt]', str(cm.exception.code))

    def test_get_config_no_upstream(self):
        from subprocess import CalledProcessError
        from unittest import mock

        import stable_rt_tools.srt_util as srt_util

        with mock.patch.object(srt_util, 'get_remote_repo_name',
                               return_value='linux'), \
                mock.patch.object(
                    srt_util, 'get_remote_branch_name',
                    side_effect=CalledProcessError(128, 'git')), \
                self.assertRaises(SystemExit) as cm:
            srt_util.get_config()
        self.assertIn('upstream', str(cm.exception.code))

    def test_get_gpg_env_keeps_environment(self):
        import os
        from unittest import mock

        import stable_rt_tools.srt_util as srt_util

        with mock.patch.dict(os.environ, {'HOME': '/home/someone'}):
            env = srt_util.get_gpg_env({'GNUPGHOME': '~/keys'})
        self.assertEqual(env['HOME'], '/home/someone')
        self.assertEqual(env['GNUPGHOME'], '/home/someone/keys')

    def test_read_config_srt_conf_wins(self):
        import os
        from unittest import mock

        import stable_rt_tools.srt_util as srt_util

        tmp = tempfile.mkdtemp()
        try:
            for d, val in (('env', 'from-env'), ('home', 'from-home')):
                os.makedirs(os.path.join(tmp, d, '.config'))
                with open(os.path.join(tmp, d, '.config', 'srt.conf'),
                          'w') as f:
                    f.write(f'[a/b]\nKEY = {val}\n')
            env = {'SRT_CONF': os.path.join(tmp, 'env', '.config'),
                   'HOME': os.path.join(tmp, 'home')}
            with mock.patch.dict(os.environ, env):
                config = srt_util.read_config()
            self.assertEqual(config['a/b']['KEY'], 'from-env')
        finally:
            rmtree(tmp)

    def test_get_template_path(self):
        import os

        import stable_rt_tools.srt_util as srt_util

        for key, name in (('ANNOUNCE', 'announce-srt.txt'),
                          ('RC_TEXT', 'announce-srt-rc.txt'),
                          ('COMMIT_TMPL', 'commit-tmpl.txt')):
            path = srt_util.get_template_path({}, key, name)
            self.assertTrue(os.path.isfile(path), path)
            self.assertEqual(
                srt_util.get_template_path({key: '/my/tmpl'}, key, name),
                '/my/tmpl')

    def test_confirm_eof_is_no(self):
        import io
        from unittest import mock

        import stable_rt_tools.srt_util as srt_util

        with mock.patch('sys.stdin', io.StringIO('')), \
                mock.patch('sys.stdout', io.StringIO()):
            self.assertFalse(srt_util.confirm('OK?'))
        with mock.patch('sys.stdin', io.StringIO('maybe\ny\n')), \
                mock.patch('sys.stdout', io.StringIO()):
            self.assertTrue(srt_util.confirm('OK?'))

    def test_pipe(self):
        import stable_rt_tools.srt_util as srt_util

        with tempfile.TemporaryFile() as f:
            srt_util.pipe(['printf', 'abc'], ['tr', 'a-z', 'A-Z'], stdout=f)
            f.seek(0)
            self.assertEqual(f.read(), b'ABC')
        for producer, consumer, culprit in (
                (['false'], ['cat'], 'false'),
                # the producer may die of SIGPIPE, the consumer is the cause
                (['yes'], ['false'], 'false'),
                (['printf', 'x'], ['false'], 'false')):
            with tempfile.TemporaryFile() as f, \
                    self.assertRaises(SystemExit) as e:
                srt_util.pipe(producer, consumer, stdout=f)
            self.assertEqual(str(e.exception),
                             f'{culprit} failed with exit code 1')

    def test_check_context_exits_on_missing_tag(self):
        import argparse
        from unittest import mock

        import stable_rt_tools.srt_util as srt_util
        from stable_rt_tools.srt_util_context import SrtContext

        ctx = SrtContext(argparse.Namespace(OLD_TAG='v6.12.111-rt21',
                                            NEW_TAG='v6.12.116-rt22'),
                         path='/tmp')
        with mock.patch.object(srt_util, 'tag_exists',
                               side_effect=lambda t, path=None:
                               str(t) != 'v6.12.116'):
            with self.assertRaises(SystemExit) as e:
                srt_util.check_context(ctx)
        self.assertIn('v6.12.116', str(e.exception))
        with mock.patch.object(srt_util, 'tag_exists', return_value=True):
            srt_util.check_context(ctx)

    def test_format_fingerprint(self):
        import stable_rt_tools.srt_util as srt_util

        self.assertEqual(
            srt_util.format_fingerprint(
                'B0C0324F040A1861EF965160DA7C9F5C915CFC7C'),
            'B0C0 324F 040A 1861 EF96  5160 DA7C 9F5C 915C FC7C')

    def test_get_gpg_fingerprint_of_the_configured_key(self):
        import stable_rt_tools.srt_util as srt_util

        # a second key in the keyring must not be picked up
        batch = os.path.join(self.gnupghome, 'other.batch')
        with open(batch, 'w') as f:
            f.write(gnupg_config.replace('Mighty Eagle', 'Other Key')
                    .replace('me@incredible.com', 'other@example.com'))
        cmd(['gpg', '--batch', '--generate-key', batch],
            env={'GNUPGHOME': self.gnupghome})
        config = {'GNUPGHOME': self.gnupghome,
                  'GPG_KEY_ID': self.config['GPG_KEY_ID']}
        fpr = srt_util.get_gpg_fingerprint(config)
        self.assertEqual(fpr.replace(' ', ''), self.config['GPG_KEY_ID'])

    def test_upload_fails_with_kup(self):
        import argparse
        from subprocess import CalledProcessError
        from unittest import mock

        from stable_rt_tools import srt_upload
        from stable_rt_tools.srt_util_context import SrtContext

        ctx = SrtContext(argparse.Namespace(OLD_TAG='v6.12.111-rt21',
                                            NEW_TAG='v6.12.116-rt22'),
                         path=self.tdir)
        with mock.patch('os.path.isfile', return_value=True), \
                mock.patch.object(srt_upload, 'confirm', return_value=True), \
                mock.patch.object(srt_upload, 'cmd',
                                  side_effect=CalledProcessError(3, 'kup')), \
                mock.patch('sys.stdout'), mock.patch('sys.stderr'), \
                self.assertRaises(SystemExit) as e:
            srt_upload.upload({'PRJ_DIR': '/pub/rt/6.12'}, ctx)
        self.assertEqual(e.exception.code, 3)

    def test_upload_dry_run(self):
        import argparse
        import io
        from unittest import mock

        from stable_rt_tools import srt_upload
        from stable_rt_tools.srt_util_context import SrtContext

        ctx = SrtContext(argparse.Namespace(OLD_TAG='v6.12.111-rt21',
                                            NEW_TAG='v6.12.116-rt22'),
                         path=self.tdir)
        with mock.patch('os.path.isfile', return_value=True), \
                mock.patch.object(srt_upload, 'confirm') as confirm, \
                mock.patch.object(srt_upload, 'cmd') as kup, \
                mock.patch('sys.stdout', new_callable=io.StringIO) as out:
            srt_upload.upload({'PRJ_DIR': '/pub/rt/6.12'}, ctx, dry_run=True)
        confirm.assert_not_called()
        kup.assert_not_called()
        self.assertIn("'put'", out.getvalue())
        self.assertIn('/pub/rt/6.12/older/', out.getvalue())

    def test_require(self):
        from configparser import ConfigParser

        from stable_rt_tools.srt_util import require, with_defaults

        self.assertEqual(require({'PRJ_DIR': '/pub'}, 'PRJ_DIR'), '/pub')
        with self.assertRaises(SystemExit) as e:
            require({'PRJ_DIR': ''}, 'PRJ_DIR')
        self.assertEqual(e.exception.code,
                         'PRJ_DIR is not set: add it to srt.conf')

        config = ConfigParser()
        config.read_string('[rt/origin/v6.12-rt]\nPRJ_DIR = /pub\n')
        group = with_defaults(config['rt/origin/v6.12-rt'])
        self.assertEqual(require(group, 'PRJ_DIR'), '/pub')
        with self.assertRaises(SystemExit) as e:
            require(group, 'MAIL_TO')
        self.assertEqual(e.exception.code,
                         'MAIL_TO is not set: add it to the '
                         '[rt/origin/v6.12-rt] group of srt.conf')

    def test_require_hints_git_config(self):
        from stable_rt_tools.srt_util import require

        with self.assertRaises(SystemExit) as e:
            require({}, 'GPG_KEY_ID')
        self.assertEqual(e.exception.code,
                         'GPG_KEY_ID is not set: add it to the [DEFAULT] '
                         'group of srt.conf or set git config '
                         'user.signingkey')
        with self.assertRaises(SystemExit) as e:
            require({}, 'SENDER')
        self.assertIn('git config user.name and user.email',
                      str(e.exception.code))

    def test_upload_without_prj_dir(self):
        import argparse
        from unittest import mock

        from stable_rt_tools import srt_upload
        from stable_rt_tools.srt_util_context import SrtContext

        ctx = SrtContext(argparse.Namespace(OLD_TAG='v6.12.111-rt21',
                                            NEW_TAG='v6.12.116-rt22'),
                         path=self.tdir)
        with mock.patch('os.path.isfile', return_value=True), \
                mock.patch.object(srt_upload, 'cmd') as kup, \
                self.assertRaises(SystemExit) as e:
            srt_upload.upload({}, ctx)
        kup.assert_not_called()
        self.assertEqual(e.exception.code,
                         'PRJ_DIR is not set: add it to srt.conf')

    def test_srt_without_command_shows_usage(self):
        import io
        from unittest import mock

        from stable_rt_tools import srt

        with mock.patch('sys.argv', ['srt']), \
                mock.patch('sys.stderr', new_callable=io.StringIO) as err, \
                self.assertRaises(SystemExit) as e:
            srt.main()
        self.assertEqual(e.exception.code, 2)
        self.assertIn('usage: srt', err.getvalue())

    def test_get_config_falls_back_to_the_series(self):
        from configparser import ConfigParser
        from unittest import mock

        import stable_rt_tools.srt_util as srt_util

        config = ConfigParser()
        config.read_string('[linux/stable-rt/v6.12-rt]\nSUFFIX = rt\n'
                           '[linux/stable-rt/v6.12-rt-rebase]\nSUFFIX = x\n')
        for branch, suffix in (('v6.12-rt', 'rt'), ('v6.12-rt-patches', 'rt'),
                               ('v6.12-rt-rebase', 'x')):
            with mock.patch.object(srt_util, 'read_config',
                                   return_value=config), \
                    mock.patch.object(srt_util, 'get_remote_repo_name',
                                      return_value='linux'), \
                    mock.patch.object(srt_util, 'get_remote_branch_name',
                                      return_value='stable-rt/' + branch):
                self.assertEqual(srt_util.get_config()['SUFFIX'], suffix,
                                 branch)

    def test_config_defaults(self):
        from configparser import ConfigParser
        from unittest import mock

        import stable_rt_tools.srt_util as srt_util

        git_config = {'user.signingkey': 'ABCD', 'user.name': 'Ada Lovelace',
                      'user.email': 'ada@example.com'}
        config = ConfigParser()
        config.read_string('[DEFAULT]\nMAIL_TO = list@example.com\n'
                           '[a/b/v6.1-foo]\nSUFFIX = foo\n'
                           '[a/b/v6.12-rt]\nNAME = Daniel\n')
        with mock.patch.object(srt_util, '_git_config',
                               side_effect=git_config.get):
            foo = srt_util.with_defaults(config['a/b/v6.1-foo'])
            rt = srt_util.with_defaults(config['a/b/v6.12-rt'])
        self.assertEqual(foo['LOCALVERSION'], 'localversion-foo')
        self.assertEqual(rt['LOCALVERSION'], 'localversion-rt')
        self.assertEqual(foo['GPG_KEY_ID'], 'ABCD')
        self.assertEqual(foo['SENDER'], 'Ada Lovelace <ada@example.com>')
        self.assertEqual(foo['NAME'], 'Ada')
        # the group wins, [DEFAULT] applies, keys are case-insensitive
        self.assertEqual(rt['NAME'], 'Daniel')
        self.assertEqual(rt['MAIL_TO'], 'list@example.com')
        self.assertEqual(rt['mail_to'], 'list@example.com')
        self.assertNotIn('ANNOUNCE', rt)

    def test_workflow_setting(self):
        from configparser import ConfigParser

        import stable_rt_tools.srt_util as srt_util

        config = ConfigParser()
        config.read_string('[quilt]\nWORKFLOW = quilt\n[git]\nWORKFLOW = git\n'
                           '[old]\nquilt_workflow = true\n[none]\n'
                           '[bad]\nWORKFLOW = svn\n')
        for name, quilt in (('quilt', True), ('git', False), ('old', True),
                            ('none', False)):
            self.assertEqual(srt_util.is_quilt_workflow(config[name]), quilt,
                             name)
        with self.assertRaises(SystemExit):
            srt_util.is_quilt_workflow(config['bad'])


class TestStatePerSeries(TestCase):
    """Two series in one work area: the worktrees share the git common
    dir, each series has its own prepared release."""

    def setUp(self):
        self.tdir = tempfile.mkdtemp()
        self.addCleanup(rmtree, self.tdir)
        self.linux = self.tdir + '/linux'
        cmd(['git', 'init', '-q', '-b', 'master', self.linux])
        cmd(['git', '-C', self.linux, '-c', 'user.name=T',
             '-c', 'user.email=t@x', 'commit', '-q', '--allow-empty',
             '-m', 'init'])
        for b in ('v6.12-rt', 'v6.12-rt-patches', 'v6.18-rt'):
            cmd(['git', '-C', self.linux, 'worktree', 'add', '-q', '-b', b,
                 f'{self.tdir}/{b}'])

    def state(self, series):
        return {'old_tag': f'{series}-a', 'new_tag': f'{series}-b',
                'workflow_branch': series}

    def test_one_state_per_series(self):
        from stable_rt_tools import srt_util

        v612, v618 = self.tdir + '/v6.12-rt', self.tdir + '/v6.18-rt'
        srt_util.write_srt_state(self.state('v6.12-rt'), v612)
        self.assertIsNone(srt_util.read_srt_state(v618))
        srt_util.write_srt_state(self.state('v6.18-rt'), v618)
        # all worktrees of a series share its state
        for path, series in ((v612, 'v6.12-rt'),
                             (self.tdir + '/v6.12-rt-patches', 'v6.12-rt'),
                             (v618, 'v6.18-rt')):
            state = srt_util.read_srt_state(path)
            assert state is not None
            self.assertEqual(state['new_tag'], f'{series}-b')
        srt_util.clear_srt_state(v618)
        self.assertIsNone(srt_util.read_srt_state(v618))
        self.assertIsNotNone(srt_util.read_srt_state(v612))

    def test_state_of_srt_2_1_moves_to_its_series(self):
        import json

        from stable_rt_tools import srt_util

        legacy = self.linux + '/.git/srt/state.json'
        os.makedirs(os.path.dirname(legacy))
        with open(legacy, 'w') as f:
            json.dump(self.state('v6.12-rt'), f)
        # another series doesn't take it
        self.assertIsNone(srt_util.read_srt_state(self.tdir + '/v6.18-rt'))
        self.assertTrue(os.path.exists(legacy))
        state = srt_util.read_srt_state(self.tdir + '/v6.12-rt-patches')
        assert state is not None
        self.assertEqual(state['new_tag'], 'v6.12-rt-b')
        self.assertFalse(os.path.exists(legacy))
        self.assertTrue(os.path.exists(self.linux + '/.git/srt/v6.12-rt.json'))


class TestReleaseTags(TestCase):
    """The releases found in the history of a real repository: the
    series v6.1-rt with v6.1.1-rt1 and v6.1.2-rt2, published on origin,
    the stable tree is the clone v6.1 next to it."""

    def git(self, path, *args):
        return cmd(['git', '-C', path, '-c', 'user.name=Mighty Eagle',
                    '-c', 'user.email=me@incredible.com'] + list(args))

    def commit(self, path, msg):
        # stable changes version, the series localversion-rt: the stable
        # merges don't conflict
        name = 'version' if path == self.stable else 'localversion-rt'
        with open(f'{path}/{name}', 'w') as f:
            f.write(msg + '\n')
        self.git(path, 'add', name)
        self.git(path, 'commit', '-q', '-m', msg)

    def tag(self, path, name):
        self.git(path, 'tag', '-a', '-m', name, name)

    def stable_release(self, version):
        self.commit(self.stable, f'Linux {version}')
        self.tag(self.stable, f'v{version}')
        self.git(self.rt, 'fetch', '-q', 'stable', '--tags')

    def rt_release(self, version, number, rc=None):
        self.git(self.rt, 'merge', '-q', '--no-ff', '-m',
                 f'Merge tag v{version}', f'v{version}')
        name = f'v{version}-rt{number}' + (f'-rc{rc}' if rc else '')
        self.commit(self.rt, f'Linux {name[1:]}')
        self.tag(self.rt, name)

    def setUp(self):
        self.tdir = tempfile.mkdtemp()
        self.addCleanup(rmtree, self.tdir)
        self.addCleanup(os.chdir, os.getcwd())
        self.stable = self.tdir + '/v6.1'
        self.rt = self.tdir + '/v6.1-rt'
        self.origin = self.tdir + '/origin.git'

        cmd(['git', 'init', '-q', '-b', 'master', self.stable])
        self.commit(self.stable, 'Linux 6.1.1')
        self.tag(self.stable, 'v6.1.1')

        cmd(['git', 'clone', '-q', '-o', 'stable', self.stable, self.rt])
        self.git(self.rt, 'checkout', '-q', '-b', 'v6.1-rt', 'v6.1.1')
        self.commit(self.rt, 'Linux 6.1.1-rt1')
        self.tag(self.rt, 'v6.1.1-rt1')
        self.stable_release('6.1.2')
        self.rt_release('6.1.2', 2)

        cmd(['git', 'init', '-q', '--bare', self.origin])
        self.git(self.rt, 'remote', 'add', 'origin', self.origin)
        self.git(self.rt, 'push', '-q', '-u', 'origin', 'v6.1-rt', '--tags')
        self.stable_release('6.1.3')
        os.chdir(self.rt)

    def context(self):
        from unittest import mock

        from stable_rt_tools.srt_util_context import SrtContext

        with mock.patch.dict(os.environ):
            os.environ.pop('OLD_TAG', None)
            os.environ.pop('NEW_TAG', None)
            ctx = SrtContext(None, path=self.rt)
        return str(ctx.old_tag), str(ctx.new_tag)

    def test_last_release_not_the_merged_stable_tag(self):
        from stable_rt_tools.srt_util import (
            get_last_release,
            get_previous_release,
        )

        self.git(self.rt, 'merge', '-q', '--no-ff', '-m', 'Merge', 'v6.1.3')
        self.assertEqual(get_last_release('HEAD', 'rt'), 'v6.1.2-rt2')
        self.assertEqual(get_last_release(), 'v6.1.2-rt2')
        self.assertIsNone(get_last_release('HEAD', 'foo'))
        self.assertEqual(get_previous_release('v6.1.2-rt2'), 'v6.1.1-rt1')
        with self.assertRaises(SystemExit):
            get_previous_release('v6.1.1-rt1')

    def test_no_release_on_a_branch_without_one(self):
        from stable_rt_tools.srt_util import get_last_release

        # like a -rebase branch: only upstream history on the first
        # parents, with an old mainline release candidate in it
        self.git(self.stable, 'tag', '-a', '-m', 'old', 'v2.6.39-rc7',
                 'v6.1.1')
        self.assertIsNone(get_last_release('v6.1.3', rc=True,
                                           path=self.stable))
        self.assertIsNone(get_last_release('v6.1.3', path=self.stable))

    def test_prep_finds_the_old_release_locally(self):
        from unittest import mock

        from stable_rt_tools.srt_prep import prep
        from stable_rt_tools.srt_util import read_srt_state

        # nothing is fetched: origin can't be reached
        self.git(self.rt, 'remote', 'set-url', 'origin', '/nonexistent')
        self.git(self.rt, 'merge', '-q', '--no-ff', '-m', 'Merge', 'v6.1.3')
        with mock.patch('sys.stdout'):
            prep({'WORKFLOW': 'git'}, pull=False)
        state = read_srt_state(self.rt)
        assert state is not None
        self.assertEqual(state['old_tag'], 'v6.1.2-rt2')
        self.assertEqual(state['new_tag'], 'v6.1.3-rt3')

    def test_after_push_without_state(self):
        # srt push published v6.1.3-rt3 and cleared the state
        self.rt_release('6.1.3', 3)
        self.git(self.rt, 'push', '-q', 'origin', 'v6.1-rt', '--tags')
        self.assertEqual(self.context(), ('v6.1.2-rt2', 'v6.1.3-rt3'))

    def test_tagged_not_pushed_without_state(self):
        self.rt_release('6.1.3', 3)
        self.assertEqual(self.context(), ('v6.1.2-rt2', 'v6.1.3-rt3'))

    def test_release_candidate(self):
        from stable_rt_tools.srt_util import (
            get_last_release,
            get_last_release_number,
            get_previous_release,
        )

        self.git(self.rt, 'checkout', '-q', '-b', 'v6.1-rt-next')
        self.rt_release('6.1.3', 3, rc=1)
        # the new release is the release candidate, the old one the last
        # release
        self.assertEqual(self.context(), ('v6.1.2-rt2', 'v6.1.3-rt3-rc1'))
        self.assertEqual(get_last_release('HEAD', 'rt'), 'v6.1.2-rt2')
        # srt commit -r numbers the release after the last one of v6.1-rt
        self.assertEqual(
            get_last_release_number('v6.1-rt-next', 'rt', '-next'), 2)

        # the release after the release candidate, on v6.1-rt
        self.git(self.rt, 'checkout', '-q', 'v6.1-rt')
        self.git(self.rt, 'merge', '-q', '--ff-only', 'v6.1-rt-next')
        self.commit(self.rt, 'Linux 6.1.3-rt3')
        self.tag(self.rt, 'v6.1.3-rt3')
        self.assertEqual(get_previous_release('v6.1.3-rt3'), 'v6.1.2-rt2')
        self.assertEqual(self.context(), ('v6.1.2-rt2', 'v6.1.3-rt3'))

    def test_remote_branch_name(self):
        from stable_rt_tools.srt_util import get_remote_branch_name

        self.assertEqual(get_remote_branch_name(), 'v6.1-rt')
        self.assertEqual(get_remote_branch_name(short=False),
                         'origin/v6.1-rt')
        # a branch name with '/', tracked by a local branch of another
        # name, on a remote with '/' in its name
        self.git(self.rt, 'remote', 'add', 'kernel/org', self.origin)
        self.git(self.rt, 'push', '-q', 'kernel/org',
                 'v6.1-rt:stable/v6.1-rt')
        self.git(self.rt, 'checkout', '-q', '-b', 'work', '--track',
                 'kernel/org/stable/v6.1-rt')
        self.assertEqual(get_remote_branch_name(), 'stable/v6.1-rt')
        self.assertEqual(get_remote_branch_name(short=False),
                         'kernel/org/stable/v6.1-rt')

    def test_get_config_of_another_worktree(self):
        from unittest import mock

        from stable_rt_tools.srt_util import (
            get_config,
            get_remote_branch_name,
            get_remote_repo_name,
        )

        # srt runs in the directory above the worktrees, srt.conf is there
        os.chdir(self.tdir)
        with open(f'{self.tdir}/srt.conf', 'w') as f:
            f.write('[origin/origin/v6.1-rt]\nSUFFIX = foo\n')
        self.git(self.rt, 'config', 'user.signingkey', 'ABCD')
        self.assertEqual(get_remote_repo_name(self.rt), 'origin')
        self.assertEqual(get_remote_branch_name(path=self.rt), 'v6.1-rt')
        with mock.patch.dict(os.environ):
            os.environ.pop('SRT_CONF', None)
            config = get_config(self.rt)
        self.assertEqual(config['SUFFIX'], 'foo')
        # the git configuration of the worktree, not of the cwd
        self.assertEqual(config['GPG_KEY_ID'], 'ABCD')
        self.assertEqual(os.getcwd(), self.tdir)

    def test_context_of_another_worktree(self):
        from unittest import mock

        from stable_rt_tools.srt_util import write_srt_state
        from stable_rt_tools.srt_util_context import SrtContext

        write_srt_state({'old_tag': 'v6.1.2-rt2', 'new_tag': 'v6.1.3-rt3',
                         'workflow_branch': 'v6.1-rt'}, self.rt)
        # the current directory is no git repository at all
        os.chdir(self.tdir)
        with mock.patch.dict(os.environ):
            os.environ.pop('OLD_TAG', None)
            os.environ.pop('NEW_TAG', None)
            ctx = SrtContext(None, path=self.rt)
        self.assertEqual(str(ctx.old_tag), 'v6.1.2-rt2')
        self.assertEqual(str(ctx.new_tag), 'v6.1.3-rt3')
        self.assertEqual(os.getcwd(), self.tdir)
