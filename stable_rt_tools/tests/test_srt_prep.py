#!/usr/bin/env python3
#
# srt - stable rt tooling
#
# Copyright (c) Daniel Wagner <wagi@monom.org>, 2026
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
from unittest import TestCase
from unittest.mock import patch

from stable_rt_tools.srt_prep import prep, execute


class TestPrepState(TestCase):
    def test_prep_writes_state(self):
        config = {'quilt_workflow': 'true'}
        with patch('stable_rt_tools.srt_prep.os.getcwd',
                   return_value='/tmp/v6.12-rt'):
            with patch('stable_rt_tools.srt_prep.get_old_tag',
                       return_value='v6.12.79-rt17'):
                with patch('stable_rt_tools.srt_prep.get_remote_branch_name',
                           return_value='v6.12-rt'):
                    with patch('stable_rt_tools.srt_prep.get_last_rt_tag',
                               return_value='-rt17'):
                        with patch(
                            'stable_rt_tools.srt_prep.get_next_stable_version',
                            return_value='v6.12.89'
                        ):
                            with patch(
                                'stable_rt_tools.srt_prep.write_srt_state'
                            ) as write_state:
                                prep(config)
                                write_state.assert_called_once()
                                state = write_state.call_args[0][0]
                                self.assertEqual(
                                    state['old_tag'], 'v6.12.79-rt17')
                                self.assertEqual(
                                    state['new_tag'], 'v6.12.89-rt18')
                                self.assertEqual(
                                    state['workflow_branch'], 'v6.12-rt')

    def test_clear_state(self):
        args = argparse.Namespace(clear=True)
        with patch('stable_rt_tools.srt_prep.clear_srt_state') as clear_state:
            execute(args)
            clear_state.assert_called_once()
