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
            'MAIL_TO': 'Foo Bar <foo@bar.barf>,example@example.com',
            'SENDER': 'Mighty Eagle <me@incredible.com>',
            'NAME': 'Mighty Eagle'}

        self.setup_gpg()

    def tearDown(self):
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
        self.assertTrue(fingerprint.replace(' ', '')
                        == self.config['GPG_KEY_ID'])
