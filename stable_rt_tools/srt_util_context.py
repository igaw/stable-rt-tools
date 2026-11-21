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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ReleaseFiles:
    """A release tag and where srt create puts its files: the directory
    patches/<tag> of the worktree, with the patch, the tarball, the
    exported series and the review mails of a release candidate."""

    tag: Tag
    # patches/<tag> in the worktree
    dir: str

    @classmethod
    def of(cls, path: str, tag: str) -> 'ReleaseFiles':
        """The files of the release tag in the worktree at path."""
        return cls(Tag(tag), release_dir(path, tag))

    @property
    def short(self) -> str:
        """The tag without the v: 6.12.118-rt24."""
        return str(self.tag)[1:]

    @property
    def series_dir(self) -> str:
        """Where srt create exports the series of patches."""
        return f'{self.dir}/patches'

    @property
    def mails_dir(self) -> str:
        """The review mails of a release candidate."""
        return f'{self.dir}/mails'

    @property
    def patch_file(self) -> str:
        return f'{self.dir}/patch-{self.short}.patch.xz'

    @property
    def tar_file(self) -> str:
        return f'{self.dir}/patches-{self.short}.tar.xz'

    @property
    def files(self) -> tuple[str, str]:
        """The patch and the tarball, the files srt sign and srt upload
        handle."""
        return (self.patch_file, self.tar_file)


class SrtContext:
    """OLD_TAG and NEW_TAG of a release and the files made for them.

    The tags come from the command line, the environment, the state of
    srt prep or the git history, in this order. From the history, NEW_TAG
    is the last release (or release candidate) on the first parents of
    HEAD in path, OLD_TAG the release before NEW_TAG: HEAD is local and
    has the release once it is tagged, pushed or not. The release suffix
    is the one of the last release tag there (no srt.conf needed).

    old and new are the ReleaseFiles of the tags in path: ctx.new.tag,
    ctx.new.patch_file, ...
    """

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

        self.old = ReleaseFiles.of(self.path, old_tag)
        self.new = ReleaseFiles.of(self.path, new_tag)
        self.is_rc: bool = self.new.tag.is_rc
        debug(self._dump())

    @property
    def old_tag(self) -> Tag:
        return self.old.tag

    @property
    def new_tag(self) -> Tag:
        return self.new.tag

    def _dump(self) -> str:
        return (f'\n\tpath: {self.path}\n\tis_rc: {self.is_rc}' +
                ''.join(f'\n\t{name}: {rel.tag} in {rel.dir}'
                        for name, rel in (('old', self.old),
                                          ('new', self.new))))


def release_dir(path: str, tag: str) -> str:
    """Where srt create puts the files of the release tag."""
    return f'{path}/patches/{tag}'


def release_files(path: str, tag: str) -> tuple[str, str]:
    """The patch and the tarball srt create makes for the release tag."""
    return ReleaseFiles.of(path, tag).files
