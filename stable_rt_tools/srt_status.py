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


"""The status of the release, for both workflows.

The steps up to the tag differ (srt commit and srt tag, or srt quilt
refresh..release), the rest is the same: srt create and srt sign leave
their files in the release directory, srt upload puts them on kernel.org
(kup ls tells), srt push puts the release on the remote branch (as of
the last fetch) and srt announce sends the announcement (its mail is in
the archive of the mailing list, see srt_inbox). A release published or
made on top of another one meanwhile is stale. srt status, srt mcp and
agents read the result, see status_info().

The steps are derived from the trees: the state of srt prep only names
the release prepared. Without it (srt push clears it, or it got lost),
the release is the one after the last release on HEAD if one of its
steps is done, else the last release itself.
"""

import argparse
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from subprocess import CalledProcessError
from typing import cast

from stable_rt_tools import srt_inbox, srt_log, srt_quilt
from stable_rt_tools.srt_prep import get_next_stable_version, worktree_dirs
from stable_rt_tools.srt_quilt import git, pushed, rev, upstream
from stable_rt_tools.srt_util import (
    Config,
    SrtState,
    SubParsers,
    get_config,
    get_last_release,
    get_remote_branch_name,
    get_suffix,
    get_workflow_branch,
    is_quilt_workflow,
    next_step,
    print_test,
    read_srt_state,
    release_testing_command,
)
from stable_rt_tools.srt_util_context import release_dir, release_files
from stable_rt_tools.srt_util_tag import Tag, is_upstream_release

# a release like v6.12.116-rt22 and the upstream release it is made on

# kup ls goes to kernel.org over ssh, don't let it hang srt status
KUP_TIMEOUT = 30

# a step is done (True), not done (False) or unknown (None), e.g. srt
# upload without access to kernel.org
type Step = tuple[str, bool | None]

# what the JSON tells about a step besides done: why it is unknown, the
# mail of the announcement
type StepDetails = dict[str, dict[str, object]]

# the event in the log of the series once the announcement is found
ANNOUNCED = 'announced'

NOT_PREPARED_NEXT = 'srt prep (in the worktree of the series)'


def last_tag(path: str) -> str | None:
    """The last tag on the upstream branch of the worktree."""
    try:
        return git(path, 'describe', '--tags', '--abbrev=0', '@{u}')
    except CalledProcessError:
        return None


def published(path: str, tag: str) -> bool:
    """True if the tag exists and its branch upstream contains it."""
    ref = rev(path, 'refs/tags/' + tag)
    return ref is not None and pushed(path, ref)


def stale_warnings(path: str, old: str, new: str,
                   from_state: bool = True) -> list[str]:
    """Why the release old -> new doesn't fit the upstream branch of the
    worktree path (anymore). A release prepared with srt prep and
    published is stale (srt push clears the state), a release found in
    the trees is pushed then (the srt push step)."""
    if from_state and published(path, new):
        return [f'{new} is published already, on {upstream(path)}: run '
                '"srt prep --clear" and "srt prep" for the next release']
    # the last release on the upstream branch, as everywhere: its first
    # parents, not -rebase, -patches or release candidates
    last = get_last_release('@{u}', Tag(new).suffix, path=path)
    if last is not None and last not in (old, new):
        return [f'{upstream(path)} is at {last}, the release was prepared '
                f'on top of {old}: run "srt prep --clear" and "srt prep"']
    return []


def file_steps(path: str, tag: str, tagged: bool) -> list[Step]:
    """srt create and srt sign, done when the release is tagged and
    their files are there."""
    files = release_files(path, tag)
    created = tagged and all(os.path.isfile(f) for f in files)
    signed = created and all(os.path.isfile(os.path.splitext(f)[0] +
                                            '.sign') for f in files)
    return [('srt create', created), ('srt sign', signed)]


def parse_kup_ls(text: str) -> set[str]:
    """The names kup ls lists: a '+++ <directory>/' line, then one entry
    per line in the format of ls -l, the name is the last field
    (directories with a trailing /)."""
    names = set()
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] != '+++':
            names.add(os.path.basename(fields[-1].rstrip('/')))
    return names


def kup_ls(path: str) -> tuple[set[str] | None, str]:
    """The names in the directory path on kernel.org, or None and why
    kup couldn't tell (not installed, no network or access)."""
    try:
        # its own session: ssh must not ask for a passphrase on the tty
        p = subprocess.run(['kup', 'ls', path], capture_output=True,
                           encoding='utf-8', errors='replace',
                           stdin=subprocess.DEVNULL, timeout=KUP_TIMEOUT,
                           start_new_session=True)
    except FileNotFoundError:
        return None, 'kup is not installed'
    except subprocess.TimeoutExpired:
        return None, f'kup ls {path} timed out'
    if p.returncode:
        err = (p.stderr.strip().splitlines() or [''])[-1]
        return None, f'kup ls {path} failed ({p.returncode}) {err}'.strip()
    return parse_kup_ls(p.stdout), ''


def uploaded(names: set[str], files: Sequence[str]) -> bool:
    """True if names (of kup ls) has each file of srt upload and its
    signature: patch-6.12.118-rt24.patch.xz, as it is or with another
    compression, and patch-6.12.118-rt24.patch.sign."""
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        sign = stem + '.sign'
        if sign not in names:
            return False
        if not any(n == stem or (n.startswith(stem + '.') and n != sign)
                   for n in names):
            return False
    return True


def _config(path: str, config: Config | None) -> Config | None:
    if config is None:
        try:
            config = get_config(path)
        except SystemExit:
            return None
    return config


def _prj_dir(path: str, config: Config | None) -> str | None:
    config = _config(path, config)
    if config is None:
        return None
    return config.get('PRJ_DIR') or None


def upload_step(path: str, tag: str, signed: bool, offline: bool,
                config: Config | None = None) -> tuple[Step, str | None]:
    """srt upload: done when kup ls lists the files in PRJ_DIR/older.
    Only asked once the files are signed, unknown offline or when kup
    can't tell. Returns the step and why it is unknown."""
    name = 'srt upload'
    if not signed:
        return (name, False), None
    if offline:
        return (name, None), 'offline'
    prj_dir = _prj_dir(path, config)
    if prj_dir is None:
        return (name, None), 'PRJ_DIR is not set'
    names, why = kup_ls(prj_dir + '/older')
    if names is None:
        return (name, None), why
    return (name, uploaded(names, release_files(path, tag))), None


def logged_mail(path: str, tag: str) -> dict[str, object] | None:
    """The mail of the announcement of tag an earlier srt status found,
    from the log of the series: the archive doesn't forget it."""
    try:
        events = srt_log.read_log(path)
    except (OSError, SystemExit):
        return None
    for event in reversed(events):
        if event.get('step') == ANNOUNCED and event.get('release') == tag:
            return {k: event.get(k) for k in
                    ('subject', 'date', 'sender', 'message_id', 'link')}
    return None


def announce_step(path: str, tag: str, old: str | None, pushed: bool,
                  offline: bool, config: Config | None = None) \
        -> tuple[Step, dict[str, object]]:
    """srt announce: done when the archive of the mailing list (INBOX)
    has the announcement, in the local clone of it (srt_inbox). Only
    looked for once the release is pushed; the clone is fetched only
    when the mail isn't in it yet, never offline. Once found, the log of
    the series has it and the next srt status doesn't look again.
    Returns the step and its details for the JSON: the mail, or why it
    is unknown."""
    name = 'srt announce'
    if not pushed:
        return (name, False), {}
    mail = logged_mail(path, tag)
    if mail is not None:
        return (name, True), {'mail': mail}
    config = _config(path, config)
    if config is None:
        return (name, None), {'unknown': 'no srt.conf group'}
    inbox = config.get('INBOX', srt_inbox.DEFAULT_INBOX)
    if not inbox:
        return (name, None), {'unknown': 'INBOX is empty'}
    found = srt_inbox.find(inbox, tag)
    if found is None:
        if offline:
            return (name, None), {'unknown': 'offline'}
        why = srt_inbox.sync(inbox)
        if why:
            return (name, None), {'unknown': why}
        found = srt_inbox.find(inbox, tag)
        if found is None:
            return (name, False), {}
    srt_log.log_step(ANNOUNCED, tag, old, path, subject=found.subject,
                     date=found.date, sender=found.sender,
                     message_id=found.message_id, link=found.link)
    return (name, True), {'mail': dict(found.as_dict())}


def publish_steps(path: str, tag: str, tagged: bool, offline: bool,
                  config: Config | None = None, old: str | None = None) \
        -> tuple[list[Step], StepDetails]:
    """srt create, sign, upload, push and announce of the release tag,
    and the details of the steps: why one is unknown, the mail of the
    announcement."""
    steps = file_steps(path, tag, tagged)
    details: StepDetails = {}
    upload, why = upload_step(path, tag, steps[-1][1] is True, offline,
                              config)
    steps.append(upload)
    if why:
        details[upload[0]] = {'unknown': why}
    pushed = tagged and published(path, tag)
    steps.append(('srt push', pushed))
    announce, extra = announce_step(path, tag, old, pushed, offline,
                                    config)
    steps.append(announce)
    if extra:
        details[announce[0]] = extra
    return steps, details


def leftover_warnings(path: str, tag: str, tagged: bool) -> list[str]:
    """Files of the release before it is tagged, e.g. of a release made
    and undone with srt 2.1: they must not be uploaded."""
    d = release_dir(path, tag)
    if tagged or not os.path.isdir(d) or not os.listdir(d):
        return []
    return [f'{d} holds files but {tag} is not tagged: remove them, srt '
            'create makes them after the release']


# steps a release doesn't need: open, they are skipped once a later step
# is done
OPTIONAL_STEPS = ('srt test',)


def first_open(steps: Sequence[Step]) -> Step | None:
    """The first step not done. An unknown step followed by a done one
    counts as done: srt upload comes before srt push. So does an optional
    one (srt test): srt create doesn't need it. None when all are done:
    the release is complete."""
    for i, (name, done) in enumerate(steps):
        if done is True:
            continue
        if (done is None or name in OPTIONAL_STEPS) and \
                any(d is True for _, d in steps[i + 1:]):
            continue
        return name, done
    return None


def test_step(path: str, tag: str) -> tuple[Step, dict[str, object]]:
    """srt test of the release tag: done once the history has it ran
    (whatever its exit code), and the exit code of the last run."""
    try:
        events = [e for e in srt_log.read_log(path)
                  if e.get('step') == 'test' and e.get('release') == tag]
    except (OSError, SystemExit):
        events = []
    if not events:
        return ('srt test', False), {}
    return ('srt test', True), {'exit': events[-1].get('exit')}


def release_next(tag: str, steps: Sequence[Step],
                 warnings: Sequence[str],
                 overrides: Mapping[str, str]) -> str:
    """The next step of the release tag: the first one not done, told
    as overrides says (e.g. 'srt tag' -> 'srt commit and srt tag'). A
    stale release (the first warning is about the tag) is prepared
    again. After a release with all steps done, announced too, comes the
    next one (tree_status_info tells when)."""
    if warnings and warnings[0].startswith(tag):
        return 'srt prep --clear, then srt prep'
    nxt = first_open(steps)
    if nxt is None:
        return 'srt prep'
    name, done = nxt
    text = overrides.get(name, name)
    if done is None:
        text += ' (unless done already)'
    return text


def _info(workflow: str, old: str, new: str, steps: Sequence[Step],
          warnings: list[str], nxt: str, details: StepDetails,
          **extra: object) -> dict[str, object]:
    def step(name: str, done: bool | None) -> dict[str, object]:
        return {'step': name, 'done': done, **details.get(name, {})}

    return {
        'prepared': True,
        'workflow': workflow,
        'old_tag': old,
        'new_tag': new,
        **extra,
        'steps': [step(name, done) for name, done in steps],
        'warnings': warnings,
        'next': nxt,
    }


def git_status_info(old: str, new: str, offline: bool = False,
                    from_state: bool = True,
                    path: str | None = None) -> dict[str, object]:
    """The release of the git workflow in the worktree path, the current
    directory for None."""
    path = path or os.getcwd()
    tagged = rev(path, 'refs/tags/' + new) is not None
    publish, details = publish_steps(path, new, tagged, offline, old=old)
    steps: list[Step] = [('srt tag', tagged), *publish]
    warnings = stale_warnings(path, old, new, from_state)
    warnings += leftover_warnings(path, new, tagged)
    nxt = release_next(new, steps, warnings,
                       {'srt tag': 'srt commit and srt tag'})
    return _info('git', old, new, steps, warnings, nxt, details)


def quilt_status_info(rel: srt_quilt.Release, offline: bool = False,
                      from_state: bool = True) -> dict[str, object]:
    """The release of the quilt workflow."""
    dropped, added = rel.series_changes()
    tagged = rel.done('release')
    steps: list[Step] = [(f'srt quilt {step}', rel.done(step))
                         for step in srt_quilt.STEPS]
    publish, details = publish_steps(rel.rt_dir, rel.release_tag, tagged,
                                     offline, rel.config, str(rel.old))
    overrides = {'srt create': srt_quilt.RELEASE_NEXT}
    if rel.config.get('TEST_COMMAND'):
        tested, detail = test_step(rel.rt_dir, rel.release_tag)
        steps.append(tested)
        if detail:
            details['srt test'] = detail
        overrides = {'srt test': srt_quilt.TEST_NEXT}
    steps += publish
    warnings = stale_warnings(rel.rt_dir, str(rel.old), rel.release_tag,
                              from_state)
    warnings += leftover_warnings(rel.rt_dir, rel.release_tag, tagged)
    last_stable = last_tag(rel.stable_dir)
    if not rel.done('refresh') and last_stable and \
            is_upstream_release(last_stable) and last_stable != rel.base:
        warnings.append(f'upstream is at {last_stable}, the release was '
                        f'prepared for {rel.base}: run "srt prep" again')
    nxt = release_next(rel.release_tag, steps, warnings, overrides)
    return _info('quilt', str(rel.old), rel.release_tag, steps, warnings,
                 nxt, details, dropped=dropped, added=added)


#
# the release from the trees, without the state of srt prep
#

def series_dir(path: str) -> str:
    """The worktree of the series for path, which may be its -patches or
    -rebase worktree."""
    path = os.path.abspath(path)
    for postfix in ('-patches', '-rebase'):
        if path.endswith(postfix) and os.path.isdir(path[:-len(postfix)]):
            return path[:-len(postfix)]
    return path


def tree_state(path: str, config: Config, old: str, new: str) -> SrtState:
    """The state srt prep would have written for the release old -> new
    of the series in the worktree path. Without refreshed: srt quilt
    finds it in the patch queue."""
    suffix = get_suffix(config)
    quilt = is_quilt_workflow(config)
    state = SrtState(
        old_tag=old, new_tag=new, suffix=suffix, quilt_workflow=quilt,
        workflow_branch=get_workflow_branch(
            get_remote_branch_name(path=path)))
    if quilt:
        dirs = worktree_dirs(path, suffix)
        state['rt_dir'] = dirs['rt_dir']
        state['stable_dir'] = dirs['stable_dir']
        state['patches_dir'] = dirs['patches_dir']
        state['rebase_dir'] = dirs['rebase_dir']
        state['quilt_patches'] = os.path.join(dirs['patches_dir'],
                                              'patches')
    return state


def stable_tags(path: str, last: Tag, ref: str | None = None) -> list[str]:
    """The upstream releases of the series of last (v6.12.*), newest
    first: all of them (as fetched), or those merged into ref."""
    args = ['tag', '-l', '--sort=-v:refname']
    if ref is not None:
        args += ['--merged', ref]
    out = git(path, *args, f'v{last.major}.{last.minor}.*')
    return [t for t in out.splitlines() if is_upstream_release(t)]


def newer_stable(path: str, last: Tag) -> str | None:
    """The newest upstream release after the one last is made on, as of
    the last fetch."""
    tags = stable_tags(path, last)
    if tags and Tag(tags[0]).patch > last.patch:
        return tags[0]
    return None


def release_tags(path: str, last: Tag, number: int) -> list[str]:
    """The releases number of the series of last its tags (the release,
    -rebase or -patches) name, e.g. v6.12.118-rt24."""
    out = git(path, 'tag', '-l',
              f'v{last.major}.{last.minor}.*-{last.suffix}{number}*')
    found = []
    for t in out.splitlines():
        tag = Tag.parse(t)
        if tag is None or not tag.is_release or tag.is_rc or \
                tag.suffix != last.suffix or tag.number != number or \
                not set(tag.flags) <= {'patches', 'rebase'}:
            continue
        found.append(f'{tag.base}-{last.suffix}{number}')
    return sorted(set(found))


def started_release(path: str, config: Config, last: Tag) -> str | None:
    """The release after last if one of its steps is done: one of its
    tags exists, the queue is refreshed for it (quilt) or HEAD has a
    newer upstream release merged (git)."""
    number = last.number + 1
    tags = release_tags(path, last, number)
    if tags:
        return tags[-1]
    base: str | None
    if is_quilt_workflow(config):
        dirs = worktree_dirs(path, last.suffix)
        localversion = srt_quilt.series_localversion(
            os.path.join(dirs['patches_dir'], 'patches'),
            config.get('LOCALVERSION', f'localversion-{last.suffix}'))
        if localversion != f'-{last.suffix}{number}' or \
                not os.path.isdir(dirs['stable_dir']):
            return None
        # srt quilt refresh refreshes on top of what srt prep found there
        base = get_next_stable_version('', dirs['stable_dir'])
    else:
        merged = stable_tags(path, last, 'HEAD')
        base = merged[0] if merged else None
        if base is not None and Tag(base).patch <= last.patch:
            return None
    return f'{base}-{last.suffix}{number}' if base else None


def prep_next(path: str, last: Tag) -> str:
    """The next step when the release last is done."""
    if newer_stable(path, last):
        return 'srt prep'
    return f'srt prep, once upstream has a release after {last.base}'


def tree_status_info(offline: bool = False) -> dict[str, object]:
    """The release from the trees: the one after the last release on HEAD
    if it is started, else the last release. prepared is False when that
    one is done: nothing is in progress."""
    path = series_dir(os.getcwd())
    try:
        config = get_config(path)
    except SystemExit:
        return {'prepared': False, 'next': NOT_PREPARED_NEXT}
    suffix = get_suffix(config)
    last_name = get_last_release('HEAD', suffix, path=path)
    if last_name is None:
        return {'prepared': False, 'next': NOT_PREPARED_NEXT}
    last = Tag(last_name)

    started = started_release(path, config, last)
    if started is not None:
        old, new = last_name, started
    else:
        previous = get_last_release(f'{last_name}^', suffix, path=path)
        if previous is None:
            return {'prepared': False, 'next': prep_next(path, last)}
        old, new = previous, last_name

    state = tree_state(path, config, old, new)
    if state.get('quilt_workflow'):
        info = quilt_status_info(srt_quilt.Release(state), offline,
                                 from_state=False)
    else:
        info = git_status_info(old, new, offline, from_state=False,
                               path=path)
    info['source'] = 'trees'
    steps = cast(list[dict[str, object]], info['steps'])
    if started is None and first_open(
            [(str(s['step']), cast(bool | None, s['done']))
             for s in steps]) is None:
        info['prepared'] = False
        info['next'] = prep_next(path, last)
    return info


def status_info(offline: bool = False) -> dict[str, object]:
    """The release, its steps, warnings and the next step: the one srt
    prep prepared, else the one the trees show (tree_status_info)."""
    state = read_srt_state()
    if not state or not state.get('new_tag'):
        return with_test(tree_status_info(offline))
    if state.get('quilt_workflow'):
        info = quilt_status_info(srt_quilt.Release(state), offline)
    else:
        info = git_status_info(state['old_tag'], state['new_tag'], offline)
    info['source'] = 'state'
    return with_test(info)


def with_test(info: dict[str, object]) -> dict[str, object]:
    """info with 'test', the test command (TEST_COMMAND), when testing
    the release is the next step."""
    if not info.get('prepared') or \
            info.get('next') not in (srt_quilt.RELEASE_NEXT,
                                     srt_quilt.TEST_NEXT):
        return info
    path = series_dir(os.getcwd())
    try:
        config = get_config(path)
    except SystemExit:
        return info
    text = release_testing_command(config, str(info['new_tag']),
                                   str(info['old_tag']), path)
    if text is not None:
        info['test'] = text
    return info


def status(as_json: bool = False, offline: bool = False) -> None:
    info = status_info(offline)
    if as_json:
        print(json.dumps(info, indent=2))
    elif info['prepared']:
        print_status(info)
    elif 'steps' in info:
        print('No release in progress, the last one:')
        print_status(info)
    else:
        print('No release prepared.')
        next_step(cast(str, info['next']))


def _mark(done: object) -> str:
    if done is None:
        return '?'
    return 'x' if done else ' '


def print_status(info: Mapping[str, object]) -> None:
    print(f"{info['old_tag']} -> {info['new_tag']}")
    for p in cast(list[str], info.get('dropped', [])):
        print(f'  dropped: {p}')
    for p in cast(list[str], info.get('added', [])):
        print(f'  added:   {p}')
    for step in cast(list[dict[str, object]], info['steps']):
        line = f"  [{_mark(step['done'])}] {step['step']}"
        if 'unknown' in step:
            line += f" (unknown: {step['unknown']})"
        print(line)
        mail = cast(dict[str, object] | None, step.get('mail'))
        if mail:
            print(f"      {mail['date']} {mail['sender']}")
            print(f"      {mail.get('link') or mail['message_id']}")
    for w in cast(list[str], info['warnings']):
        print(f'warning: {w}')
    if info.get('test'):
        print_test(cast(str, info['test']))
    next_step(cast(str, info['next']))


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('status',
                            help='show the release in progress and the '
                            'next step',
                            description='Show the release of the series of '
                            'the current worktree, its steps done ([x]), not '
                            'done ([ ]) or unknown ([?]), warnings and the '
                            'next step. The release is the one prepared with '
                            'srt prep, else the one the trees show. The steps '
                            'come from the trees: tags, the patch queue, the '
                            'files of srt create and srt sign, kup ls for '
                            'srt upload, the fetched branch for srt push and '
                            'the archive of the mailing list (INBOX) for srt '
                            'announce. It changes nothing in the trees; it '
                            'clones or fetches the archive into ~/.cache and '
                            'adds a line to the history once it finds the '
                            'announcement.')
    prs.add_argument('--json', action='store_true',
                     help='print the status as JSON, for scripts')
    prs.add_argument('--offline', action='store_true',
                     help="don't ask kernel.org (kup ls) whether the "
                     "release is uploaded, don't fetch the archive of the "
                     'mailing list (INBOX) whether it is announced')
    return prs


def execute(args: argparse.Namespace) -> None:
    status(as_json=args.json, offline=getattr(args, 'offline', False))
