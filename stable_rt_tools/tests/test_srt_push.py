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

import unittest
from unittest.mock import patch
from stable_rt_tools.srt_push import push


class DummyCtx:

    def __init__(self, new_tag, is_rc=False):
        self.new_tag = new_tag
        self.is_rc = is_rc


class DummyConfig(dict):

    def get(self, key, default=None):
        return super().get(key, default)

    def __getitem__(self, key):
        return super().__getitem__(key)

    def __contains__(self, key):
        return super().__contains__(key)

    def getboolean(self, key, fallback=None):
        if key == 'quilt_workflow':
            return True
        return fallback


def test_push_quilt_workflow():
    config = DummyConfig({'PRJ_GIT_TREE': 'origin'})
    ctx = DummyCtx('v6.12.39-rt11', is_rc=False)

    with patch('stable_rt_tools.srt_push.get_remote_branch_name',
               return_value='v6.12-rt'):
        with patch('stable_rt_tools.srt_push.confirm', return_value=True):
            calls = []

            def fake_cmd(args, verbose=False):
                calls.append(args)

            with patch('stable_rt_tools.srt_push.cmd', side_effect=fake_cmd):
                push(config, ctx)

            push_calls = [c for c in calls if c[0:2] == ['git', 'push']]
            assert push_calls, 'No git push calls made'
            found_branch = any(
                'v6.12-rt-patches' in c for c in push_calls[-1]
            )
            found_tag = any(
                'v6.12.39-rt11-patches' in c for c in push_calls[-1]
            )
            assert found_branch, 'Did not push -rt-patches branch'
            assert found_tag, 'Did not push -patches tag'


if __name__ == '__main__':
    unittest.main()
