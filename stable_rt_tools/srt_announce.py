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
import sys
from datetime import date, timedelta
from email.utils import make_msgid
from subprocess import DEVNULL, PIPE, run
from time import gmtime, strftime

from stable_rt_tools.srt_util import (
    Config,
    SubParsers,
    check_context,
    cmd,
    confirm,
    get_config,
    get_gpg_fingerprint,
    get_remote_branch_name,
    get_suffix,
    get_template_path,
)
from stable_rt_tools.srt_util_context import SrtContext

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
    return text + ' ' + cmd(['git', 'diff', '--stat', f'{ref}..']) + '\n'


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
                 '-o', ctx.new_dir_mails, '--subject-prefix', prefix,
                 '--cover-letter']).splitlines()
    mails = add_merge_mails(mails, ref, resolved_merges(ref), prefix)
    for mail in mails:
        if not mail.endswith('/0000-cover-letter.patch'):
            add_review_text(mail, str(ctx.new_tag))


def cover_letter_replacements(config: Config,
                              ctx: SrtContext) -> dict[str, object]:
    r = {
        "mail_to": config['MAIL_TO'],
        "major": ctx.new_tag.major,
        "minor": ctx.new_tag.minor,
        "patch": ctx.new_tag.patch,
        "new_version": ctx.new_short_tag,
        "old_version": ctx.old_short_tag,
        "prj_dir": config['PRJ_DIR'],
        "message_id": make_msgid(),
        "sender": config['SENDER'],
        "name": config['NAME'],
        # new_tag_rt: the name templates know from before 2.0
        "new_tag_rt": ctx.new_tag.number,
        "new_tag_number": ctx.new_tag.number,
        "gpg_key_fingerprint": get_gpg_fingerprint(config),
    }
    if ctx.is_rc:
        r["new_tag_rc"] = ctx.new_tag.rc
    return r


def write_rc_cover_letter(config: Config, ctx: SrtContext) -> None:
    with open(ctx.new_dir_mails + '/0000-cover-letter.patch') as f:
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

    with open(ctx.new_dir_mails + '/0000-cover-letter.patch', 'w') as f:
        f.write(coverletter)


def send_rc_patches(config: Config, ctx: SrtContext,
                    args: argparse.Namespace) -> None:
    gmd = ['git', 'send-email', '--confirm=never']
    if args.suppress_cc:
        gmd += ['--suppress-cc=all']
    # an argument list, no shell: quotes would end up in the address
    gmd += [f'--to={t.strip()}' for t in config['MAIL_TO'].split(',')]
    gmd += [ctx.new_dir_mails]

    print('Dry run')
    gmdd = gmd.copy()
    gmdd.insert(2, '--dry-run')
    print(cmd(gmdd, verbose=True))
    if confirm('OK to send patches?'):
        cmd(gmd)


def announce_rc(config: Config, ctx: SrtContext,
                args: argparse.Namespace) -> None:
    create_rc_patches(config, ctx)
    write_rc_cover_letter(config, ctx)
    send_rc_patches(config, ctx, args)


def get_announce_tmpl_path(config: Config) -> str:
    return get_template_path(config, 'ANNOUNCE', 'announce-srt.txt')


def get_rc_templ_path(config: Config) -> str:
    return get_template_path(config, 'RC_TEXT', 'announce-srt-rc.txt')


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
            stdout=PIPE, stderr=DEVNULL, encoding='utf-8')
    # 1: the merge has conflicts, the tree contains the conflict markers
    if p.returncode not in (0, 1):
        sys.exit(f'git merge-tree {old} {base} failed')
    return p.stdout.splitlines()[0]


def print_changes(ctx: SrtContext) -> None:
    """The shortlog, diffstat and delta of the release."""
    new = str(ctx.new_tag)
    base = delta_base(ctx)
    print(cmd(['git', '--no-pager', 'shortlog', '--first-parent',
               f'{ctx.old_tag}..{new}']))
    print('---')
    print(cmd(['git', '--no-pager', 'diff', '--stat', base, new]))
    print('---')
    print(cmd(['git', '--no-pager', 'diff', base, new]))


def quilt_announcement(ctx: SrtContext) -> str:
    """The announcement of the queue commit, srt quilt queue wrote it."""
    msg = cmd(['git', 'show', '-s', '--format=%B',
               f'{ctx.new_tag}-patches^{{commit}}'])
    subject, _, body = msg.partition('\n')
    if not subject.startswith('[ANNOUNCE]'):
        sys.exit(f'{ctx.new_tag}-patches: the commit message is not an '
                 'announcement, it starts with ' + repr(subject))
    return strip_trailers(body.lstrip('\n'))


def announce(config: Config, ctx: SrtContext,
             args: argparse.Namespace) -> None:
    from stable_rt_tools.srt_util import is_quilt_workflow
    if ctx.is_rc:
        announce_rc(config, ctx, args)
        return

    # rfc2822.html
    # 3.3. Date and Time Specification
    timestamp = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())

    if is_quilt_workflow(config):
        print(f"From: {config.get('SENDER', '')}")
        print(f"Subject: [ANNOUNCE] {ctx.new_tag}")
        print(f"Date: {timestamp}")
        print(f"Message-ID: {make_msgid()}")
        print(f"To: {config.get('MAIL_TO', '')}")
        print()
        print(quilt_announcement(ctx))
        print()
        print('---')
        print_changes(ctx)
        return

    stable_rt_text = ''
    with open(get_announce_tmpl_path(config)) as f:
        stable_rt_text = f.read()

    r = cover_letter_replacements(config, ctx)

    r["date"] = timestamp
    r["branch_name"] = get_remote_branch_name()
    r["branch_head"] = cmd(['git', 'rev-parse', 'HEAD'])

    print(stable_rt_text.format(**r))
    print_changes(ctx)


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('announce')
    prs.add_argument('OLD_TAG', nargs='?')
    prs.add_argument('NEW_TAG', nargs='?')
    prs.add_argument('--suppress-cc', '-s', action="store_true", default=False,
                     help='Don''t auto-cc anyone (for testing)')
    return prs


def execute(args: argparse.Namespace) -> None:
    ctx = SrtContext(args)
    check_context(ctx)

    announce(get_config(), ctx, args)
