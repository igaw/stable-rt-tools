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
import re
import shlex
import sys
import tempfile
from email import message_from_string
from email.utils import make_msgid
from subprocess import DEVNULL, PIPE, run
from time import gmtime, strftime

from stable_rt_tools.srt_log import log_step
from stable_rt_tools.srt_review import announce_rc
from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    check_context,
    cmd,
    get_config,
    get_remote_branch_name,
    get_template_path,
    next_step,
)
from stable_rt_tools.srt_util_context import SrtContext
from stable_rt_tools.srt_util_mail import cover_letter_replacements


def get_announce_tmpl_path(config: Config) -> str:
    return get_template_path(config, 'ANNOUNCE', 'announce-srt.txt')


def strip_trailers(msg: str) -> str:
    """Remove the trailer block (Signed-off-by: ...) of a commit message."""
    paragraphs = msg.rstrip().split('\n\n')
    last = paragraphs[-1].splitlines()
    if len(paragraphs) > 1 and all(
            re.match(r'^[A-Za-z][A-Za-z0-9-]*: ', line) for line in last):
        paragraphs = paragraphs[:-1]
    return '\n\n'.join(paragraphs)


def delta_base(ctx: SrtContext) -> str:
    """Where the delta of a release starts: the old release with the new
    stable release merged in, as git merges it.

    The delta is then the series' own change, also across a stable
    update: patches before and after the merge, conflict resolutions
    (as conflict markers which are removed) and the release commit, but
    not the stable update.
    """
    old, base = str(ctx.old_tag), ctx.new_tag.base
    if ctx.old_tag.base == base:
        return old
    p = run(['git', 'merge-tree', '--write-tree', old, base],
            stdout=PIPE, stderr=DEVNULL, encoding='utf-8', cwd=ctx.path)
    # 1: the merge has conflicts, the tree contains the conflict markers
    if p.returncode not in (0, 1):
        sys.exit(f'git merge-tree {old} {base} failed')
    return p.stdout.splitlines()[0]


def changes(ctx: SrtContext) -> str:
    """The shortlog, diffstat and delta of the release."""
    new = str(ctx.new_tag)
    base = delta_base(ctx)

    return '\n'.join([
        cmd(['git', 'shortlog', '--first-parent', f'{ctx.old_tag}..{new}'],
            cwd=ctx.path),
        '---',
        cmd(['git', 'diff', '--stat', base, new], cwd=ctx.path),
        '---',
        cmd(['git', 'diff', base, new], cwd=ctx.path)])


def quilt_announcement(ctx: SrtContext) -> str:
    """The announcement of the queue commit, srt quilt queue wrote it."""
    msg = cmd(['git', 'show', '-s', '--format=%B',
               f'{ctx.new_tag}-patches^{{commit}}'], cwd=ctx.path)
    subject, _, body = msg.partition('\n')
    if not subject.startswith('[ANNOUNCE]'):
        sys.exit(f'{ctx.new_tag}-patches: the commit message is not an '
                 'announcement, it starts with ' + repr(subject))
    return strip_trailers(body.lstrip('\n'))


def announcement(config: Config, ctx: SrtContext) -> str:
    """The announcement of a release as mail, with the headers."""
    from stable_rt_tools.srt_util import is_quilt_workflow

    # rfc2822.html
    # 3.3. Date and Time Specification
    timestamp = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())

    if is_quilt_workflow(config):
        return '\n'.join([
            f"From: {config.get('SENDER', '')}",
            # without the v, like the announcements of the other stable
            # series and the git workflow template (announce-srt.txt)
            f"Subject: [ANNOUNCE] {ctx.new.short}",
            f"Date: {timestamp}",
            f"Message-ID: {make_msgid()}",
            f"To: {config.get('MAIL_TO', '')}",
            '',
            quilt_announcement(ctx),
            '',
            '---',
            changes(ctx)]) + '\n'

    with open(get_announce_tmpl_path(config)) as f:
        stable_rt_text = f.read()

    r = cover_letter_replacements(config, ctx)

    r["date"] = timestamp
    r["branch_name"] = get_remote_branch_name()
    r["branch_head"] = cmd(['git', 'rev-parse', 'HEAD'])

    return stable_rt_text.format(**r) + '\n' + changes(ctx) + '\n'


def announce_path(ctx: SrtContext) -> str:
    """Where srt announce --mail writes the mail: a new directory in the
    temporary directory ($TMPDIR, /tmp). It is kept: a mail client which
    is running already (thunderbird -compose) reads the files after srt
    is done."""
    return os.path.join(tempfile.mkdtemp(prefix='srt-announce-'),
                        f'announce-{ctx.new_tag}')


def mailer_command(mailer: str, mail_path: str, mail: str) -> list[str]:
    """The MAILER command line for the mail in mail_path.

    MAILER is split like a shell would split it, then the placeholders
    in each word are replaced: {mail} the file with the headers, {body}
    the file with only the body (written next to it), {from}, {to},
    {cc} and {subject} the headers. A value stays one word, also with
    spaces in it, and no shell runs the command.
    """
    headers, _, body = mail.partition('\n\n')
    msg = message_from_string(headers + '\n\n')
    words = shlex.split(mailer)
    if not words:
        sys.exit('MAILER is empty')
    values = {
        'mail': os.path.abspath(mail_path),
        'body': os.path.abspath(mail_path + '.body'),
        'from': msg.get('From', ''),
        'to': msg.get('To', ''),
        'cc': msg.get('Cc', ''),
        'subject': msg.get('Subject', ''),
    }
    if any('{body}' in w for w in words):
        with open(values['body'], 'w') as f:
            f.write(body)
    try:
        return [w.format(**values) for w in words]
    except (KeyError, IndexError, ValueError) as err:
        sys.exit(f'MAILER {mailer!r}: unknown placeholder {err}, use '
                 '{mail}, {body}, {from}, {to}, {cc} or {subject}')


def mail_announcement(config: Config, ctx: SrtContext) -> None:
    """Write the announcement to a file and open it in MAILER."""
    mailer = config.get('MAILER')
    if not mailer:
        sys.exit('srt announce --mail: set MAILER in srt.conf, e.g. '
                 'MAILER = mutt -H {mail}')
    mail = announcement(config, ctx)
    path = announce_path(ctx)
    with open(path, 'w') as f:
        f.write(mail)
    print(f'wrote {path}', flush=True)
    argv = mailer_command(mailer, path, mail)
    print(' '.join(shlex.quote(w) for w in argv), flush=True)
    try:
        p = run(argv)
    except OSError as err:
        sys.exit(f'MAILER {argv[0]}: {err}')
    if p.returncode != 0:
        sys.exit(f'MAILER {argv[0]} failed with exit code {p.returncode}, '
                 f'the mail is in {path}')
    # opened, whether it was sent is up to the mail client
    headers = message_from_string(mail.partition('\n\n')[0] + '\n\n')
    log_step('announce --mail', ctx=ctx, result='mail opened',
             mailer=argv[0], mail=path, message_id=headers.get('Message-ID'))


def announce(config: Config, ctx: SrtContext,
             args: argparse.Namespace) -> None:
    if ctx.is_rc:
        if getattr(args, 'mail', False):
            sys.exit('srt announce --mail: the review mails of a release '
                     'candidate are sent with git send-email')
        announce_rc(config, ctx, args)
        return

    if getattr(args, 'mail', False):
        mail_announcement(config, ctx)
        return

    print(announcement(config, ctx), end='')
    announce_next_step(config)


def announce_next_step(config: Config) -> None:
    # stdout is the mail
    if config.get('MAILER'):
        next_step('srt announce --mail, it opens the announcement in '
                  'MAILER', file=sys.stderr)
    else:
        next_step('send the announcement, e.g. srt announce > ../announce '
                  'and mutt -H ../announce, or set MAILER in srt.conf for '
                  'srt announce --mail', file=sys.stderr)


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('announce')
    prs.add_argument('OLD_TAG', nargs='?')
    prs.add_argument('NEW_TAG', nargs='?')
    prs.add_argument('--suppress-cc', '-s', action="store_true", default=False,
                     help='Don''t auto-cc anyone (for testing)')
    prs.add_argument('--mail', '-m', action='store_true',
                     help='write the announcement to a temporary file and '
                     'open it in the mail client MAILER (srt.conf)')
    return prs


def execute(args: argparse.Namespace) -> None:
    ctx = SrtContext(args)
    check_context(ctx)

    announce(get_config(), ctx, args)
