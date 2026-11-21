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


from unittest import TestCase

from stable_rt_tools.srt_util_tag import Tag, TagParseError, release_in_message


class TestTag(TestCase):
    def test_stable(self):
        tag = Tag('v4.4.144')
        self.assertEqual(str(tag), 'v4.4.144')

    def test_stable_base_exception(self):
        tag = Tag('v4.4.144')
        with self.assertRaises(TagParseError):
            _ = tag.base

    def test_stable_rebase(self):
        tag = Tag('v4.4.144')
        self.assertEqual(tag.rebase, 'v4.4.144-rebase')

    def test_stable_getattr(self):
        tag = Tag('v4.4.144')
        self.assertEqual(tag.major, 4)
        self.assertEqual(tag.minor, 4)
        self.assertEqual(tag.patch, 144)

    def test_stable_no_suffix(self):
        tag = Tag('v4.4.144')
        self.assertIsNone(tag.get('foo'))
        self.assertIsNone(tag.rc)
        self.assertFalse(tag.has('foo'))
        self.assertFalse(tag.is_release)
        self.assertEqual(tag.flags, [])
        self.assertEqual(tag.localversion, '')

    def test_rt(self):
        tag = Tag('v4.4.144-rt134')
        self.assertEqual(str(tag), 'v4.4.144-rt134')

    def test_rt_base(self):
        tag = Tag('v4.4.144-rt134')
        self.assertEqual(tag.base, 'v4.4.144')

    def test_rt_getattr(self):
        tag = Tag('v4.4.144-rt134')
        self.assertEqual(tag.get('rt'), 134)

    def test_cip(self):
        tag = Tag('v4.4.144-cip13-rt134')
        self.assertEqual(str(tag), 'v4.4.144-cip13-rt134')

    def test_cip_base(self):
        tag = Tag('v4.4.144-cip13-rt134')
        self.assertEqual(tag.base, 'v4.4.144-cip13')

    def test_cip_getattr(self):
        tag = Tag('v4.4.144-cip13-rt134')
        self.assertEqual(tag.get('cip'), 13)
        self.assertEqual(tag.get('rt'), 134)

    def test_rc(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(str(tag), 'v4.4.144-cip13-rt134-rc1')

    def test_rc_base(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.base, 'v4.4.144-cip13')

    def test_rc_getattr(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.get('rt'), 134)
        self.assertEqual(tag.get('cip'), 13)
        self.assertEqual(tag.rc, 1)

    def test_rc_localversion(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.version, 'v4.4.144')
        self.assertEqual(tag.localversion, '-cip13-rt134-rc1')

    def test_is_rc(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.is_rc, True)

    def test_is_not_rc(self):
        tag = Tag('v4.4.144-cip13-rt134')
        self.assertEqual(tag.is_rc, False)

    def test_suffix_and_number(self):
        for name, suffix, number, base in (
                ('v6.12.116-rt22', 'rt', 22, 'v6.12.116'),
                ('v6.12.116-rt22-patches', 'rt', 22, 'v6.12.116'),
                ('v6.12.116-rt22-rc1', 'rt', 22, 'v6.12.116'),
                ('v4.4.144-cip13-rt134-rc1', 'rt', 134, 'v4.4.144-cip13'),
                ('v6.1.5-foo3', 'foo', 3, 'v6.1.5'),
                ('v6.1.5-foo3-rebase', 'foo', 3, 'v6.1.5')):
            tag = Tag(name)
            self.assertEqual((tag.suffix, tag.number, tag.base),
                             (suffix, number, base), name)
        with self.assertRaises(TagParseError):
            _ = Tag('v4.4.144-rebase').base

    def test_flags(self):
        tag = Tag('v6.12.116-rt22-rebase')
        self.assertEqual(tag.flags, ['rebase'])
        self.assertTrue(tag.has('rebase'))
        self.assertTrue(tag.has('rt'))
        self.assertFalse(tag.has('patches'))
        self.assertIsNone(tag.get('rebase'))
        self.assertFalse(tag.is_rc)
        self.assertEqual(Tag('v6.12.116-rt22-patches').flags, ['patches'])

    def test_rc_number(self):
        self.assertEqual(Tag('v6.12.116-rt22-rc3').rc, 3)
        self.assertIsNone(Tag('v6.12.116-rt22').rc)

    def test_is_release(self):
        for name, release in (
                ('v6.12.116-rt22', True),
                ('v6.12.116-rt22-rc1', True),
                ('v6.12.116-rt22-rebase', True),
                ('v4.4.144-cip13-rt134-rc1', True),
                ('v6.12.116', False),
                ('v6.12.116-rebase', False),
                ('v2.6.39-rc7', False)):
            self.assertEqual(Tag(name).is_release, release, name)

    def test_parse(self):
        self.assertEqual(Tag.parse('v6.12.116-rt22'), Tag('v6.12.116-rt22'))
        for name in ('6.12.116-rt22', 'v6.12-rt22', 'v6.12.116-RT22',
                     'v6.12.116-rt22-', 'v6.12.116-22', ''):
            self.assertIsNone(Tag.parse(name), name)
            with self.assertRaises(TagParseError):
                Tag(name)
        self.assertTrue(issubclass(TagParseError, ValueError))

    def test_eq_hash(self):
        self.assertEqual(Tag('v6.12.116-rt22'), Tag('v6.12.116-rt22'))
        self.assertNotEqual(Tag('v6.12.116-rt22'), Tag('v6.12.116-rt23'))
        self.assertNotEqual(Tag('v6.12.116-rt22'), 'v6.12.116-rt22')
        self.assertEqual(len({Tag('v6.12.116-rt22'),
                              Tag('v6.12.116-rt22')}), 1)
        self.assertEqual(repr(Tag('v6.12.116-rt22')), "Tag('v6.12.116-rt22')")

    def test_rebase_of_rc(self):
        tag = Tag('v4.4.144-cip13-rt134-rc1')
        self.assertEqual(tag.rebase, 'v4.4.144-cip13-rt134-rc1-rebase')


class TestReleaseInMessage(TestCase):
    def test_release(self):
        for msg, name, line in (
                ('Linux 6.12.118-rt24', 'v6.12.118-rt24',
                 'Linux 6.12.118-rt24'),
                ('Linux 6.12.118-rt24 REBASE', 'v6.12.118-rt24-rebase',
                 'Linux 6.12.118-rt24 REBASE'),
                ('Linux 4.4.14-rt5-rc1\n\nSigned-off-by: A <a@b>\n',
                 'v4.4.14-rt5-rc1', 'Linux 4.4.14-rt5-rc1'),
                ('Linux 4.4.144-cip13-rt134', 'v4.4.144-cip13-rt134',
                 'Linux 4.4.144-cip13-rt134')):
            found = release_in_message(msg)
            assert found is not None, msg
            self.assertEqual((str(found[0]), found[1]), (name, line))

    def test_no_release(self):
        for msg in ('Add -rt patches', 'Linux 6.12.118',
                    'Merge tag \'v6.12.118\' into v6.12-rt', ''):
            self.assertIsNone(release_in_message(msg), msg)



class TestUpstreamRelease(TestCase):
    def test_upstream(self):
        from stable_rt_tools.srt_util_tag import is_upstream_release
        for tag in ('v6.12.118', 'v4.4.144', 'v6.1.0'):
            self.assertTrue(is_upstream_release(tag), tag)
            self.assertTrue(Tag(tag).is_upstream, tag)
        for tag in ('v6.12.118-rt24', 'v6.12.118-rt24-rebase',
                    'v6.12.118-rt24-patches', 'v6.12.118-rt24-rc1',
                    'v4.4.144-cip13', 'v6.13-rc1', 'v6.12', '6.12.118',
                    'v6.12.118 ', ''):
            self.assertFalse(is_upstream_release(tag), tag)
