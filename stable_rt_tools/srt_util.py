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
from logging import error, debug
from configparser import SafeConfigParser
from subprocess import PIPE, run, CalledProcessError

from stable_rt_tools.srt_util_context import SrtContext


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


def get_context(args):
    ctx = SrtContext()
    if not hasattr(args, 'OLD_TAG') or not hasattr(args, 'NEW_TAG'):
        return ctx

    ctx.add_tag('old', args.OLD_TAG)
    ctx.add_tag('new', args.NEW_TAG)
    ctx.init()
    debug(ctx.dump())

    tags = [ctx.old_tag, ctx.new_tag, ctx.new_tag.base]
    if not ctx.new_tag.is_rc:
        tags.append(ctx.new_tag.rebase)

    for tag in tags:
        debug('Check if tag {0} exists'.format(tag))
        if not tag_exists(tag):
            print('tag {0} doesn\'t exists'.format(tag), file=sys.stderr)
            return None

    return ctx
