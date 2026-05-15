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

import argparse
import unittest
from subprocess import CalledProcessError
from unittest.mock import patch

from stable_rt_tools.srt_quilt import quilt, execute


def test_quilt_runs_expected_sequence():
    side_effects = [
        '',  # quilt push
        '',  # quilt refresh
        '',  # quilt push
        '',  # quilt refresh
        CalledProcessError(1, ['quilt', 'push']),  # end of series
        '',  # final quilt refresh
        '',  # quilt pop -a
    ]
    with patch('stable_rt_tools.srt_quilt.cmd', side_effect=side_effects) as c:
        with patch('stable_rt_tools.srt_quilt.localversion_inc') as lv_inc:
            quilt('localversion-rt')
            lv_inc.assert_called_once_with('localversion-rt')
            assert c.call_args_list == [
                (['quilt', 'push'],),
                (['quilt', 'refresh'],),
                (['quilt', 'push'],),
                (['quilt', 'refresh'],),
                (['quilt', 'push'],),
                (['quilt', 'refresh'],),
                (['quilt', 'pop', '-a'],),
            ]


def test_quilt_always_pops_on_failure():
    side_effects = [
        CalledProcessError(1, ['quilt', 'push']),  # no patches applied
        '',  # quilt pop -a from finally block
    ]
    with patch('stable_rt_tools.srt_quilt.cmd', side_effect=side_effects) as c:
        with patch('stable_rt_tools.srt_quilt.localversion_inc',
                   side_effect=RuntimeError('bump failed')):
            with unittest.TestCase().assertRaises(RuntimeError):
                quilt('localversion-rt')
            assert c.call_args_list == [
                (['quilt', 'push'],),
                (['quilt', 'pop', '-a'],),
            ]


class TestQuiltExecute(unittest.TestCase):
    def test_execute(self):
        args = argparse.Namespace(localversion='localversion-rt')
        with patch('stable_rt_tools.srt_quilt.quilt') as q:
            execute(args)
            q.assert_called_once_with('localversion-rt')


if __name__ == '__main__':
    unittest.main()
