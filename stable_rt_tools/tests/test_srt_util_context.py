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
import argparse
from unittest import TestCase

from stable_rt_tools.srt_util_context import SrtContext


def make_args(old_tag=None, new_tag=None):
    return argparse.Namespace(OLD_TAG=old_tag, NEW_TAG=new_tag)


class TestSrtContext(TestCase):
    def test_tag(self):
        ctx = SrtContext(make_args('v4.4.114-rt37', 'v4.4.115-rt38'), '/tmp')
        self.assertEqual(str(ctx.new_tag), 'v4.4.115-rt38')
        self.assertEqual(ctx.new_short_tag, '4.4.115-rt38')
        self.assertEqual(ctx.new_dir_patches,
                         '/tmp/patches/v4.4.115-rt38')
        self.assertEqual(ctx.new_dir_series,
                         '/tmp/patches/v4.4.115-rt38/patches')
        self.assertEqual(ctx.new_dir_mails,
                         '/tmp/patches/v4.4.115-rt38/mails')
        self.assertEqual(ctx.new_fln_patch,
                         '/tmp/patches/v4.4.115-rt38/patch-4.4.115-rt38.patch.xz')
        self.assertEqual(ctx.new_fln_tar,
                         '/tmp/patches/v4.4.115-rt38/patches-4.4.115-rt38.tar.xz')

    def test_is_rc(self):
        ctx = SrtContext(make_args('v4.4.115-rt38', 'v4.4.115-rt39-rc1'), '/tmp')
        path = '/tmp/patches/v4.4.115-rt39-rc1/'
        files = [path + 'patch-4.4.115-rt39-rc1.patch.xz',
                 path + 'patches-4.4.115-rt39-rc1.tar.xz']
        self.assertEqual(ctx.get_files(), files)

    def test_get_files(self):
        ctx = SrtContext(make_args('v4.4.115-rt38', 'v4.4.115-rt39'), '/tmp')

        path = '/tmp/patches/v4.4.115-rt39/'
        files = [path + 'patch-4.4.115-rt39.patch.xz',
                 path + 'patches-4.4.115-rt39.tar.xz']
        self.assertEqual(ctx.get_files(), files)
