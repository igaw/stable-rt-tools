#!/usr/bin/env python3i
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

import os
from unittest import TestCase

from stable_rt_tools.srt_util_context import SrtContext

class TestSrtContext(TestCase):
    def test_tag(self):
        ctx = SrtContext()
        ctx.add_tag('new', 'v4.4.115-rt38')
        self.assertEqual(str(ctx.new_tag), 'v4.4.115-rt38')
        self.assertEqual(ctx.new_short_tag, '4.4.115-rt38')
        self.assertEqual(ctx.new_dir_patches,
                         os.getcwd() + '/patches/v4.4.115-rt38')
        self.assertEqual(ctx.new_dir_series,
                         os.getcwd() + '/patches/v4.4.115-rt38/patches')
        self.assertEqual(ctx.new_dir_mails,
                         os.getcwd() + '/patches/v4.4.115-rt38/mails')
        self.assertEqual(ctx.new_fln_patch,
                         os.getcwd() +
                         '/patches/v4.4.115-rt38/patch-4.4.115-rt38.patch.xz')
        self.assertEqual(ctx.new_fln_tar,
                         os.getcwd() +
                         '/patches/v4.4.115-rt38/patches-4.4.115-rt38.tar.xz')

    def test_incr(self):
        ctx = SrtContext()
        ctx.add_tag('old', 'v4.4.115-rt38')
        ctx.add_tag('new', 'v4.4.115-rt39')
        ctx.init()
        fname = (os.getcwd() +
                 '/patches/v4.4.115-rt39/' +
                 'patch-4.4.115-rt38-rt39.patch.xz')
        self.assertEqual(ctx.fln_incr, fname)

    def test_is_rc(self):
        ctx = SrtContext()
        ctx.add_tag('old', 'v4.4.115-rt38')
        ctx.add_tag('new', 'v4.4.115-rt39-rc1')
        ctx.init()
        fname = (os.getcwd() +
                 '/patches/v4.4.115-rt39-rc1/' +
                 'patch-4.4.115-rt38-rt39-rc1.patch.xz')
        self.assertEqual(ctx.fln_incr, fname)
        self.assertEqual(ctx.is_rc, True)

    def test_get_files(self):
        ctx = SrtContext()
        ctx.add_tag('old', 'v4.4.115-rt38')
        ctx.add_tag('new', 'v4.4.115-rt39')
        ctx.init()

        path = os.getcwd() + '/patches/v4.4.115-rt39/'
        files = [path + 'patch-4.4.115-rt39.patch.xz',
                 path + 'patches-4.4.115-rt39.tar.xz',
                 path + 'patch-4.4.115-rt38-rt39.patch.xz']
        self.assertEqual(ctx.get_files(), files)
