#!/usr/bin/env python3
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
import os
import sys
from logging import debug

from stable_rt_tools.srt_util import (
    SrtState,
    get_last_tag,
    get_old_tag,
    get_remote_branch_name,
    read_srt_state,
    validate_srt_state,
)
from stable_rt_tools.srt_util_tag import Tag


def _read_and_validate_state(path: str) -> SrtState | None:
    state = read_srt_state(path)
    if not state:
        return None

    current_branch = get_remote_branch_name()
    err = validate_srt_state(state, current_branch)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)
    return state


class SrtContext:
    """OLD_TAG and NEW_TAG of a release and the files made for them.

    The tags come from the command line, the environment, the state of
    srt prep or the git history, in this order.
    """

    old_tag: Tag
    old_short_tag: str
    old_dir_patches: str
    old_dir_series: str
    old_dir_mails: str
    old_fln_patch: str
    old_fln_tar: str
    new_tag: Tag
    new_short_tag: str
    new_dir_patches: str
    new_dir_series: str
    new_dir_mails: str
    new_fln_patch: str
    new_fln_tar: str

    def __init__(self, args: argparse.Namespace | None,
                 path: str | None = None) -> None:
        self.path = path if path is not None else os.getcwd()

        state: SrtState | None = None
        if args and getattr(args, 'OLD_TAG', None):
            old_tag = args.OLD_TAG
        elif os.environ.get('OLD_TAG'):
            old_tag = os.environ['OLD_TAG']
        else:
            state = _read_and_validate_state(self.path)
            if state:
                old_tag = state['old_tag']
            else:
                old_tag = get_old_tag()

        if args and getattr(args, 'NEW_TAG', None):
            new_tag = args.NEW_TAG
        elif os.environ.get('NEW_TAG'):
            new_tag = os.environ['NEW_TAG']
        else:
            if state is None:
                state = _read_and_validate_state(self.path)
            if state:
                new_tag = state['new_tag']
            else:
                new_tag = get_last_tag(get_remote_branch_name())

        self._add_tag('old', old_tag)
        self._add_tag('new', new_tag)
        self.is_rc = self.new_tag.is_rc
        debug(self._dump())

    def _add_tag(self, prefix: str, tag: str) -> None:
        dir_patches = f'{self.path}/patches/{tag}'
        setattr(self, prefix + '_tag', Tag(tag))
        setattr(self, prefix + '_short_tag', tag[1:])
        setattr(self, prefix + '_dir_patches', dir_patches)
        setattr(self, prefix + '_dir_series', f'{dir_patches}/patches')
        setattr(self, prefix + '_dir_mails', f'{dir_patches}/mails')
        setattr(self, prefix + '_fln_patch',
                f'{dir_patches}/patch-{tag[1:]}.patch.xz')
        setattr(self, prefix + '_fln_tar',
                f'{dir_patches}/patches-{tag[1:]}.tar.xz')

    def get_files(self) -> list[str]:
        return [self.new_fln_patch, self.new_fln_tar]

    def get_old_files(self) -> list[str]:
        return [self.old_fln_patch, self.old_fln_tar]

    def _dump(self) -> str:
        return '\n' + '\n'.join(f'\t{key}: {val}'
                                for key, val in self.__dict__.items())
