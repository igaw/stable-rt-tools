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
    get_last_release,
    get_previous_release,
    get_remote_branch_name,
    read_srt_state,
    validate_srt_state,
)
from stable_rt_tools.srt_util_tag import Tag


def _read_and_validate_state(path: str) -> SrtState | None:
    state = read_srt_state(path)
    if not state:
        return None

    current_branch = get_remote_branch_name(path=path)
    err = validate_srt_state(state, current_branch)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)
    return state


def _given(args: argparse.Namespace | None, name: str) -> str | None:
    """The tag name given on the command line or in the environment."""
    tag = getattr(args, name, None) if args else None
    return tag or os.environ.get(name) or None


class SrtContext:
    """OLD_TAG and NEW_TAG of a release and the files made for them.

    The tags come from the command line, the environment, the state of
    srt prep or the git history, in this order. From the history, NEW_TAG
    is the last release (or release candidate) on the first parents of
    HEAD in path, OLD_TAG the release before NEW_TAG: HEAD is local and
    has the release once it is tagged, pushed or not. The release suffix
    is the one of the last release tag there (no srt.conf needed).
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

        old_tag = _given(args, 'OLD_TAG')
        new_tag = _given(args, 'NEW_TAG')
        if old_tag is None or new_tag is None:
            state = _read_and_validate_state(self.path)
            if state:
                old_tag = old_tag or state['old_tag']
                new_tag = new_tag or state['new_tag']
        if new_tag is None:
            # the release is tagged already (srt push clears the state):
            # the last one on HEAD, a release candidate too
            new_tag = get_last_release(rc=True, path=self.path)
            if new_tag is None:
                sys.exit('no release tag on HEAD, give the tags: '
                         'srt <command> OLD_TAG NEW_TAG')
        if old_tag is None:
            old_tag = get_previous_release(new_tag, self.path)

        self._add_tag('old', old_tag)
        self._add_tag('new', new_tag)
        self.is_rc = self.new_tag.is_rc
        debug(self._dump())

    def _add_tag(self, prefix: str, tag: str) -> None:
        dir_patches = release_dir(self.path, tag)
        setattr(self, prefix + '_tag', Tag(tag))
        setattr(self, prefix + '_short_tag', tag[1:])
        setattr(self, prefix + '_dir_patches', dir_patches)
        setattr(self, prefix + '_dir_series', f'{dir_patches}/patches')
        setattr(self, prefix + '_dir_mails', f'{dir_patches}/mails')
        patch, tar = release_files(self.path, tag)
        setattr(self, prefix + '_fln_patch', patch)
        setattr(self, prefix + '_fln_tar', tar)

    def get_files(self) -> list[str]:
        return [self.new_fln_patch, self.new_fln_tar]

    def get_old_files(self) -> list[str]:
        return [self.old_fln_patch, self.old_fln_tar]

    def _dump(self) -> str:
        return '\n' + '\n'.join(f'\t{key}: {val}'
                                for key, val in self.__dict__.items())


def release_dir(path: str, tag: str) -> str:
    """Where srt create puts the files of the release tag."""
    return f'{path}/patches/{tag}'


def release_files(path: str, tag: str) -> tuple[str, str]:
    """The patch and the tarball srt create makes for the release tag."""
    d = release_dir(path, tag)
    return (f'{d}/patch-{tag[1:]}.patch.xz', f'{d}/patches-{tag[1:]}.tar.xz')
