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
import os
import tempfile
import unittest
from configparser import ConfigParser
from shutil import rmtree
from unittest import mock

from stable_rt_tools import srt_config
from stable_rt_tools.srt_util import get_workflow_branch, is_quilt_workflow

TREE = 'git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt'

# the format of srt 1.x, as in the documentation of 1.5
OLD = f"""\
[DEFAULT]
MAIL_TO = LKML <linux-kernel@vger.kernel.org>
NAME = Daniel
SENDER = Daniel Wagner <wagi@monom.org>

[linux/stable-rt/v6.12-rt]
quilt_workflow = true
LOCALVERSION = localversion-rt
GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
PRJ_GIT_TREE = {TREE}
PRJ_DIR = /pub/linux/kernel/projects/rt/6.12

[linux/stable-rt/v6.12-rt-patches]
LOCALVERSION = localversion-rt
GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
PRJ_GIT_TREE = {TREE}
PRJ_DIR = /pub/linux/kernel/projects/rt/6.12

[linux/stable-rt/v6.12-rt-rebase]
LOCALVERSION = localversion-rt
GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
PRJ_GIT_TREE = {TREE}
PRJ_DIR = /pub/linux/kernel/projects/rt/6.12

[linux/stable-rt/v4.19-rt]
LOCALVERSION = localversion-rt
GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
PRJ_GIT_TREE = {TREE}
PRJ_DIR = /pub/linux/kernel/projects/rt/4.19

[linux/stable-rt/v4.19-rt-next]
LOCALVERSION = localversion-rt
GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
PRJ_GIT_TREE = {TREE}
PRJ_DIR = /pub/linux/kernel/projects/rt/4.19
COMMIT_TMPL = /home/wagi/next-tmpl.txt
"""

NEW = f"""\
[DEFAULT]
MAIL_TO = LKML <linux-kernel@vger.kernel.org>
NAME = Daniel
SENDER = Daniel Wagner <wagi@monom.org>
GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
PRJ_GIT_TREE = {TREE}

[linux/stable-rt/v6.12-rt]
PRJ_DIR = /pub/linux/kernel/projects/rt/6.12
WORKFLOW = quilt

[linux/stable-rt/v4.19-rt]
PRJ_DIR = /pub/linux/kernel/projects/rt/4.19

[linux/stable-rt/v4.19-rt-next]
PRJ_DIR = /pub/linux/kernel/projects/rt/4.19
COMMIT_TMPL = /home/wagi/next-tmpl.txt

"""

KEYS = ('MAIL_TO', 'NAME', 'SENDER', 'GPG_KEY_ID', 'PRJ_GIT_TREE',
        'PRJ_DIR', 'COMMIT_TMPL', 'LOCALVERSION')


def effective(text, group):
    """The settings srt uses for the branch of group, as get_config()."""
    config = ConfigParser()
    config.read_string(text)
    repo, remote, branch = group.split('/', 2)
    for name in (group, f'{repo}/{remote}/{get_workflow_branch(branch)}'):
        if config.has_section(name):
            section = config[name]
            values: dict[str, object] = {k: section.get(k) for k in KEYS}
            values['LOCALVERSION'] = values['LOCALVERSION'] or \
                'localversion-' + section.get('SUFFIX', 'rt')
            values['quilt'] = is_quilt_workflow(section)
            return values
    raise KeyError(group)


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.tdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tdir, 'srt.conf')
        with open(self.path, 'w') as f:
            f.write(OLD)
        os.chmod(self.path, 0o600)

    def tearDown(self):
        rmtree(self.tdir)

    def convert(self):
        with mock.patch('sys.stderr', new_callable=io.StringIO) as err:
            changes = srt_config.convert_file(self.path)
        return changes, err.getvalue()

    def read(self, path=None):
        with open(path or self.path) as f:
            return f.read()

    def test_convert(self):
        changes, out = self.convert()
        self.assertEqual(len(changes), 8)
        self.assertEqual(self.read(), NEW)
        self.assertIn('converted', out)
        self.assertIn('quilt_workflow = true -> WORKFLOW = quilt', out)
        self.assertEqual(self.read(self.path + '.bak'), OLD)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_same_settings_for_every_branch(self):
        self.convert()
        for line in OLD.splitlines():
            if line.startswith('[linux/'):
                group = line[1:-1]
                old = effective(OLD, group)
                # a branch takes the workflow of its series now
                series = group.rsplit('/', 1)[0] + '/' + \
                    get_workflow_branch(group.rsplit('/', 1)[1])
                old['quilt'] = effective(OLD, series)['quilt']
                self.assertEqual(effective(self.read(), group), old, group)

    def test_converts_once(self):
        self.convert()
        changes, out = self.convert()
        self.assertEqual((changes, out), ([], ''))
        self.assertEqual(self.read(), NEW)
        self.assertFalse(os.path.exists(self.path + '.bak1'))

    def test_new_format_untouched(self):
        with open(self.path, 'w') as f:
            f.write('# my comment\n[linux/stable-rt/v6.12-rt]\n'
                    'WORKFLOW = quilt\n')
        self.assertEqual(self.convert(), ([], ''))
        self.assertIn('# my comment', self.read())

    def test_different_branch_group_kept(self):
        with open(self.path, 'w') as f:
            f.write('[a/b/v6.1-rt]\nPRJ_DIR = /x\n'
                    '[a/b/v6.1-rt-rebase]\nPRJ_DIR = /y\n')
        self.assertEqual(self.convert(), ([], ''))

    def test_srt_command_converts(self):
        from stable_rt_tools import srt

        env = {'SRT_CONF': self.tdir, 'HOME': self.tdir}
        with mock.patch.dict(os.environ, env), \
                mock.patch('os.curdir', self.tdir), \
                mock.patch('sys.argv', ['srt', 'status']), \
                mock.patch('sys.stdout', new_callable=io.StringIO), \
                mock.patch('sys.stderr', new_callable=io.StringIO) as err, \
                mock.patch('stable_rt_tools.srt_status.status'):
            srt.main()
        self.assertIn('converted', err.getvalue())
        self.assertEqual(self.read(), NEW)


if __name__ == '__main__':
    unittest.main()
