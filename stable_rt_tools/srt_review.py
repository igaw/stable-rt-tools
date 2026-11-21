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


"""The review mails of a release candidate."""

import argparse
import os
import re
import sys
from datetime import date, timedelta

from stable_rt_tools.srt_log import log_step
from stable_rt_tools.srt_util import (
    Config,
    cmd,
    confirm,
    get_suffix,
    get_template_path,
    next_step,
    require,
)
from stable_rt_tools.srt_util_context import SrtContext
from stable_rt_tools.srt_util_mail import cover_letter_replacements

REVIEW_TEXT = """\
{tag} stable review patch.
If anyone has any objections, please let me know.

-----------

"""


def add_review_text(path: str, tag: str) -> None:
    """Put the review note at the top of the body of a patch mail."""
    with open(path) as f:
        headers, sep, body = f.read().partition('\n\n')
    with open(path, 'w') as f:
        f.write(headers + sep + REVIEW_TEXT.format(tag=tag) + body)


MERGE_NOTE = """\
The resolution of the merge conflicts, as shown by
git show --remerge-diff: the conflicts git left in the merge on the
- lines, the merge as committed on the + lines.

"""


def resolved_merges(ref: str) -> list[str]:
    """The merges of the release candidate with conflict resolutions.

    git format-patch leaves out merges, but the conflict resolution of
    a stable merge is a change to the series which needs review.
    """
    merges = cmd(['git', 'rev-list', '--reverse', '--first-parent',
                  '--merges', f'{ref}..']).split()
    # a clean merge has no remerge diff
    return [m for m in merges
            if cmd(['git', 'show', '--remerge-diff', '--format=', m])]


def mail_subject(text: str, prefix: str) -> str:
    """Number the subject of a mail with prefix, e.g. 'PATCH RT 1/3'."""
    return re.sub(r'^Subject: \[[^]\n]*\]', f'Subject: [{prefix}]', text,
                  count=1, flags=re.MULTILINE)


def merge_mail(merge: str) -> tuple[str, str]:
    """The file name slug and the mail of a merge, like git format-patch."""
    mail = cmd(['git', 'show', '--format=email', '--remerge-diff',
                '--stat', '--patch', merge]) + '\n'
    head, sep, rest = mail.partition('\n---\n')
    subject = cmd(['git', 'show', '-s', '--format=%s', merge])
    slug = re.sub(r'[^A-Za-z0-9_]+', '-', subject).strip('-')[:64]
    return slug, head + sep + MERGE_NOTE + rest


def series_summary(ref: str, commits: list[str]) -> str:
    """The shortlog and diffstat of the series for the cover letter.

    git format-patch neither lists the merges nor gets the diffstat
    right across a merge: it would count the stable update in.
    """
    authors: dict[str, list[str]] = {}
    for c in commits:
        author, subject = cmd(['git', 'show', '-s', '--format=%an%x00%s',
                               c]).split('\0', 1)
        authors.setdefault(author, []).append(subject)
    text = ''
    for author, subjects in authors.items():
        text += f'{author} ({len(subjects)}):\n'
        text += ''.join(f'  {s}\n' for s in subjects) + '\n'
    if cmd(['git', 'rev-list', '--first-parent', '--merges', f'{ref}..']):
        # a merge with conflicts has a mail of its own
        return text + 'The diffstat is left out, it would contain the ' \
            'stable update.\n'
    return text + cmd(['git', 'diff', '--stat', f'{ref}..']) + '\n'


def rewrite_cover(cover: str, prefix: str, total: int, summary: str) -> None:
    with open(cover) as f:
        text = f.read()
    text = mail_subject(text, f'{prefix} 0/{total}')
    blurb = '*** BLURB HERE ***\n'
    head, sep, rest = text.partition(blurb)
    signature = rest[rest.rfind('\n-- \n'):] if '\n-- \n' in rest else ''
    with open(cover, 'w') as f:
        f.write(head + sep + '\n' + summary + signature)


def add_merge_mails(mails: list[str], ref: str, merges: list[str],
                    prefix: str) -> list[str]:
    """Put the merge mails into the series in commit order.

    The patches of git format-patch are numbered again, the series has
    more mails now, and the cover letter lists all of them.
    """
    order = cmd(['git', 'rev-list', '--reverse', '--first-parent',
                 f'{ref}..']).split()

    cover = mails[0]
    by_commit: dict[str, tuple[str, str]] = {}
    for path in mails[1:]:
        with open(path) as f:
            text = f.read()
        # format-patch starts a mail with 'From <commit> <date>'
        by_commit[text.split()[1]] = (os.path.basename(path)[5:], text)
        os.remove(path)
    for m in merges:
        slug, text = merge_mail(m)
        by_commit[m] = (slug + '.patch', text)

    commits = [c for c in order if c in by_commit]
    series = [by_commit[c] for c in commits]
    total = len(series)
    directory = os.path.dirname(cover)
    result = [cover]
    for n, (name, text) in enumerate(series, start=1):
        path = os.path.join(directory, f'{n:04d}-{name}')
        with open(path, 'w') as f:
            f.write(mail_subject(text, f'{prefix} {n}/{total}'))
        result.append(path)

    rewrite_cover(cover, prefix, total, series_summary(ref, commits))
    return result


def create_rc_patches(config: Config, ctx: SrtContext) -> None:
    """Mail everything added to the series since the last release.

    These are the commits on the series' own line (--first-parent):
    patches before and after the stable merge, the merge itself if it
    has a conflict resolution, the release commit. The commits of the
    stable releases merged in are reviewed elsewhere.
    """
    ref = str(ctx.old_tag)
    prefix = f'PATCH {get_suffix(config).upper()}'
    mails = cmd(['git', 'format-patch', '--first-parent', f'{ref}..',
                 '-o', ctx.new.mails_dir, '--subject-prefix', prefix,
                 '--cover-letter']).splitlines()
    mails = add_merge_mails(mails, ref, resolved_merges(ref), prefix)
    for mail in mails:
        if not mail.endswith('/0000-cover-letter.patch'):
            add_review_text(mail, str(ctx.new_tag))



def write_rc_cover_letter(config: Config, ctx: SrtContext) -> None:
    with open(ctx.new.mails_dir + '/0000-cover-letter.patch') as f:
        coverletter = f.read()

    coverletter = coverletter.replace('*** SUBJECT HERE ***',
                                      'Linux ' + str(ctx.new_tag))

    rc_text = ''
    with open(get_rc_templ_path(config)) as f:
        rc_text = f.read()

    r = cover_letter_replacements(config, ctx)

    today = date.today()
    rc_date = today + timedelta(weeks=1)
    r["release_date"] = rc_date

    rc_text = rc_text.format(**r)

    coverletter = coverletter.replace('*** BLURB HERE ***',
                                      rc_text)

    with open(ctx.new.mails_dir + '/0000-cover-letter.patch', 'w') as f:
        f.write(coverletter)


def send_rc_patches(config: Config, ctx: SrtContext,
                    args: argparse.Namespace) -> None:
    gmd = ['git', 'send-email', '--confirm=never']
    if args.suppress_cc:
        gmd += ['--suppress-cc=all']
    # an argument list, no shell: quotes would end up in the address
    gmd += [f'--to={t.strip()}' for t in require(config, 'MAIL_TO').split(',')]
    gmd += [ctx.new.mails_dir]

    print('Dry run')
    gmdd = gmd.copy()
    gmdd.insert(2, '--dry-run')
    print(cmd(gmdd, verbose=True))
    if not confirm('OK to send patches?'):
        sys.exit('not sent')
    out = cmd(gmd)
    mails = sorted(f for f in os.listdir(ctx.new.mails_dir)
                   if f.endswith('.patch'))
    # git send-email logs the headers of each mail it sent, the
    # cover letter first
    sent = re.search(r'^Message-ID: *(<[^>]+>)', out,
                     flags=re.MULTILINE | re.IGNORECASE)
    log_step('announce', ctx=ctx, result='review mails sent',
             mails=len(mails),
             to=require(config, 'MAIL_TO'),
             message_id=sent.group(1) if sent else None)
    next_step('srt push')


def announce_rc(config: Config, ctx: SrtContext,
                args: argparse.Namespace) -> None:
    create_rc_patches(config, ctx)
    write_rc_cover_letter(config, ctx)
    send_rc_patches(config, ctx, args)



def get_rc_templ_path(config: Config) -> str:
    return get_template_path(config, 'RC_TEXT', 'announce-srt-rc.txt')
