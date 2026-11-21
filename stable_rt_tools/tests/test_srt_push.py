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
from typing import Any
from unittest.mock import patch

import pytest

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
    ctx: Any = DummyCtx('v6.12.39-rt11', is_rc=False)

    with patch('stable_rt_tools.srt_push.get_remote_branch_name',
               return_value='v6.12-rt'):
        with patch('stable_rt_tools.srt_push.confirm', return_value=True):
            calls = []

            def fake_cmd(args, verbose=False):
                calls.append(args)

            with patch('stable_rt_tools.srt_push.cmd', side_effect=fake_cmd):
                with patch(
                    'stable_rt_tools.srt_push.clear_srt_state'
                ) as clear_state:
                    push(config, ctx)
                    clear_state.assert_called_once()

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


def test_push_does_not_clear_state_when_cancelled():
    config = DummyConfig({'PRJ_GIT_TREE': 'origin'})
    ctx: Any = DummyCtx('v6.12.39-rt11', is_rc=False)

    with patch('stable_rt_tools.srt_push.get_remote_branch_name',
               return_value='v6.12-rt'):
        with patch('stable_rt_tools.srt_push.confirm', return_value=False):
            with patch('stable_rt_tools.srt_push.cmd'):
                with patch(
                    'stable_rt_tools.srt_push.clear_srt_state'
                ) as clear_state:
                    with pytest.raises(SystemExit, match='not pushed'):
                        push(config, ctx)
                    clear_state.assert_not_called()


def test_push_dry_run():
    config = DummyConfig({'PRJ_GIT_TREE': 'origin'})
    ctx: Any = DummyCtx('v6.12.39-rt11', is_rc=False)
    calls = []

    def fake_cmd(args, verbose=False):
        calls.append(args)

    with patch('stable_rt_tools.srt_push.get_remote_branch_name',
               return_value='v6.12-rt'), \
            patch('stable_rt_tools.srt_push.confirm') as confirm, \
            patch('stable_rt_tools.srt_push.cmd', side_effect=fake_cmd), \
            patch('stable_rt_tools.srt_push.clear_srt_state') as clear_state:
        push(config, ctx, dry_run=True)
        confirm.assert_not_called()
        clear_state.assert_not_called()
    # only git push -n
    assert len(calls) == 1
    assert calls[0][:3] == ['git', 'push', '-n']


def test_push_offers_announcement():
    from stable_rt_tools.srt_push import offer_announcement
    ctx: Any = DummyCtx('v6.12.39-rt11')
    config = DummyConfig({'MAILER': 'mutt -H {mail}'})
    with patch('stable_rt_tools.srt_push.interactive', return_value=True), \
            patch('stable_rt_tools.srt_push.confirm', return_value=True), \
            patch('stable_rt_tools.srt_announce.mail_announcement') as mail:
        offer_announcement(config, ctx)
        mail.assert_called_once_with(config, ctx)


def test_push_no_mailer_with_yes_or_no_terminal(capsys):
    from stable_rt_tools.srt_push import offer_announcement
    ctx: Any = DummyCtx('v6.12.39-rt11')
    config = DummyConfig({'MAILER': 'mutt -H {mail}'})
    with patch('stable_rt_tools.srt_push.interactive', return_value=False), \
            patch('stable_rt_tools.srt_push.confirm') as confirm, \
            patch('stable_rt_tools.srt_announce.mail_announcement') as mail:
        offer_announcement(config, ctx)
        confirm.assert_not_called()
        mail.assert_not_called()
    assert 'next: srt announce --mail' in capsys.readouterr().out


if __name__ == '__main__':
    unittest.main()
