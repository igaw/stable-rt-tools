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


import os
import unittest

from srt_util_tag import Tag


class SrtContext:
    def __init__(self):
        self.is_rc = False
        self.fln_incr = None

    def add_tag(self, prefix, tag):
        t = Tag(tag)
        dir_patches = '{0}/patches/{1}'.format(os.getcwd(), tag)
        dir_series = '{0}/patches/{1}/patches'.format(os.getcwd(), tag)
        fln_patch = '{0}/patch-{1}.patch.xz'.format(dir_patches, tag[1:])
        fln_tar = '{0}/patches-{1}.tar.xz'.format(dir_patches, tag[1:])

        setattr(self, prefix + '_tag', t)
        setattr(self, prefix + '_short_tag', tag[1:])
        setattr(self, prefix + '_dir_patches', dir_patches)
        setattr(self, prefix + '_dir_series', dir_series)
        setattr(self, prefix + '_fln_patch', fln_patch)
        setattr(self, prefix + '_fln_tar', fln_tar)

    def init(self):
        if self.old_tag.base == self.new_tag.base:
            postfix = '-rt{0}'.format(self.new_tag.rt)
            if self.new_tag.is_rc:
                postfix = '-rt{0}-rc{1}'.format(self.new_tag.rt,
                                                self.new_tag.rc)
            self.fln_incr = ('{0}/patch-{1}{2}.patch.xz'.
                             format(self.new_dir_patches,
                                    self.old_short_tag,
                                    postfix))
            self.is_rc = self.new_tag.is_rc

    def __getattr__(self, name):
        """Returns the attribute matching passed name."""
        value = self.__dict__.get(name)
        if not value:
            raise AttributeError('No such attribute {0}'.format(name))
        return value

    def get_files(self):
        files = [self.new_fln_patch, self.new_fln_tar]
        if self.fln_incr:
            files.append(self.fln_incr)
        return files

    def dump(self):
        out = '\n'
        for key, val in self.__dict__.items():
            out = out + '\t{0}: {1}\n'.format(key, val)
        out = out[:-1]
        return out


class TestSrtContext(unittest.TestCase):
    def test_tag(self):
        ctx = SrtContext()
        ctx.add_tag('new', 'v4.4.115-rt38')
        self.assertEqual(str(ctx.new_tag), 'v4.4.115-rt38')
        self.assertEqual(ctx.new_short_tag, '4.4.115-rt38')
        self.assertEqual(ctx.new_dir_patches,
                         os.getcwd() + '/patches/v4.4.115-rt38')
        self.assertEqual(ctx.new_dir_series,
                         os.getcwd() + '/patches/v4.4.115-rt38/patches')
        self.assertEqual(ctx.new_fln_patch,
                         os.getcwd() +
                         '/patches/v4.4.115-rt38/patch-4.4.115-rt38.patch.xz')
        self.assertEqual(ctx.new_fln_tar,
                         os.getcwd() +
                         '/patches/v4.4.115-rt38/patches-4.4.115-rt38.tar.xz')

    def test_incr(self):
        ctx = SrtContext()
        ctx.add_tag('old', 'v4.4.115-rt38')
        ctx.add_tag('new', 'v4.4.115-rt39')
        ctx.init()
        fname = (os.getcwd() +
                 '/patches/v4.4.115-rt39/' +
                 'patch-4.4.115-rt38-rt39.patch.xz')
        self.assertEqual(ctx.fln_incr, fname)

    def test_is_rc(self):
        ctx = SrtContext()
        ctx.add_tag('old', 'v4.4.115-rt38')
        ctx.add_tag('new', 'v4.4.115-rt39-rc1')
        ctx.init()
        fname = (os.getcwd() +
                 '/patches/v4.4.115-rt39-rc1/' +
                 'patch-4.4.115-rt38-rt39-rc1.patch.xz')
        self.assertEqual(ctx.fln_incr, fname)
        self.assertEqual(ctx.is_rc, True)

    def test_get_files(self):
        ctx = SrtContext()
        ctx.add_tag('old', 'v4.4.115-rt38')
        ctx.add_tag('new', 'v4.4.115-rt39')
        ctx.init()

        path = os.getcwd() + '/patches/v4.4.115-rt39/'
        files = [path + 'patch-4.4.115-rt39.patch.xz',
                 path + 'patches-4.4.115-rt39.tar.xz',
                 path + 'patch-4.4.115-rt38-rt39.patch.xz']
        self.assertEqual(ctx.get_files(), files)


if __name__ == '__main__':
    unittest.main()
