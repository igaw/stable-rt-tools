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


class TagParseError(ValueError):
    """Not a tag, or no release tag where one is needed."""


# 'Linux 6.12.118-rt24' or 'Linux 6.12.118-rt24 REBASE' in the message of
# a release commit (srt commit)
_RELEASE_COMMIT = re.compile(r'^.*Linux ([0-9.]+[-a-z0-9]+)( REBASE)*')


class Tag:
    """A release tag like v6.12.116-rt22 or v6.12.116-rt22-rc1.

    After vX.Y.Z come the suffixes: numbered ones like -rt22, -cip13 or
    -rc1 and flags without number like -rebase or -patches.

    The release suffix is the last numbered suffix except -rc: rt in
    v4.4.144-cip13-rt134-rc1, foo in v6.1.5-foo3. Everything before it is
    the base the release is made on.
    """

    def __init__(self, tag: str) -> None:
        parts = tag.split('-')
        m = re.match(r'^v([0-9]+)\.([0-9]+)\.([0-9]+)$', parts[0])
        if not m:
            raise TagParseError(f'Failed to parse {parts[0]}')
        self.major = int(m.group(1))
        self.minor = int(m.group(2))
        self.patch = int(m.group(3))

        # the suffixes in order, None as number for a flag
        self._suffixes: list[tuple[str, int | None]] = []
        for p in parts[1:]:
            m = re.match(r'^([a-z]+)([0-9]+)?$', p)
            if not m:
                raise TagParseError(f'Failed to parse {p}')
            num = int(m.group(2)) if m.group(2) is not None else None
            self._suffixes.append((m.group(1), num))

    @classmethod
    def parse(cls, text: str) -> 'Tag | None':
        """The tag text, None if it is no tag."""
        try:
            return cls(text)
        except TagParseError:
            return None

    def _build(self, stop: str | None) -> str:
        tag = self.version
        for name, num in self._suffixes:
            if name == stop:
                break
            tag += f'-{name}' if num is None else f'-{name}{num}'
        return tag

    def get(self, name: str) -> int | None:
        """The number of the suffix name, e.g. 13 for cip in
        v4.4.144-cip13-rt134, None without it or for a flag."""
        for n, num in self._suffixes:
            if n == name and num is not None:
                return num
        return None

    def has(self, name: str) -> bool:
        """Whether the tag has the suffix name, numbered or a flag."""
        return any(n == name for n, _ in self._suffixes)

    @property
    def flags(self) -> list[str]:
        """The suffixes without number, e.g. ['rebase']."""
        return [n for n, num in self._suffixes if num is None]

    @property
    def rc(self) -> int | None:
        """N of a release candidate -rcN, None for no release candidate."""
        return self.get('rc')

    @property
    def is_rc(self) -> bool:
        return self.has('rc')

    @property
    def version(self) -> str:
        """The upstream version, e.g. v6.12.116."""
        return f'v{self.major}.{self.minor}.{self.patch}'

    @property
    def localversion(self) -> str:
        """Everything after the version, e.g. -rt22 for v6.12.116-rt22."""
        return str(self)[len(self.version):]

    @property
    def is_release(self) -> bool:
        """Whether the tag has a release suffix (-rt22), a release
        candidate, -rebase or -patches tag of a release too."""
        return any(n != 'rc' and num is not None
                   for n, num in self._suffixes)

    @property
    def suffix(self) -> str:
        """The release suffix, e.g. rt."""
        for name, num in reversed(self._suffixes):
            if name != 'rc' and num is not None:
                return name
        raise TagParseError(f'No release suffix in tag {self!s}')

    @property
    def number(self) -> int:
        """The release number, e.g. 22 for v6.12.116-rt22."""
        num = self.get(self.suffix)
        assert num is not None
        return num

    @property
    def base(self) -> str:
        """Return the tag up to the release suffix, without trailing
        postfixes like -rc, -patches."""
        return self._build(self.suffix)

    @property
    def rebase(self) -> str:
        return self._build(None) + '-rebase'

    def __str__(self) -> str:
        return self._build(None)

    def __repr__(self) -> str:
        return f'Tag({str(self)!r})'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tag):
            return NotImplemented
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))


def release_in_message(message: str) -> tuple[Tag, str] | None:
    """The release of a release commit (srt commit) and the line of its
    message naming it: v6.12.118-rt24 for 'Linux 6.12.118-rt24',
    v6.12.118-rt24-rebase for 'Linux 6.12.118-rt24 REBASE'. None for
    another commit."""
    for line in message.splitlines():
        m = _RELEASE_COMMIT.match(line)
        if not m:
            continue
        tag = Tag.parse('v' + m.group(1) + ('-rebase' if m.group(2) else ''))
        if tag is not None and tag.is_release:
            return tag, line
    return None
