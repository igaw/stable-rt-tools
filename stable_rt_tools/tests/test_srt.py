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
import argparse
import re
from pprint import pformat
from shutil import rmtree
from logging import error, debug

from stable_rt_tools.srt_util_context import SrtContext
from stable_rt_tools.srt_util import cmd, tag_exists, check_context
from stable_rt_tools.srt_commit import commit
from stable_rt_tools.srt_tag import tag
from stable_rt_tools.srt_create import create
from stable_rt_tools.srt_sign import sign
from stable_rt_tools.srt_upload import upload
from stable_rt_tools.srt_push import push
from stable_rt_tools.srt_announce import announce


def sort_steps(entries):
    entries = list(filter(lambda x: x.startswith('step'), entries))
    convert = lambda text: int(text) if text.isdigit() else text
    key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ]
    return sorted(entries, key = key)


def make_args(old_tag=None, new_tag=None):
    return argparse.Namespace(OLD_TAG=old_tag, NEW_TAG=new_tag)


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

class TestSrtBase(unittest.TestCase):
    def setup_stable_repo(self, version):
        os.mkdir(self.stable_repo)
        os.chdir(self.stable_repo)
        cmd(['git', 'init', '--initial-branch=master'])
        with open('version', 'w') as f:
            f.write(version)
            f.write('\n\n')
        with open('Makefile', 'w') as f:
            # make kernelrelease adds an bogus? char to the end of the string
            f.write(makefile)

        cmd(['git', 'add', 'version', 'Makefile'])
        cmd(['git', 'commit', '-m', 'Initial stable commit'])
        cmd(['git', 'tag', '-a', '-m', 'v'+version, 'v'+version])

    def setup_stable_new_release(self, version):
        os.chdir(self.stable_repo)
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

    def do_merge(self, version):
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt])
        cmd(['git', 'fetch', '--all'])
        cmd(['git', 'merge', 'v'+version])

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
        for l in lines.splitlines():
            c = l.split(':')
            if c[0] != 'fpr':
                continue
            key = c[-2]
            break

        self.config['GPG_KEY_ID'] = key
        self.config['GNUPGHOME'] = self.gnupghome

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
        self.setup_stable_repo('4.4.13')
        self.setup_rt_repo()
        self.setup_work_tree()
        self.setup_stable_new_release('4.4.14')
        self.do_merge('4.4.14')

    def tearDown(self):
        rmtree(self.tdir)
        rmtree(self.gnupghome)

    def _steps(self):
        for attr in sort_steps(dir(self)):
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
        self.ctx = SrtContext(make_args('v4.4.13-rt3', 'v4.4.14-rt4'),
                              path=self.work_tree)

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
        ap = argparse.ArgumentParser()
        ap.add_argument('--suppress-cc', '-s', action="store_true",
                        default=False,
                        help='Don''t auto-cc anyone (for testing)')
        args = ap.parse_args("")

        stub_stdin(self, '')
        stub_stdouts(self)
        announce(self.config, self.ctx, args)

        letter = sys.stdout.getvalue()
        debug(letter)
        self.assertNotEqual(letter, '')


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
        ctx = SrtContext(make_args('v4.4.13-rt3', 'v4.4.14-rt4'),
                         path=self.work_tree)

        # step8_push()
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt])

        stub_stdin(self, 'y')
        stub_stdouts(self)
        push(self.config, ctx)


    def setup_add_patches(self, start, stop):
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt_next])
        cmd(['git', 'reset', '--hard', self.branch_rt])

        for n in range(start, stop):
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
            cmd(['git', 'commit', '-m', msg])


    def setUp(self):
        super().setUp()

        self.setup_release()

        cmd(['git', 'checkout', self.branch_rt_next])
        self.setup_add_patches(1, 3)

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
        self.ctx = SrtContext(make_args('v4.4.14-rt4', 'v4.4.14-rt5-rc1'),
                              path=self.work_tree)

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

        ap = argparse.ArgumentParser()
        ap.add_argument('--suppress-cc', '-s', action="store_true",
                        default=False,
                        help='Don''t auto-cc anyone (for testing)')
        args = ap.parse_args("")

        stub_stdin(self, 'n')
        stub_stdouts(self)
        announce(self.config, self.ctx, args)
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
            debug(letter)
            self.assertTrue(letter.find('Linux ' + str(self.ctx.new_tag)))


class TestSrtContext(TestReleaseCanditate):
    def setUp(self):
        super().setUp()

    def step0_get_context(self):
        ap = argparse.ArgumentParser()
        sap = ap.add_subparsers(dest='cmd')
        prs = sap.add_parser('create')
        prs.add_argument('OLD_TAG')
        prs.add_argument('NEW_TAG')

        args = ap.parse_args(['create',
                              'v4.4.13-rt3',
                              'v4.4.14-rt4'])
        ctx = SrtContext(args)
        self.assertTrue(ctx)
        print(ctx)


class TestNoTagsOneMergeCanditate(TestSrtBase):
    # Test if 'srt create' works if only one stable release
    # has been merged. No intermedeated commits and tags

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
        cmd(['git', 'checkout', self.branch_rt])
        self.ctx = SrtContext(make_args(), path=self.work_tree)

        create(self.config, self.ctx)

        path = self.work_tree + '/patches/v4.4.14-rt4/'
        files = [path + 'patch-4.4.14-rt4.patch.xz',
                 path + 'patches-4.4.14-rt4.tar.xz']
        for f in files:
            self.assertEqual(os.path.isfile(f), True)


class TestNoTagsManyMergesCanditate(TestSrtBase):
    # Test if 'srt create' works if more than one stable release
    # has been merged and some intermediates commits have been
    # done

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

    def step5_new_stable_release(self):
        self.setup_stable_new_release('4.4.15')
        self.do_merge('4.4.15')

    def step6_commit2(self):
        stub_stdin(self, 'y')
        stub_stdouts(self)
        commit(self.config, rc=False)
        ans = 'git commit -m Linux 4.4.15-rt5 \nOK to commit? (y/n): '
        self.assertEqual(sys.stdout.getvalue(), ans)
        lines = cmd(['git', 'show'])
        self.assertTrue(find_string(lines, 'Linux 4.4.15-rt5'))

    def step7_tag(self):
        stub_stdin(self, 'y')
        stub_stdouts(self)
        tag(self.config)
        self.assertTrue(tag_exists('v4.4.15-rt5'))

    def step8_commit_rebase2(self):
        cmd(['git', 'checkout', self.branch_rt_rebase])
        cmd(['git', 'rebase', 'v4.4.15'])

        stub_stdin(self, 'y')
        stub_stdouts(self)
        commit(self.config, rc=False)
        ans = 'git commit -m Linux 4.4.15-rt5 REBASE\nOK to commit? (y/n): '
        self.assertEqual(sys.stdout.getvalue(), ans)
        lines = cmd(['git', 'show'])
        self.assertTrue(find_string(lines, 'Linux 4.4.15-rt5 REBASE'))

    def step9_tag_rebase2(self):
        stub_stdin(self, 'y')
        stub_stdouts(self)
        tag(self.config)
        self.assertTrue(tag_exists('v4.4.15-rt5-rebase'))

    def step10_create(self):
        cmd(['git', 'checkout', self.branch_rt])
        self.ctx = SrtContext(make_args(), path=self.work_tree)

        create(self.config, self.ctx)

        path = self.work_tree + '/patches/v4.4.15-rt5/'
        files = [path + 'patch-4.4.15-rt5.patch.xz',
                 path + 'patches-4.4.15-rt5.tar.xz']
        for f in files:
            self.assertEqual(os.path.isfile(f), True)

    def step11_push(self):
        os.chdir(self.work_tree)
        cmd(['git', 'checkout', self.branch_rt])

        stub_stdin(self, 'y')
        stub_stdouts(self)
        push(self.config, self.ctx)

        # XXX check if missing intermedeate tags are pushed as well


if __name__ == '__main__':
    import logging
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    unittest.main()
