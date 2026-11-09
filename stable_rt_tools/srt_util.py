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

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from configparser import ConfigParser
from datetime import UTC, datetime
from importlib.resources import files
from logging import debug, error
from subprocess import DEVNULL, PIPE, CalledProcessError, run
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from stable_rt_tools.srt_util_context import SrtContext

# An srt.conf group: a configparser section or, in tests, a dict.
type Config = Mapping[str, str]


class SrtState(TypedDict, total=False):
    """The release prepared by srt prep, stored in the git common dir."""

    old_tag: str
    new_tag: str
    branch: str
    workflow_branch: str
    quilt_workflow: bool
    quilt_patches: str
    rt_dir: str
    stable_dir: str
    patches_dir: str
    rebase_dir: str
    refreshed: str | None
    updated_at: str


def cmd(args: Sequence[str], verbose: bool = False,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None) -> str:
    if verbose:
        print(' '.join(args))
    debug('run: ' + ' '.join(args) + (f' (in {cwd})' if cwd else ''))
    p = run(args, check=True, stdout=PIPE,
            stderr=None if verbose else DEVNULL, env=env, cwd=cwd)
    r = p.stdout.decode('utf-8').strip()
    debug('     ' + r)
    return r


def get_remote_repo_name() -> str:
    line = cmd(['git', 'config', '--get', 'remote.origin.url'])
    name = os.path.splitext(os.path.basename(line))[0]
    return name


def get_local_branch_name() -> str:
    return cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip()


def get_remote_branch_name(short: bool = True) -> str:
    name = cmd(['git', 'rev-parse', '--abbrev-ref',
                '--symbolic-full-name', '@{u}'])
    if short:
        return name.split('/')[1]
    return name


def get_workflow_branch(branch_name: str) -> str:
    for suffix in ('-patches', '-rebase', '-next'):
        if branch_name.endswith(suffix):
            return branch_name[:-len(suffix)]
    return branch_name


def tag_exists(tag: object) -> bool:
    try:
        run(['git', 'rev-parse', '--verify',
             '--quiet', f'{tag}^{{tag}}'],
            check=True, stdout=PIPE)
    except CalledProcessError:
        return False
    return True


def get_last_tag(branch_name: str, postfix: str | None = None) -> str:
    if postfix:
        base_branch = branch_name[:-len(postfix)]
    else:
        base_branch = branch_name
    last_tag = cmd(['git', 'describe', '--abbrev=0', '--tags', base_branch])
    return last_tag


def get_last_rt_tag(branch_name: str, postfix: str | None = None) -> str:
    last_tag = get_last_tag(branch_name, postfix)
    m = re.search(r'(-rt[0-9]+)$', last_tag)
    if not m:
        print(f'Last tag {last_tag} does not end in -rt[0-9]+ on '
              f'{branch_name}', file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def get_old_tag() -> str:
    last_tag = get_last_tag(get_remote_branch_name())

    import logging
    log = logging.getLogger()
    log.debug("Last tag: %s", last_tag)

    # Match tags like: v6.12.28-rt10[-rc1][-patches]
    tag_re = r'^v(\d+)\.(\d+)\.(\d+)-rt(\d+)(-rc(\d+))?(-patches)?$'
    m = re.match(tag_re, last_tag)
    if not m:
        print(f'Invalid last tag format: {last_tag}')
        sys.exit(1)

    major = int(m.group(1))
    minor = int(m.group(2))
    base_version = f'v{major}.{minor}'

    tags = cmd(['git', 'ls-remote', '--tags'])
    # Look for all matching tags with optional -rcN and -patches
    match_re = rf'.*({base_version}\.\d+-rt\d+(-rc\d+)?(-patches)?)$'
    matches = re.findall(match_re, tags, re.MULTILINE)

    if not matches:
        print('Last remote tag -rt[0-9]+ not found on '
              f'{get_remote_branch_name()}')
        sys.exit(1)

    last_patch = 0
    last_rt = 0
    last_rc: int | None = None

    for groups in matches:
        tag_str = groups[0]  # full tag string
        m2 = re.match(tag_re, tag_str)
        if not m2:
            continue
        patch = int(m2.group(3))
        rt = int(m2.group(4))
        rc_str = m2.group(6)
        rc = int(rc_str) if rc_str else None

        if patch > last_patch or (patch == last_patch and rt > last_rt):
            last_patch = patch
            last_rt = rt
            last_rc = rc
        elif (patch == last_patch and rt == last_rt and rc is not None
              and (last_rc is None or rc > last_rc)):
            last_rc = rc

    tag = f'{base_version}.{last_patch}-rt{last_rt}'
    if last_rc is not None:
        tag += f'-rc{last_rc}'
    return tag


def get_git_common_dir(path: str | None = None) -> str:
    base = path if path else os.getcwd()
    common_dir = cmd(['git', '-C', base, 'rev-parse', '--git-common-dir'])
    if os.path.isabs(common_dir):
        return common_dir
    return os.path.abspath(os.path.join(base, common_dir))


def get_srt_state_path(path: str | None = None) -> str:
    return os.path.join(get_git_common_dir(path), 'srt', 'state.json')


def read_srt_state(path: str | None = None) -> SrtState | None:
    state_path = get_srt_state_path(path)
    if not os.path.exists(state_path):
        return None
    with open(state_path) as f:
        state: SrtState = json.load(f)
    return state


def write_srt_state(state: SrtState, path: str | None = None) -> None:
    state_path = get_srt_state_path(path)
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    state = state.copy()
    state['updated_at'] = datetime.now(UTC).isoformat()
    with open(state_path, 'w') as f:
        json.dump(state, f, sort_keys=True)


def update_srt_state(changes: SrtState, path: str | None = None) -> SrtState:
    state = read_srt_state(path) or SrtState()
    state.update(changes)
    write_srt_state(state, path)
    return state


def clear_srt_state(path: str | None = None) -> None:
    state_path = get_srt_state_path(path)
    if os.path.exists(state_path):
        os.remove(state_path)


def validate_srt_state(state: SrtState, current_branch: str) -> str | None:
    required = ('old_tag', 'new_tag', 'workflow_branch')
    missing = [k for k in required if not state.get(k)]
    if missing:
        return ('srt state is invalid (missing: {}). '
                'Run "srt prep --clear" and then "srt prep".'
                .format(', '.join(missing)))

    expected_workflow = state['workflow_branch']
    current_workflow = get_workflow_branch(current_branch)
    if expected_workflow != current_workflow:
        return (f'srt state is stale: prepared for workflow '
                f'"{expected_workflow}" but current workflow is '
                f'"{current_workflow}". Run "srt prep --clear" and then '
                f'"srt prep".')
    return None


def is_dirty() -> bool:
    line = cmd(['git', 'status', '--short'])
    return line != ''


def read_config() -> ConfigParser:
    config = ConfigParser()
    dirs = [os.curdir,
            os.path.expanduser('~/.config/'),
            os.path.expanduser('~'),
            '/etc/srt']
    if 'SRT_CONF' in os.environ:
        dirs.insert(0, os.environ['SRT_CONF'])
    # ConfigParser.read() lets later files override earlier ones, the
    # first directory in the list has to win
    config.read([d + '/srt.conf' for d in reversed(dirs)])
    return config


def get_config() -> Config:
    try:
        repo_name = get_remote_repo_name()
        branch_name = get_remote_branch_name(short=False)
    except CalledProcessError:
        error('Could not determine configuration group: check that the '
              'remote "origin" exists and the current branch tracks an '
              'upstream branch (git branch -vv)')
        sys.exit(1)

    config_name = f'{repo_name}/{branch_name}'
    debug(f'Using configuration {config_name}')
    config = read_config()
    if not config.has_section(config_name):
        error(f'Could not retrieve configuration [{config_name}] from '
              'srt.conf')
        sys.exit(1)

    return config[config_name]


def is_quilt_workflow(config: Mapping[str, Any]) -> bool:
    """Return True if the quilt workflow is enabled in config, else False."""
    getboolean = getattr(config, 'getboolean', None)
    if getboolean is not None:
        # a configparser section
        return bool(getboolean('quilt_workflow', fallback=False))
    val = config.get('quilt_workflow', False)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('1', 'yes', 'true', 'on')
    return False


def get_template_path(config: Config, key: str, name: str) -> str:
    """Return the template configured as key, else the one shipped."""
    if key in config:
        return config[key]
    return str(files('stable_rt_tools').joinpath(name))


def get_gnupghome(config: Config) -> str:
    gnupghome = os.getenv('GNUPGHOME', '~/.gnupg')
    if 'GNUPGHOME' in config:
        gnupghome = config['GNUPGHOME']
    return gnupghome


def get_gpg_env(config: Config) -> dict[str, str]:
    # Extend the environment, don't replace it: git needs HOME for
    # ~/.gitconfig (user identity) and gpg the agent/tty variables.
    env = os.environ.copy()
    env['GNUPGHOME'] = os.path.expanduser(get_gnupghome(config))
    return env


def get_gpg_fingerprint(config: Config) -> str:
    out = cmd(['gpg2',
               '--homedir', get_gnupghome(config),
               '--local-user', config['GPG_KEY_ID'],
               '--fingerprint'])

    # thank you gpg for nothing! the fingerprint is the 4th line
    lines = out.splitlines()
    return lines[3].strip() if len(lines) > 3 else ''


def confirm(text: str) -> bool:
    try:
        while True:
            reply = str(input(text + ' (y/n): ')).lower().strip()
            if reply[:1] == 'y':
                return True
            if reply[:1] == 'n':
                return False
    except (KeyboardInterrupt, EOFError):
        # Ctrl-C or no input at all (closed stdin) mean no
        return False


def check_context(ctx: 'SrtContext') -> 'SrtContext | None':
    if ctx.old_tag == ctx.new_tag:
        text = ('Something went wrong. '
                'OLD_TAG and NEW_TAG are the same ({}).\n'
                'Did you push your changes already? In this case you need to\n'
                'provide the OLD_TAG and NEW_TAG')
        print(text.format(ctx.old_tag))
        sys.exit(1)

    tags = [ctx.old_tag, ctx.new_tag, ctx.new_tag.base]
    if not ctx.new_tag.is_rc:
        tags.append(ctx.new_tag.rebase)

    for tag in tags:
        debug(f'Check if tag {tag} exists')
        if not tag_exists(tag):
            print(f'tag {tag} doesn\'t exists', file=sys.stderr)
            return None

    return ctx
