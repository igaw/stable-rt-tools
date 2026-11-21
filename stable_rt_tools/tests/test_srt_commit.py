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


import os
import tempfile
from shutil import rmtree
from unittest import TestCase

from stable_rt_tools.srt_commit import get_kernel_version

MAKEFILE = '''# SPDX-License-Identifier: GPL-2.0
VERSION = 6
PATCHLEVEL = 12
SUBLEVEL = {sublevel}
EXTRAVERSION ={extraversion}
NAME = Baby Opossum Posse

# *DOCUMENTATION*
# VERSION = 1 later in the Makefile doesn't count
VERSION = 1
'''


class TestGetKernelVersion(TestCase):
    def setUp(self):
        self.tree = tempfile.mkdtemp()

    def tearDown(self):
        rmtree(self.tree)

    def write(self, name, text):
        with open(os.path.join(self.tree, name), 'w') as f:
            f.write(text)

    def makefile(self, sublevel='118', extraversion=''):
        self.write('Makefile', MAKEFILE.format(sublevel=sublevel,
                                               extraversion=extraversion))

    def test_stable(self):
        # no localversion file: the upstream version
        self.makefile()
        self.assertEqual(get_kernel_version(self.tree), '6.12.118')

    def test_release(self):
        self.makefile()
        self.write('localversion-rt', '-rt24\n')
        self.assertEqual(get_kernel_version(self.tree), '6.12.118-rt24')

    def test_release_candidate(self):
        self.makefile()
        self.write('localversion-rt', '-rt24-rc1\n')
        self.assertEqual(get_kernel_version(self.tree), '6.12.118-rt24-rc1')

    def test_extraversion(self):
        # a mainline release candidate, SUBLEVEL 0 stays
        self.makefile(sublevel='0', extraversion=' -rc1')
        self.write('localversion-rt', '-rt1\n')
        self.assertEqual(get_kernel_version(self.tree), '6.12.0-rc1-rt1')

    def test_localversion_files(self):
        # all of them in sorted order, without backups, no directories
        self.makefile()
        self.write('localversion-rt', '-rt24\n')
        self.write('localversion-cip', '-cip13\n\n')
        self.write('localversion-rt~', '-rt23\n')
        os.mkdir(os.path.join(self.tree, 'localversion-dir'))
        self.assertEqual(get_kernel_version(self.tree),
                         '6.12.118-cip13-rt24')

    def test_no_version(self):
        self.write('Makefile', 'all:\n')
        with self.assertRaises(SystemExit):
            get_kernel_version(self.tree)
