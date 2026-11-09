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
import re
from datetime import date, timedelta
from email.utils import make_msgid
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


def find_starting_ref(ctx: SrtContext) -> str:
    # find starting point. first check for stable update only
    ref = cmd(['git', 'log', '--pretty=format:%H', '--merges', '-n', '1'])

    # if patches have been added, we find the old tag and should start there
    # and not the last merge
    commits = cmd(['git', 'log', '--simplify-by-decoration',
                   '--oneline', str(ref) + '..'])
    if ' '.join(commits.split('\n')).find(str(ctx.old_short_tag)) != -1:
        ref = str(ctx.old_tag)

    return ref


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


def create_rc_patches(config: Config, ctx: SrtContext) -> None:
    ref = find_starting_ref(ctx)
    mails = cmd(['git', 'format-patch', f'{ref}..',
                 '-o', ctx.new_dir_mails, '--subject-prefix',
                 f'PATCH {get_suffix(config).upper()}',
                 '--cover-letter']).splitlines()
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


def announce(config: Config, ctx: SrtContext,
             args: argparse.Namespace) -> None:
    from stable_rt_tools.srt_util import is_quilt_workflow
    if ctx.is_rc:
        announce_rc(config, ctx, args)
        return

    if is_quilt_workflow(config):
        import subprocess
        tag = str(ctx.new_tag) + '-patches'
        try:
            msg = subprocess.check_output([
                'git', 'show', '-s', '--format=%B', tag
            ], encoding='utf-8').strip()
            announce_start = msg.find('[ANNOUNCE]')
            if announce_start != -1:
                lines = msg[announce_start:].splitlines()
                msg = '\n'.join(lines[1:]).lstrip('\n')
            else:
                pass
            msg = strip_trailers(msg)
            timestamp = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())
            sender = config.get('SENDER', '')
            mail_to = config.get('MAIL_TO', '')
            print(f"From: {sender}")
            print(f"To: {mail_to}")
            print(f"Subject: [ANNOUNCE] {ctx.new_tag}")
            print(f"Date: {timestamp}\n")
            print(msg)
        except Exception as e:
            print(f"Error extracting announcement from tag {tag}: {e}")
        return

    # rfc2822.html
    # 3.3. Date and Time Specification
    timestamp = strftime('%a, %d %b %Y %H:%M:%S -0000', gmtime())

    stable_rt_text = ''
    with open(get_announce_tmpl_path(config)) as f:
        stable_rt_text = f.read()

    r = cover_letter_replacements(config, ctx)

    r["date"] = timestamp
    r["branch_name"] = get_remote_branch_name()
    r["branch_head"] = cmd(['git', 'rev-parse', 'HEAD'])

    print(stable_rt_text.format(**r))

    ref = find_starting_ref(ctx)
    print(cmd(['git', '--no-pager', 'shortlog', f'{ref}..{ctx.new_tag}']))

    print('---')

    print(cmd(['git', '--no-pager', 'diff', '--stat',
               f'{ref}..{ctx.new_tag}']))

    print('---')

    print(cmd(['git', '--no-pager', 'diff', f'{ref}..{ctx.new_tag}']))


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
