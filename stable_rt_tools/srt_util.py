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


import os
import sys
import re
from logging import error, debug
from configparser import SafeConfigParser
from subprocess import PIPE, run, CalledProcessError


def cmd(args, verbose=False, env=None):
    if verbose:
        print(' '.join(args))
    debug('run: ' + ' '.join(args))
    p = run(args, check=True, stdout=PIPE, env=env)
    r = p.stdout.decode('utf-8').strip()
    debug('     ' + r)
    return r


def get_remote_repo_name():
    line = cmd(['git', 'config', '--get', 'remote.origin.url'])
    name = os.path.splitext(os.path.basename(line))[0]
    return name


def get_local_branch_name():
    return cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip()


def get_remote_branch_name(short=True):
    name = cmd(['git', 'rev-parse', '--abbrev-ref',
                '--symbolic-full-name', '@{u}'])
    if short:
        return name.split('/')[1]
    return name


def tag_exists(tag):
    try:
        run(['git', 'rev-parse', '--verify',
             '--quiet', '{0}^{{tag}}'.format(tag)],
            check=True, stdout=PIPE)
    except CalledProcessError:
        return False
    return True


def get_last_tag(branch_name, postfix=None):
    if postfix:
        base_branch = branch_name[:-len(postfix)]
    else:
        base_branch = branch_name
    last_tag = cmd(['git', 'describe', '--abbrev=0', '--tags', base_branch])
    return last_tag


def get_last_rt_tag(branch_name, postfix=None):
    last_tag = get_last_tag(branch_name, postfix)
    m = re.search(r'(-rt[0-9]+)$', last_tag)
    if not m:
        print('Last tag {0} does not end in -rt[0-9]+ on {1}'.
              format(last_tag, branch_name),
              file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def get_old_tag():
    last_tag = get_last_tag(get_remote_branch_name())

    import logging
    log = logging.getLogger()
    log.debug(last_tag)

    m = re.match(r'^v(\d+)\.(\d+)\.(\d+)-rt(\d+)$', last_tag)
    major = int(m.group(1))
    minor = int(m.group(2))
    base_version = 'v{}.{}'.format(major, minor)

    tags = cmd(['git', 'ls-remote', '--tags'])
    match = r'.*({}\.\d+-rt\d+)$'.format(base_version)
    m = re.findall(match, tags, re.MULTILINE)
    if not m:
        print('Last remote tag -rt[0-9]+ not found on {}'.
              format(branch_name))
        sys.exit(1)

    last_patch = 0
    last_rt = 0
    for f in m:
        m2 = re.match(r'^v(\d+)\.(\d+)\.(\d+)-rt(\d+)$', f)
        patch = int(m2.group(3))
        rt = int(m2.group(4))

        if patch > last_patch:
            last_patch = patch
            last_rt = rt

        if rt > last_rt:
            last_rt = rt

    return '{}.{}-rt{}'.format(base_version, last_patch, last_rt)


def is_dirty():
    line = cmd(['git', 'status', '--short'])
    if line != '':
        return True
    return False


def read_config():
    config = SafeConfigParser()
    dirs = [os.curdir,
            os.path.expanduser('~/.config/'),
            os.path.expanduser('~'),
            '/etc/srt']
    if 'SRT_CONF' in os.environ:
        dirs.insert(0, os.environ.get('SRT_CONF'))
    config.read(list(map(lambda x: x + '/srt.conf', dirs)))
    return config


def get_config():
    try:
        repo_name = get_remote_repo_name()
        branch_name = get_remote_branch_name(short=False)
        config_name = '{0}/{1}'.format(repo_name, branch_name)
        debug('Using configuration {0}'.format(config_name))
        config = read_config()[config_name]
    except:
        error('Could not retrieve configuration {0} from srt.conf'.format(config_name))
        sys.exit(1)

    return config


def get_gnupghome(config):
    gnupghome = os.getenv('GNUPGHOME', '~/.gnupg')
    if 'GNUPGHOME' in config:
        gnupghome = config['GNUPGHOME']
    return gnupghome


def get_gpg_fingerprint(config):
    out = cmd(['gpg2',
               '--homedir', get_gnupghome(config),
               '--local-user', '{}'.format(config['GPG_KEY_ID']),
               '--fingerprint'])

    # thank you gpg for nothing!
    fingerprint = ''
    cnt = 0
    for line in out.splitlines():
        if cnt == 3:
            fingerprint = line.strip()
            break
        cnt += 1
    return fingerprint


def confirm(text):
    try:
        while True:
            reply = str(input(text + ' (y/n): ')).lower().strip()
            if reply[:1] == 'y':
                return True
            if reply[:1] == 'n':
                return False
    except KeyboardInterrupt:
        return False


def check_context(ctx):
    if ctx.old_tag == ctx.new_tag:
        text = ('Something went wrong. OLD_TAG and NEW_TAG are the same ({}).\n'
                'Did you push your changes already? In this case you need to\n'
                'provide the OLD_TAG and NEW_TAG')
        print(text.format(old_tag))
        exit(1)

    tags = [ctx.old_tag, ctx.new_tag, ctx.new_tag.base]
    if not ctx.new_tag.is_rc:
        tags.append(ctx.new_tag.rebase)

    for tag in tags:
        debug('Check if tag {0} exists'.format(tag))
        if not tag_exists(tag):
            print('tag {0} doesn\'t exists'.format(tag), file=sys.stderr)
            return None

    return ctx
