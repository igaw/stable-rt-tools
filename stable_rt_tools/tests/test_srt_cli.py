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
import unittest
from unittest import mock

from stable_rt_tools import srt_util
from stable_rt_tools.srt import srt_get_argparser


def parse(*argv):
    return srt_get_argparser().parse_args(list(argv))


class TestYes(unittest.TestCase):

    def test_default_no(self):
        self.assertFalse(getattr(parse('push'), 'yes', False))
        self.assertFalse(getattr(parse('quilt', 'queue'), 'yes', False))

    def test_before_and_after_the_command(self):
        for argv in (('-y', 'push'), ('push', '-y'), ('--yes', 'upload'),
                     ('-y', 'quilt', 'undo'), ('quilt', 'undo', '--yes'),
                     ('quilt', '-y', 'rebase')):
            self.assertTrue(getattr(parse(*argv), 'yes', False), argv)

    def test_confirm(self):
        self.addCleanup(srt_util.set_assume_yes, False)
        srt_util.set_assume_yes(True)
        out = io.StringIO()
        # stdin is not read at all
        with mock.patch('sys.stdin', io.StringIO('n\n')), \
                mock.patch('sys.stdout', out):
            self.assertTrue(srt_util.confirm('OK to push?'))
        self.assertEqual(out.getvalue(), 'OK to push? (y/n): y (--yes)\n')
