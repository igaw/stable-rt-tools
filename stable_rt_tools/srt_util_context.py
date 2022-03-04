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


import os
from logging import debug

from stable_rt_tools.srt_util import (get_last_tag, get_old_tag,
                                      get_remote_branch_name)
from stable_rt_tools.srt_util_tag import Tag


class SrtContext:
    def __init__(self, args, path=os.getcwd()):
        self.is_rc = False
        self.path = path

        old_tag = None
        new_tag = None

        if args.OLD_TAG:
            old_tag = args.OLD_TAG
        else:
            old_tag = get_old_tag()

        if args.NEW_TAG:
            new_tag = args.NEW_TAG
        else:
            new_tag = get_last_tag(get_remote_branch_name())

        self._add_tag('old', old_tag)
        self._add_tag('new', new_tag)
        self._update_tags()
        debug(self._dump())

    def _add_tag(self, prefix, tag):
        t = Tag(tag)
        dir_patches = '{0}/patches/{1}'.format(self.path, tag)
        dir_series = '{0}/patches/{1}/patches'.format(self.path, tag)
        dir_mails = '{0}/patches/{1}/mails'.format(self.path, tag)
        fln_patch = '{0}/patch-{1}.patch.xz'.format(dir_patches, tag[1:])
        fln_tar = '{0}/patches-{1}.tar.xz'.format(dir_patches, tag[1:])

        setattr(self, prefix + '_tag', t)
        setattr(self, prefix + '_short_tag', tag[1:])
        setattr(self, prefix + '_dir_patches', dir_patches)
        setattr(self, prefix + '_dir_series', dir_series)
        setattr(self, prefix + '_dir_mails', dir_mails)
        setattr(self, prefix + '_fln_patch', fln_patch)
        setattr(self, prefix + '_fln_tar', fln_tar)

    def _update_tags(self):
        if self.old_tag.base == self.new_tag.base:
            self.is_rc = self.new_tag.is_rc

    def __getattr__(self, name):
        """Returns the attribute matching passed name."""
        value = self.__dict__.get(name)
        if not value:
            raise AttributeError('No such attribute {0}'.format(name))
        return value

    def get_files(self):
        return [self.new_fln_patch, self.new_fln_tar]

    def get_old_files(self):
        return [self.old_fln_patch, self.old_fln_tar]

    def _dump(self):
        out = '\n'
        for key, val in self.__dict__.items():
            out = out + '\t{0}: {1}\n'.format(key, val)
        out = out[:-1]
        return out
