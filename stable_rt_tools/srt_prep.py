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
from stable_rt_tools.srt_util import (
    get_remote_branch_name, get_old_tag, get_config, get_last_rt_tag, cmd
)


def get_next_stable_version(branch_name, tree_dir):
    branch = cmd([
        'git', '-C', tree_dir, 'rev-parse', '--abbrev-ref', 'HEAD']
    ).strip()
    tags = cmd([
        'git', '-C', tree_dir, 'tag', '--merged', branch, '--sort=-v:refname'
    ]).splitlines()
    for tag in tags:
        if tag.startswith('v') and '-rt' not in tag:
            return tag
    return None


def prep(config):
    current_dir = os.path.basename(os.getcwd())

    # quilt patches
    quilt_patches = os.path.abspath(
        os.path.join('..', f"{current_dir}-patches", "patches")
    )

    # old tag
    old_tag = get_old_tag()

    # new tag
    branch_name = get_remote_branch_name()
    rt = get_last_rt_tag(branch_name, '')
    rt_ver = rt[3:]
    rt_ver = int(rt_ver) + 1
    stable_tree_dir = os.path.abspath(
        os.path.join('..', current_dir.split('-rt')[0])
    )
    next_stable = get_next_stable_version(branch_name, stable_tree_dir)
    new_tag = f"{next_stable}-rt{rt_ver}"

    print(f"export QUILT_PATCHES={quilt_patches}")
    print(f"export OLD_TAG={old_tag}")
    print(f"export NEW_TAG={new_tag}")


def add_argparser(parser):
    prs = parser.add_parser('prep')
    return prs


def execute(args):
    prep(get_config())
