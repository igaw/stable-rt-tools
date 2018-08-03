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


import re
import unittest


class TagParseError(Exception):
    pass


class TagAttrError(Exception):
    pass


class TagBaseError(Exception):
    pass


class Tag:
    def __init__(self, _tag):
        parts = _tag.split('-')
        m = re.match(r'^v([0-9]+)\.([0-9]+)\.([0-9]+)$', parts[0])
        if not m:
            raise(TagParseError('Failed to parse {0}'.format(parts[0])))
        self.major = int(m.group(1))
        self.minor = int(m.group(2))
        self.patch = int(m.group(3))

        self._order = []
        for p in parts[1:]:
            m = re.match('^([a-z]+)([0-9]+)$', p)
            if not m:
                raise(TagParseError('Failed to parse {0}'.format(p)))
            setattr(self, m.group(1), int(m.group(2)))
            self._order.append(m.group(1))

    def __getattr__(self, name):
        """Returns the attribute matching passed name."""
        value = self.__dict__.get(name)
        if not value:
            raise TagAttrError('No such attribute {0}'.format(name))
        return value

    def _build(self, fix):
        tag = 'v{0}.{1}.{2}'.format(self.major,
                                    self.minor,
                                    self.patch)
        for o in self._order:
            if fix == o:
                return tag
            tag = '{0}-{1}{2}'.format(tag, o, getattr(self, o))

        return str(tag)

    def prev(self, cur):
        try:
            i = self._order.index(cur) - 1
            if i == -1:
                return None
            return self._order[i]
        except ValueError:
            pass

    @property
    def is_rc(self):
        for o in self._order:
            if o == 'rc':
                return True
        return False

    @property
    def last(self):
        if not self._order:
            return None
        return self._order[-1]

    @property
    def base(self):
        """Return the tag upto -rt without trailing postfixes, e.g. -rc."""
        if 'rt' not in self._order:
            raise(TagBaseError('No rt base tag {0}'.format(str(self))))
        return self._build('rt')

    @property
    def rebase(self):
        return self._build(None) + '-rebase'

    def __str__(self):
        return self._build(None)


class TestTag(unittest.TestCase):
    def test_stable(self):
        tag = Tag('v4.4.144')
        self.assertEqual(str(tag), 'v4.4.144')

    def test_stable_base_exception(self):
        tag = Tag('v4.4.144')
        with self.assertRaises(TagBaseError):
            tag.base

    def test_stable_rebase(self):
        tag = Tag('v4.4.144')
        self.assertEqual(tag.rebase, 'v4.4.144-rebase')

    def test_stable_getattr(self):
        tag = Tag('v4.4.144')
        self.assertEqual(tag.major, 4)
        self.assertEqual(tag.minor, 4)
        self.assertEqual(tag.patch, 144)

    def test_stable_attr_exception(self):
        tag = Tag('v4.4.144')
        with self.assertRaises(TagAttrError):
            tag.foo

    def test_rt(self):
        tag = Tag('v4.4.144-rt134')
        self.assertEqual(str(tag), 'v4.4.144-rt134')

    def test_rt_base(self):
        tag = Tag('v4.4.144-rt134')
        self.assertEqual(tag.base, 'v4.4.144')

    def test_rt_getattr(self):
        tag = Tag('v4.4.144-rt134')
        self.assertEqual(tag.rt, 134)

    def test_cip(self):
        tag = Tag('v4.4.144-cip13-rt134')
        self.assertEqual(str(tag), 'v4.4.144-cip13-rt134')

    def test_cip_base(self):
        tag = Tag('v4.4.144-cip13-rt134')
        self.assertEqual(tag.base, 'v4.4.144-cip13')

    def test_cip_getattr(self):
        tag = Tag('v4.4.144-cip13-rt134')
        self.assertEqual(tag.cip, 13)
        self.assertEqual(tag.rt, 134)

    def test_rc(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(str(tag), 'v4.4.144-cip13-rt134-rc1')

    def test_rc_base(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.base, 'v4.4.144-cip13')

    def test_rc_getattr(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.rt, 134)
        self.assertEqual(tag.cip, 13)
        self.assertEqual(tag.rc, 1)

    def test_rc_last(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.last, 'rc')

    def test_rc_hierarchy(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        order = {'rc': 'rt',
                 'rt': 'cip',
                 'cip': None}
        for k, v in order.items():
            self.assertEqual(tag.prev(k), v)

    def test_is_rc(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.is_rc, True)

    def test_is_not_rc(self):
        tag = Tag('v4.4.144-cip13-rt134')
        self.assertEqual(tag.is_rc, False)


if __name__ == '__main__':
    unittest.main()
