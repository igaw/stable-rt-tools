#!/usr/bin/env python3
#
# srt - stable rt tooling
#
# Copyright (c) Daniel Wagner, 2026
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
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

MAIL = """\
From: Daniel <d@example.org>
Subject: [ANNOUNCE] v6.12.118-rt24
Date: Sat, 21 Nov 2026 10:00:00 -0000
Message-ID: <1@example.org>
To: LKML <lkml@example.org>,<rt@example.org>

Hello RT-list!

Enjoy!
"""


class TestStripTrailers(unittest.TestCase):
    def test_strip_trailers(self):
        from stable_rt_tools.srt_announce import strip_trailers
        self.assertEqual(strip_trailers(
            'body\n\nSigned-off-by: A <a@b>\nCc: C <c@d>\n'), 'body')
        # a last paragraph which isn't a trailer block stays
        self.assertEqual(strip_trailers('body\n\nEnjoy!\nDaniel'),
                         'body\n\nEnjoy!\nDaniel')
        self.assertEqual(strip_trailers('Signed-off-by: A <a@b>'),
                         'Signed-off-by: A <a@b>')


class TestMailer(unittest.TestCase):
    def test_mutt(self):
        from stable_rt_tools.srt_announce import mailer_command
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'announce')
            self.assertEqual(mailer_command('mutt -H {mail}', path, MAIL),
                             ['mutt', '-H', path])
            # no {body}: no body file
            self.assertFalse(os.path.exists(path + '.body'))

    def test_thunderbird(self):
        from stable_rt_tools.srt_announce import mailer_command
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'announce')
            argv = mailer_command(
                "thunderbird -compose \"to='{to}',subject='{subject}',"
                "from='{from}',message='{body}',format=text\"", path, MAIL)
            self.assertEqual(argv, [
                'thunderbird', '-compose',
                "to='LKML <lkml@example.org>,<rt@example.org>',"
                "subject='[ANNOUNCE] v6.12.118-rt24',"
                "from='Daniel <d@example.org>',"
                f"message='{path}.body',format=text"])
            with open(path + '.body') as f:
                self.assertEqual(f.read(), 'Hello RT-list!\n\nEnjoy!\n')

    def test_unknown_placeholder(self):
        from stable_rt_tools.srt_announce import mailer_command
        with self.assertRaises(SystemExit):
            mailer_command('mutt -H {file}', '/tmp/x', MAIL)

    def test_mail_announcement(self):
        from stable_rt_tools import srt_announce
        ctx = SimpleNamespace(new_tag='v6.12.118-rt24')
        with tempfile.TemporaryDirectory() as d, \
                patch.dict(os.environ, {'TMPDIR': d}), \
                patch.object(tempfile, 'tempdir', None), \
                patch.object(srt_announce, 'announcement',
                             return_value=MAIL), \
                patch.object(srt_announce, 'run') as run:
            run.return_value.returncode = 0
            srt_announce.mail_announcement(
                {'MAILER': 'mutt -H {mail}'}, ctx)  # type: ignore
            (path,), _ = run.call_args
            self.assertEqual(path[:2], ['mutt', '-H'])
            mail = path[2]
            self.assertEqual(os.path.basename(mail), 'announce-v6.12.118-rt24')
            self.assertEqual(os.path.dirname(os.path.dirname(mail)), d)
            with open(mail) as f:
                self.assertEqual(f.read(), MAIL)

    def test_mail_needs_mailer(self):
        from stable_rt_tools import srt_announce
        with self.assertRaises(SystemExit):
            srt_announce.mail_announcement(
                {}, SimpleNamespace(new_tag='v1-rt1'))  # type: ignore


if __name__ == '__main__':
    unittest.main()
