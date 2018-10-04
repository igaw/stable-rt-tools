#!/usr/bin/env python3
#
# srt - stable rt tooling
#
# Copyright (c) Siemens AG, 2018
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
import os
import unittest
import tempfile
import textwrap
from pprint import pformat
from shutil import rmtree

from srt_util_context import SrtContext
from srt_util import cmd, tag_exists
from srt_commit import commit
from srt_tag import tag
from srt_create import create
from srt_sign import sign
from srt_upload import upload
from srt_push import push
from srt_announce import announce


class StringIO(io.StringIO):
    """
    A "safely" wrapped version
    """

    def __init__(self, value=''):
        value = value.encode('utf8', 'backslashreplace').decode('utf8')
        io.StringIO.__init__(self, value)

    def write(self, msg):
        io.StringIO.write(self, msg.encode('utf8',
                                           'backslashreplace').decode('utf8'))


def stub_stdin(testcase_inst, inputs):
    stdin = sys.stdin

    def cleanup():
        sys.stdin = stdin

    testcase_inst.addCleanup(cleanup)
    sys.stdin = StringIO(inputs)


def stub_stdouts(testcase_inst):
    stderr = sys.stderr
    stdout = sys.stdout

    def cleanup():
        sys.stderr = stderr
        sys.stdout = stdout

    testcase_inst.addCleanup(cleanup)
    sys.stderr = StringIO()
    sys.stdout = StringIO()


def find_string(lines, token):
    for l in lines.splitlines():
        if l.strip() == token:
            return True
    return False


makefile = """
.PHONE: kernelrelease

version := $(shell cat version)
localversion := $(shell \
    if ls localversion* 1> /dev/null 2>&1; then \
        cat localversion*; \
    fi)

kernelrelease:
	@echo $(version)$(localversion)x

defconfig:

"""

class TestSrtBase(unittest.TestCase):
    def setup_stable_repo(self):
        os.mkdir(self.stable_repo)
        os.chdir(self.stable_repo)
        cmd(['git', 'init'])
        version = '4.4.13'
        with open('version', 'w') as f:
            f.write(version)
            f.write('\n\n')
        with open('Makefile', 'w') as f:
            # make kernelrelease adds an bogus? char to the end of the string
            f.write(makefile)

        cmd(['git', 'add', 'version', 'Makefile'])
        cmd(['git', 'commit', '-m', 'Initial stable commit'])
        cmd(['git', 'tag', '-a', '-m', 'v'+version, 'v'+version])

    def setup_stable_new_release(self):
        os.chdir(self.stable_repo)
        version = '4.4.14'
        with open('version', 'w') as f:
            f.write(version)
            f.write('\n\n')
        cmd(['git', 'add', 'version'])
        cmd(['git', 'commit', '-m', 'New stable release'])
        cmd(['git', 'tag', '-a', '-m', 'v'+version, 'v'+version])

    def setup_rt_repo(self):
        os.chdir(self.tdir)
        cmd(['git', 'clone', self.stable_repo, os.path.basename(self.rt_repo)])
        os.chdir(self.rt_repo)
        with open('rt.patch', 'w') as f:
            f.write('adding magic rt feature\n')
        with open(self.config['LOCALVERSION'], 'w') as f:
            f.write('-rt3\n')
        cmd(['git', 'add', 'rt.patch', self.config['LOCALVERSION']])
        cmd(['git', 'commit', '-m', 'Add -rt patches'])
        cmd(['git', 'checkout', '-b', self.branch_rt])
        cmd(['git', 'branch', self.branch_rt_rebase])
        cmd(['git', 'branch', self.branch_rt_next])
        cmd(['git', 'tag', '-a', '-m', 'v4.4.13-rt3', 'v4.4.13-rt3'])
        cmd(['git', 'checkout', 'master'])

    def setup_work_tree(self):
        os.chdir(self.tdir)
        cmd(['git', 'clone', self.rt_repo, os.path.basename(self.work_tree)])
        os.chdir(self.work_tree)
        cmd(['git', 'remote', 'add', 'stable', self.stable_repo])

    def do_merge(self):
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt])
        cmd(['git', 'fetch', '--all'])
        cmd(['git', 'merge', 'v4.4.14'])

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
            'GPG_KEY_ID': '5BF67BC5082672CABB45ACAE587C5ECA5D0A306C',
            'PRJ_GIT_TREE': self.rt_repo,
            'PRJ_DIR': '/pub/linux/kernel/people/wagi/test/4.4',
            'ANNOUNCE': '/home/wagi/work/rt/stable-rt-tools/announce-srt.txt',
            'RC_TEXT': '/home/wagi/work/rt/stable-rt-tools/announce-srt-rc.txt',
            'MAIL_TO': 'Foo Bar <foo@bar.barf>,example@example.com'}

        self.setup_stable_repo()
        self.setup_rt_repo()
        self.setup_work_tree()
        self.setup_stable_new_release()
        self.do_merge()

    def tearDown(self):
        rmtree(self.tdir)

    def _steps(self):
        for attr in sorted(dir(self)):
            if not attr.startswith('step'):
                continue
            yield attr

    def test_srt(self):
        for _s in self._steps():
            getattr(self, _s)()


class TestRelease(TestSrtBase):
    def step1_commit(self):
        stub_stdin(self, 'y')
        stub_stdouts(self)
        commit(self.config, rc=False)
        ans = 'git commit -m Linux 4.4.14-rt4 \nOK to commit? (y/n): '
        self.assertEqual(sys.stdout.getvalue(), ans)
        lines = cmd(['git', 'show'])
        self.assertTrue(find_string(lines, 'Linux 4.4.14-rt4'))

    def step2_tag(self):
        stub_stdin(self, 'y')
        stub_stdouts(self)
        tag(self.config)
        self.assertTrue(tag_exists('v4.4.14-rt4'))

    def step3_commit_rebase(self):
        cmd(['git', 'checkout', self.branch_rt_rebase])
        cmd(['git', 'rebase', 'v4.4.14'])

        stub_stdin(self, 'y')
        stub_stdouts(self)
        commit(self.config, rc=False)
        ans = 'git commit -m Linux 4.4.14-rt4 REBASE\nOK to commit? (y/n): '
        self.assertEqual(sys.stdout.getvalue(), ans)
        lines = cmd(['git', 'show'])
        self.assertTrue(find_string(lines, 'Linux 4.4.14-rt4 REBASE'))

    def step4_tag_rebase(self):
        stub_stdin(self, 'y')
        stub_stdouts(self)
        tag(self.config)
        self.assertTrue(tag_exists('v4.4.14-rt4-rebase'))

    def step5_create(self):
        self.ctx = SrtContext()
        self.ctx.add_tag('old', 'v4.4.13-rt3')
        self.ctx.add_tag('new', 'v4.4.14-rt4')
        self.ctx.init()

        create(self.config, self.ctx)

        path = self.work_tree + '/patches/v4.4.14-rt4/'
        files = [path + 'patch-4.4.14-rt4.patch.xz',
                 path + 'patches-4.4.14-rt4.tar.xz']
        for f in files:
            self.assertEqual(os.path.isfile(f), True)

    def step6_sign(self):
        sign(self.config, self.ctx)

        path = self.work_tree + '/patches/v4.4.14-rt4/'
        files = [path + 'patch-4.4.14-rt4.patch.sign',
                 path + 'patches-4.4.14-rt4.tar.sign']
        for f in files:
            self.assertEqual(os.path.isfile(f), True)

    def step7_upload(self):
        # XXX mocking kup server

        stub_stdin(self, 'n')
        stub_stdouts(self)
        upload(self.config, self.ctx)

        path = self.work_tree + '/patches/v4.4.14-rt4/'
        prj = self.config['PRJ_DIR']
        args = ['kup', 'put',
                path + 'patch-4.4.14-rt4.patch.xz',
                path + 'patch-4.4.14-rt4.patch.sign',
                prj + '/older/', '--',

                'put',
                path + 'patches-4.4.14-rt4.tar.xz',
                path + 'patches-4.4.14-rt4.tar.sign',
                prj + '/older/', '--',

                'ln', prj + '/older/patch-4.4.14-rt4.patch.xz', '../', '--',
                'ln', prj + '/older/patches-4.4.14-rt4.tar.xz', '../', '--',
                'rm', prj + '/patch-4.4.13-rt3.patch.xz', '--',
                'rm', prj + '/patches-4.4.13-rt3.tar.xz', '--',
                'ls', prj]
        msg = '{0}\nOK to commit? (y/n): '.format(pformat(args))
        self.maxDiff = None
        self.assertEqual(sys.stdout.getvalue(), msg)

    def step8_push(self):
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt])

        stub_stdin(self, 'y')
        stub_stdouts(self)
        push(self.config, self.ctx)

    def step9_announce(self):
        stub_stdin(self, '')
        stub_stdouts(self)
        announce(self.config, self.ctx)
        self.assertNotEqual(sys.stdout.getvalue(), '')


class TestReleaseCanditate(TestSrtBase):
    def setup_release(self):
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt])

        # step1_commit()
        stub_stdin(self, 'y')
        stub_stdouts(self)
        commit(self.config, rc=False)

        # step2_tag()
        stub_stdin(self, 'y')
        stub_stdouts(self)
        tag(self.config)

        # step3_commit_rebase()
        cmd(['git', 'checkout', self.branch_rt_rebase])
        cmd(['git', 'rebase', 'v4.4.14'])

        stub_stdin(self, 'y')
        stub_stdouts(self)
        commit(self.config, rc=False)

        # step4_tag_rebase()
        stub_stdin(self, 'y')
        stub_stdouts(self)
        tag(self.config)

        # step5_create()
        ctx = SrtContext()
        ctx.add_tag('old', 'v4.4.13-rt3')
        ctx.add_tag('new', 'v4.4.14-rt4')
        ctx.init()

        # step8_push()
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt])

        stub_stdin(self, 'y')
        stub_stdouts(self)
        push(self.config, ctx)


    def setup_add_patches(self):
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt_next])
        cmd(['git', 'reset', '--hard', self.branch_rt])

        for n in range(1,3):
            filename = 'file{}.txt'.format(n)
            with open(filename, 'w') as f:
                f.write(filename)
                f.write('\n')

            cmd(['git', 'add', filename])
            msg = """\
            Add {}

            Here goes nothing and you are no fun.
            """.format(filename)
            msg = textwrap.dedent(msg)
            cmd(['git', 'commit', '-s', '-m', msg])


    def setUp(self):
        super().setUp()

        self.setup_release()

        cmd(['git', 'checkout', self.branch_rt_next])
        self.setup_add_patches()

    def step1_commit(self):
        stub_stdin(self, 'y')
        stub_stdouts(self)
        commit(self.config, rc=1)
        ans = 'git commit -m Linux 4.4.14-rt5-rc1 \nOK to commit? (y/n): '
        self.assertEqual(sys.stdout.getvalue(), ans)
        lines = cmd(['git', 'show'])
        self.assertTrue(find_string(lines, 'Linux 4.4.14-rt5-rc1'))

    def step2_tag(self):
        stub_stdin(self, 'y')
        stub_stdouts(self)
        tag(self.config)
        self.assertTrue(tag_exists('v4.4.14-rt5-rc1'))

    def step3_create(self):
        self.ctx = SrtContext()
        self.ctx.add_tag('old', 'v4.4.14-rt4')
        self.ctx.add_tag('new', 'v4.4.14-rt5-rc1')
        self.ctx.init()

        create(self.config, self.ctx)

        path = self.work_tree + '/patches/v4.4.14-rt5-rc1/'
        files = [path + 'patch-4.4.14-rt5-rc1.patch.xz',
                 path + 'patches-4.4.14-rt5-rc1.tar.xz']
        for f in files:
            self.assertEqual(os.path.isfile(f), True)

    def step4_sign(self):
        sign(self.config, self.ctx)

        path = self.work_tree + '/patches/v4.4.14-rt5-rc1/'
        files = [path + 'patch-4.4.14-rt5-rc1.patch.sign',
                 path + 'patches-4.4.14-rt5-rc1.tar.sign']
        for f in files:
            self.assertEqual(os.path.isfile(f), True)

    def step5_upload(self):
        # XXX mocking kup server

        stub_stdin(self, 'n')
        stub_stdouts(self)
        upload(self.config, self.ctx)

        path = self.work_tree + '/patches/v4.4.14-rt5-rc1/'
        prj = self.config['PRJ_DIR']
        args = ['kup', 'put',
                path + 'patch-4.4.14-rt5-rc1.patch.xz',
                path + 'patch-4.4.14-rt5-rc1.patch.sign',
                prj + '/older/', '--',

                'put',
                path + 'patches-4.4.14-rt5-rc1.tar.xz',
                path + 'patches-4.4.14-rt5-rc1.tar.sign',
                prj + '/older/', '--',

                'put',
                path + 'patch-4.4.14-rt4-rt5-rc1.patch.xz',
                path + 'patch-4.4.14-rt4-rt5-rc1.patch.sign',
                prj + '/older/', '--',

                'ln', prj + '/older/patch-4.4.14-rt5-rc1.patch.xz', '../', '--',
                'ln', prj + '/older/patches-4.4.14-rt5-rc1.tar.xz', '../', '--',
                'ls', prj]
        msg = '{0}\nOK to commit? (y/n): '.format(pformat(args))
        self.maxDiff = None
        self.assertEqual(sys.stdout.getvalue(), msg)

    def step6_push(self):
        os.chdir(self.work_tree)

        stub_stdin(self, 'y')
        stub_stdouts(self)
        push(self.config, self.ctx)

    def step7_announce(self):
        os.chdir(self.work_tree)

        stub_stdin(self, 'n')
        stub_stdouts(self)
        announce(self.config, self.ctx)
        msg = ('git send-email --dry-run ' +
                '--to="Foo Bar <foo@bar.barf>" --to="example@example.com" ' +
                '{}/patches/v4.4.14-rt5-rc1/mails\n'.format(self.work_tree))
        res = sys.stdout.getvalue()
        self.maxDiff = None
        self.assertTrue(res.find(msg))

        patches = ['0000-cover-letter.patch',
                   '0001-Add-file1.txt.patch',
                   '0002-Add-file2.txt.patch',
                   '0003-Linux-4.4.14-rt5-rc1.patch']
        for p in patches:
            file_path = self.ctx.new_dir_mails + '/' + p
            self.assertTrue(os.path.isfile(file_path))

        with open(self.ctx.new_dir_mails + '/0000-cover-letter.patch', 'r') as f:
            letter = f.read()
            self.assertTrue(letter.find('Linux ' + str(self.ctx.new_tag)))


if __name__ == '__main__':
    import logging
    logging.getLogger().setLevel(logging.DEBUG)
    unittest.main(verbosity=1)
