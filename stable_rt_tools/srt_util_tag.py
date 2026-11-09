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
    """A release tag like v6.12.116-rt22 or v6.12.116-rt22-rc1.

    Every suffix becomes an attribute: tag.rt == 22, tag.rc == 1, a suffix
    without number like -rebase is True.
    """

    def __init__(self, _tag: str) -> None:
        parts = _tag.split('-')
        m = re.match(r'^v([0-9]+)\.([0-9]+)\.([0-9]+)$', parts[0])
        if not m:
            raise TagParseError(f'Failed to parse {parts[0]}')
        self.major = int(m.group(1))
        self.minor = int(m.group(2))
        self.patch = int(m.group(3))

        self._order: list[str] = []
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
                raise TagParseError(f'Failed to parse {p}')

    def __getattr__(self, name: str) -> int | bool:
        """Returns the attribute matching passed name."""
        value: int | bool | None = self.__dict__.get(name)
        if value is None:
            raise TagAttrError(f'No such attribute {name}')
        return value

    def _build(self, fix: str | None) -> str:
        tag = f'v{self.major}.{self.minor}.{self.patch}'
        for o in self._order:
            if fix == o:
                return tag
            val = getattr(self, o)
            if val is True:
                tag = f'{tag}-{o}'
            else:
                tag = f'{tag}-{o}{val}'
        return tag

    def prev(self, cur: str) -> str | None:
        try:
            i = self._order.index(cur) - 1
        except ValueError:
            return None
        if i == -1:
            return None
        return self._order[i]

    @property
    def is_rc(self) -> bool:
        return 'rc' in self._order

    @property
    def last(self) -> str | None:
        if not self._order:
            return None
        return self._order[-1]

    @property
    def base(self) -> str:
        """Return the tag up to -rt without trailing postfixes like -rc,
        -patches."""
        if 'rt' not in self._order:
            raise TagBaseError(
                f'No rt base tag {self!s}'
            )
        return self._build('rt')

    @property
    def rebase(self) -> str:
        return self._build(None) + '-rebase'

    def __str__(self) -> str:
        return self._build(None)
