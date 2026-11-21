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

import argparse
from unittest import TestCase
from unittest.mock import patch

from stable_rt_tools.srt_util_context import SrtContext, release_files


def make_args(old_tag=None, new_tag=None):
    return argparse.Namespace(OLD_TAG=old_tag, NEW_TAG=new_tag)


class TestSrtContext(TestCase):
    def test_tag(self):
        ctx = SrtContext(make_args('v4.4.114-rt37', 'v4.4.115-rt38'), '/tmp')
        path = '/tmp/patches/v4.4.115-rt38'
        self.assertEqual(str(ctx.new_tag), 'v4.4.115-rt38')
        self.assertEqual(ctx.new.short, '4.4.115-rt38')
        self.assertEqual(ctx.new.dir, path)
        self.assertEqual(ctx.new.series_dir, path + '/patches')
        self.assertEqual(ctx.new.mails_dir, path + '/mails')
        self.assertEqual(ctx.new.patch_file,
                         path + '/patch-4.4.115-rt38.patch.xz')
        self.assertEqual(ctx.new.tar_file,
                         path + '/patches-4.4.115-rt38.tar.xz')

    def test_is_rc(self):
        ctx = SrtContext(
            make_args('v4.4.115-rt38', 'v4.4.115-rt39-rc1'), '/tmp')
        path = '/tmp/patches/v4.4.115-rt39-rc1/'
        files = [path + 'patch-4.4.115-rt39-rc1.patch.xz',
                 path + 'patches-4.4.115-rt39-rc1.tar.xz']
        self.assertEqual(ctx.new.files, tuple(files))

    def test_files(self):
        ctx = SrtContext(make_args('v4.4.115-rt38', 'v4.4.115-rt39'), '/tmp')

        path = '/tmp/patches/v4.4.115-rt39/'
        files = [path + 'patch-4.4.115-rt39.patch.xz',
                 path + 'patches-4.4.115-rt39.tar.xz']
        self.assertEqual(ctx.new.files, tuple(files))
        # srt upload removes the files of the old release from latest/
        self.assertEqual(ctx.old.files,
                         ('/tmp/patches/v4.4.115-rt38/'
                          'patch-4.4.115-rt38.patch.xz',
                          '/tmp/patches/v4.4.115-rt38/'
                          'patches-4.4.115-rt38.tar.xz'))
        self.assertEqual(ctx.old.files, release_files('/tmp',
                                                      'v4.4.115-rt38'))

    def test_use_state_when_no_args_or_env(self):
        state = {
            'old_tag': 'v4.4.115-rt38',
            'new_tag': 'v4.4.115-rt39',
            'workflow_branch': 'v4.4-rt',
        }
        with patch('stable_rt_tools.srt_util_context.read_srt_state',
                   return_value=state), patch(
            'stable_rt_tools.srt_util_context.get_remote_branch_name',
            return_value='v4.4-rt-patches'
        ), patch('stable_rt_tools.srt_util_context.get_last_release',
                 return_value='v4.4.115-rt37') as last:
            ctx = SrtContext(make_args(), '/tmp')
            last.assert_not_called()
            self.assertEqual(str(ctx.old_tag), 'v4.4.115-rt38')
            self.assertEqual(str(ctx.new_tag), 'v4.4.115-rt39')

    def test_after_push_without_state(self):
        # srt push cleared the state, the new release is the last one
        # on HEAD: the old one is the release before it
        m = 'stable_rt_tools.srt_util_context.'
        with patch.dict('os.environ', {}, clear=True), \
                patch(m + 'read_srt_state', return_value=None), \
                patch(m + 'get_last_release',
                      return_value='v6.12.118-rt24') as last, \
                patch(m + 'get_previous_release',
                      return_value='v6.12.117-rt23') as previous:
            ctx = SrtContext(make_args(), '/tmp')
            last.assert_called_once_with(rc=True, path='/tmp')
            previous.assert_called_once_with('v6.12.118-rt24', '/tmp')
            self.assertEqual(str(ctx.old_tag), 'v6.12.117-rt23')
            self.assertEqual(str(ctx.new_tag), 'v6.12.118-rt24')

    def test_new_tag_given_old_tag_from_history(self):
        m = 'stable_rt_tools.srt_util_context.'
        with patch.dict('os.environ', {}, clear=True), \
                patch(m + 'read_srt_state', return_value=None), \
                patch(m + 'get_last_release') as last, \
                patch(m + 'get_previous_release',
                      return_value='v6.12.117-rt23') as previous:
            ctx = SrtContext(make_args(new_tag='v6.12.118-rt24-rc1'),
                             '/tmp')
            last.assert_not_called()
            previous.assert_called_once_with('v6.12.118-rt24-rc1', '/tmp')
            self.assertEqual(str(ctx.old_tag), 'v6.12.117-rt23')
            self.assertTrue(ctx.is_rc)

    def test_no_release_on_head(self):
        m = 'stable_rt_tools.srt_util_context.'
        with patch.dict('os.environ', {}, clear=True), \
                patch(m + 'read_srt_state', return_value=None), \
                patch(m + 'get_last_release', return_value=None), \
                self.assertRaises(SystemExit):
            SrtContext(make_args(), '/tmp')

    def test_tags_given_are_taken_as_they_are(self):
        m = 'stable_rt_tools.srt_util_context.'
        with patch(m + 'get_previous_release') as previous:
            ctx = SrtContext(make_args('v6.12.118-rt24', 'v6.12.118-rt24'),
                             '/tmp')
            previous.assert_not_called()
            self.assertEqual(str(ctx.old_tag), 'v6.12.118-rt24')

    def test_cli_and_env_precedence_over_state(self):
        state = {
            'old_tag': 'v4.4.115-rt38',
            'new_tag': 'v4.4.115-rt39',
            'workflow_branch': 'v4.4-rt',
        }
        with patch('stable_rt_tools.srt_util_context.read_srt_state',
                   return_value=state), patch(
            'stable_rt_tools.srt_util_context.get_remote_branch_name',
            return_value='v4.4-rt'
        ), patch('stable_rt_tools.srt_util_context.os.environ',
                   {'OLD_TAG': 'v4.4.115-rt40'}):
            ctx = SrtContext(
                make_args(old_tag='v4.4.115-rt41',
                          new_tag='v4.4.115-rt42'),
                '/tmp')
            self.assertEqual(str(ctx.old_tag), 'v4.4.115-rt41')
            self.assertEqual(str(ctx.new_tag), 'v4.4.115-rt42')

    def test_stale_state_fails(self):
        state = {
            'old_tag': 'v4.4.115-rt38',
            'new_tag': 'v4.4.115-rt39',
            'workflow_branch': 'v4.4-rt',
        }
        with patch('stable_rt_tools.srt_util_context.read_srt_state',
                   return_value=state), patch(
            'stable_rt_tools.srt_util_context.get_remote_branch_name',
            return_value='v6.12-rt'
        ), self.assertRaises(SystemExit):
            SrtContext(make_args(), '/tmp')

    def test_default_path_is_cwd_at_call_time(self):
        import os
        import tempfile

        old = os.getcwd()
        tmp = os.path.realpath(tempfile.gettempdir())
        try:
            os.chdir(tmp)
            ctx = SrtContext(make_args('v4.4.114-rt37', 'v4.4.115-rt38'))
        finally:
            os.chdir(old)
        self.assertEqual(ctx.path, tmp)
