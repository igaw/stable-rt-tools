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
            raise TagParseError('Failed to parse {0}'.format(parts[0]))
        self.major = int(m.group(1))
        self.minor = int(m.group(2))
        self.patch = int(m.group(3))

        self._order = []
        for p in parts[1:]:
            m = re.match(r'^([a-z]+)([0-9]+)$', p)
            if m:
                key, val = m.group(1), int(m.group(2))
                setattr(self, key, val)
                self._order.append(key)
            elif re.match(r'^[a-z]+$', p):
                setattr(self, p, True)
                self._order.append(p)
            else:
                raise TagParseError('Failed to parse {0}'.format(p))

    def __getattr__(self, name):
        """Returns the attribute matching passed name."""
        value = self.__dict__.get(name)
        if value is None:
            raise TagAttrError('No such attribute {0}'.format(name))
        return value

    def _build(self, fix):
        tag = 'v{0}.{1}.{2}'.format(self.major,
                                    self.minor,
                                    self.patch)
        for o in self._order:
            if fix == o:
                return tag
            val = getattr(self, o)
            if val is True:
                tag = '{0}-{1}'.format(tag, o)
            else:
                tag = '{0}-{1}{2}'.format(tag, o, val)
        return tag

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
        return 'rc' in self._order

    @property
    def last(self):
        if not self._order:
            return None
        return self._order[-1]

    @property
    def base(self):
        """Return the tag up to -rt without trailing postfixes like -rc, -patches."""
        if 'rt' not in self._order:
            raise TagBaseError('No rt base tag {0}'.format(str(self)))
        return self._build('rt')

    @property
    def rebase(self):
        return self._build(None) + '-rebase'

    def __str__(self):
        return self._build(None)
