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
import os
import unittest
from subprocess import CalledProcessError
from unittest.mock import patch

from stable_rt_tools.srt_quilt import quilt, execute, _quilt_env

_QUILT_PATCHES = '/some/patches/dir'
_STATE = {'quilt_patches': _QUILT_PATCHES}


def test_quilt_env_uses_state():
    with patch('stable_rt_tools.srt_quilt.read_srt_state',
               return_value=_STATE):
        env = _quilt_env()
    assert env['QUILT_PATCHES'] == _QUILT_PATCHES


def test_quilt_env_fallback_when_no_state():
    with patch('stable_rt_tools.srt_quilt.read_srt_state', return_value=None):
        env = _quilt_env()
    assert env == os.environ.copy()


def _assert_quilt_patch_env(calls):
    for c in calls:
        env = c.kwargs.get('env') or (c.args[1] if len(c.args) > 1 else None)
        assert env is not None, 'cmd called without env kwarg'
        assert env.get('QUILT_PATCHES') == _QUILT_PATCHES


def test_quilt_runs_expected_sequence():
    side_effects = [
        '',  # quilt next
        '',  # quilt push
        '',  # quilt refresh
        '',  # quilt next
        '',  # quilt push
        '',  # quilt refresh
        CalledProcessError(1, ['quilt', 'next']),  # end of series
        '',  # final quilt refresh
        '',  # quilt pop -a
    ]
    with patch('stable_rt_tools.srt_quilt.read_srt_state',
               return_value=_STATE):
        with patch('stable_rt_tools.srt_quilt.cmd',
                   side_effect=side_effects) as c:
            with patch('stable_rt_tools.srt_quilt.localversion_inc') as lv_inc:
                quilt('localversion-rt')
                lv_inc.assert_called_once_with('localversion-rt')
                assert [ca.args[0] for ca in c.call_args_list] == [
                    ['quilt', 'next'],
                    ['quilt', 'push'],
                    ['quilt', 'refresh'],
                    ['quilt', 'next'],
                    ['quilt', 'push'],
                    ['quilt', 'refresh'],
                    ['quilt', 'next'],
                    ['quilt', 'refresh'],
                    ['quilt', 'pop', '-a'],
                ]
                _assert_quilt_patch_env(c.call_args_list)


def test_quilt_returns_early_on_push_failure():
    side_effects = [
        '',  # quilt next
        CalledProcessError(1, ['quilt', 'push']),  # patch apply failure
    ]
    with patch('stable_rt_tools.srt_quilt.read_srt_state',
               return_value=_STATE):
        with patch('stable_rt_tools.srt_quilt.cmd',
                   side_effect=side_effects) as c:
            with patch('stable_rt_tools.srt_quilt.localversion_inc') as lv_inc:
                with unittest.TestCase().assertRaises(CalledProcessError):
                    quilt('localversion-rt')
                lv_inc.assert_not_called()
                assert [ca.args[0] for ca in c.call_args_list] == [
                    ['quilt', 'next'],
                    ['quilt', 'push'],
                ]
                _assert_quilt_patch_env(c.call_args_list)


class TestQuiltExecute(unittest.TestCase):
    def test_execute(self):
        args = argparse.Namespace(localversion='localversion-rt')
        with patch('stable_rt_tools.srt_quilt.quilt') as q:
            execute(args)
            q.assert_called_once_with('localversion-rt')


if __name__ == '__main__':
    unittest.main()
