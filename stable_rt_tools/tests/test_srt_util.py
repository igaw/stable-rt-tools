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

gnupg_config = """
Key-Type: DSA
Key-Length: 1024
Subkey-Type: ELG-E
Subkey-Length: 1024
Name-Real: Mighty Eagle
Name-Email: me@incredible.com
Expire-Date: 0
%no-protection
%commit
%echo done
"""


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

        cmd(['gpg2', '--batch', '--generate-key', cfg_file],
            env={'GNUPGHOME': self.gnupghome})
        lines = cmd(['gpg2', '--list-secret-keys', '--with-colons'],
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
        from stable_rt_tools.srt_util import get_config, is_quilt_workflow
        import stable_rt_tools.srt_util as srt_util

        config = ConfigParser()
        section = 'repo/branch'
        config.add_section(section)
        config.set(section, 'quilt_workflow', 'yes')

        def fake_read_config():
            return config

        def fake_get_remote_repo_name():
            return 'repo'

        def fake_get_remote_branch_name(short=False):
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
                self.assertLogs(level='ERROR') as log, \
                self.assertRaises(SystemExit):
            srt_util.get_config()
        self.assertIn('[linux/stable-rt/v6.12-rt]', log.output[0])

    def test_get_config_no_upstream(self):
        from subprocess import CalledProcessError
        from unittest import mock
        import stable_rt_tools.srt_util as srt_util

        with mock.patch.object(srt_util, 'get_remote_repo_name',
                               return_value='linux'), \
                mock.patch.object(
                    srt_util, 'get_remote_branch_name',
                    side_effect=CalledProcessError(128, 'git')), \
                self.assertLogs(level='ERROR') as log, \
                self.assertRaises(SystemExit):
            srt_util.get_config()
        self.assertIn('upstream', log.output[0])

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
                    f.write('[a/b]\nKEY = {0}\n'.format(val))
            env = {'SRT_CONF': os.path.join(tmp, 'env', '.config'),
                   'HOME': os.path.join(tmp, 'home')}
            with mock.patch.dict(os.environ, env):
                config = srt_util.read_config()
            self.assertEqual(config['a/b']['KEY'], 'from-env')
        finally:
            rmtree(tmp)
