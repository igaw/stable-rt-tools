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
from argparse import Namespace
from typing import Any
from unittest.mock import patch

from stable_rt_tools.srt_announce import announce


class DummyCtx:
    def __init__(self, new_tag):
        self.is_rc = False
        self.new_tag = new_tag


class TestAnnounceQuiltWorkflow(unittest.TestCase):
    def test_announce_quilt_workflow_extracts_commit_message(self):
        # Setup dummy config with quilt_workflow enabled
        class DummyConfig(dict):
            def getboolean(self, key, fallback=None):
                if key == 'quilt_workflow':
                    return True
                return fallback
        config = DummyConfig()
        ctx: Any = DummyCtx('v6.12.66-rt15')
        args = Namespace(suppress_cc=False)

        # Patch subprocess.check_output to simulate git show
        commit_message = (
            '[ANNOUNCE] 6.12.66-rt15\n\nHello RT-list!\n...enjoy!'
        )
        with patch('subprocess.check_output',
                   return_value=commit_message) as mock_git_show:
            with patch('builtins.print') as mock_print:
                announce(config, ctx, args)
                # Should call git show with the correct tag
                mock_git_show.assert_called_with([
                    'git', 'show', '-s', '--format=%B',
                    'v6.12.66-rt15-patches'
                ], encoding='utf-8')
                # Should print the commit message
                mock_print.assert_any_call('Hello RT-list!\n...enjoy!')

    def test_announce_quilt_workflow_drops_trailers(self):
        class DummyConfig(dict):
            def getboolean(self, key, fallback=None):
                return key == 'quilt_workflow'
        commit_message = (
            '[ANNOUNCE] 6.12.116-rt22\n\nHello RT-list!\n\n'
            'Changes since 6.12.111-rt21:\n\n  - none\n\n'
            'Enjoy!\nDaniel\n\n'
            'Signed-off-by: Daniel Wagner <wagi@monom.org>\n')
        with patch('subprocess.check_output', return_value=commit_message), \
                patch('builtins.print') as mock_print:
            ctx: Any = DummyCtx('v6.12.116-rt22')
            announce(DummyConfig(), ctx, Namespace(suppress_cc=False))
        body = mock_print.call_args_list[-1].args[0]
        self.assertTrue(body.endswith('Enjoy!\nDaniel'))
        self.assertNotIn('Signed-off-by', body)


class TestStripTrailers(unittest.TestCase):
    def test_strip_trailers(self):
        from stable_rt_tools.srt_announce import strip_trailers
        self.assertEqual(strip_trailers(
            'body\n\nSigned-off-by: A <a@b>\nCc: C <c@d>\n'), 'body')
        # a last paragraph which isn't a trailer block stays
        self.assertEqual(strip_trailers('body\n\nEnjoy!\nDaniel'),
                         'body\n\nEnjoy!\nDaniel')
        self.assertEqual(strip_trailers('Signed-off-by: A <a@b>'),
                         'Signed-off-by: A <a@b>')


if __name__ == '__main__':
    unittest.main()
