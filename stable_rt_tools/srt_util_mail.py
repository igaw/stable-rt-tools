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


"""The replacements of the mail templates: the cover letter of a
release candidate, the announcement and the queue message."""

from email.utils import make_msgid

from stable_rt_tools.srt_util import Config, get_gpg_fingerprint, require
from stable_rt_tools.srt_util_context import SrtContext


def cover_letter_replacements(config: Config,
                              ctx: SrtContext) -> dict[str, object]:
    r = {
        "mail_to": require(config, 'MAIL_TO'),
        "major": ctx.new_tag.major,
        "minor": ctx.new_tag.minor,
        "patch": ctx.new_tag.patch,
        "new_version": ctx.new.short,
        "old_version": ctx.old.short,
        "prj_dir": require(config, 'PRJ_DIR'),
        "message_id": make_msgid(),
        "sender": require(config, 'SENDER'),
        "name": require(config, 'NAME'),
        # new_tag_rt: the name templates know from before 2.0
        "new_tag_rt": ctx.new_tag.number,
        "new_tag_number": ctx.new_tag.number,
        "gpg_key_fingerprint": get_gpg_fingerprint(config),
    }
    if ctx.is_rc:
        r["new_tag_rc"] = ctx.new_tag.rc
    return r
