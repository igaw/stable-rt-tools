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

"""srt mcp: the release steps for an agent, as an MCP server.

JSON-RPC 2.0 over stdin and stdout, one message per line. The server
runs in a work area (the parent of the worktrees) and every tool runs
srt itself in the worktree of a series, without a terminal. Whoever
starts the server decides what leaves the machine: upload and push only
show what they would do, unless the server runs with --allow-publish.
"""

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, Any

from stable_rt_tools import about
from stable_rt_tools.srt_util import SubParsers

# The protocol versions this server speaks, newest first
PROTOCOL_VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

# The longest an srt command may take, seconds
TIMEOUT = 3600
# The most output a tool returns, characters
MAX_OUTPUT = 200_000

INSTRUCTIONS = """\
Makes the release of a patch series on top of an upstream release with
srt, e.g. v6.12.118-rt24 of the PREEMPT_RT series v6.12-rt. The maintainer
owns the release: run the local steps and the checks they ask for, and
leave everything which leaves the machine to their explicit OK.

Start with list_series, then status of the series: it lists the steps
done and the next one, and warns when the prepared release doesn't fit
the fetched branches. check runs the sanity checks between the trees.

Quilt workflow: prep, refresh, check (review the queue with queue_diff),
queue_draft (the maintainer completes the announcement), queue with the
message, rebase, merge, release, check. Then STOP: the maintainer tests
the release. Then create, sign, check, upload and push (dry runs; the real
ones only with the maintainer's OK and when the server allows them) and
announce, which returns the mail for the maintainer to send. undo takes a
release back as long as nothing is pushed.

Every step returns the output of srt and the status afterwards. A failed
step returns srt's message: report it, don't work around it."""

_SERIES = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')


class ToolError(Exception):
    """A tool call failed: the result reports it to the agent."""


@dataclass
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    run: Callable[[dict[str, Any]], dict[str, Any]]
    read_only: bool = False
    destructive: bool = False
    open_world: bool = False

    def describe(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'inputSchema': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {},
                **self.schema,
            },
            'annotations': {
                'readOnlyHint': self.read_only,
                'destructiveHint': self.destructive,
                'idempotentHint': self.read_only,
                'openWorldHint': self.open_world,
            },
        }


@dataclass
class Result:
    """What an srt command did."""

    exit_code: int
    stdout: str
    stderr: str


def run_srt(args: list[str], cwd: str) -> Result:
    """Run srt args in cwd, without a terminal and an editor."""
    env = dict(os.environ, GIT_EDITOR='true', GIT_TERMINAL_PROMPT='0')
    p = subprocess.run([sys.executable, '-m', 'stable_rt_tools.srt', *args],
                       cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, encoding='utf-8',
                       errors='replace', timeout=TIMEOUT)
    return Result(p.returncode, p.stdout, p.stderr)


@dataclass
class Options:
    """What the one who starts the server decides, never the agent."""

    root: str
    allow_publish: bool = False
    run: Callable[[list[str], str], Result] = field(default=run_srt)


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f'\n[{len(text) - MAX_OUTPUT} more characters]'


def _next(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        if line.startswith('next: '):
            return line[len('next: '):]
    return None


class Server:
    """The tools, and the protocol."""

    def __init__(self, opts: Options) -> None:
        self.opts = opts
        self.root = os.path.abspath(opts.root)
        self.tools = {t.name: t for t in self._tools()}

    # --- tool definitions ---------------------------------------------------

    def _tools(self) -> list[Tool]:
        series = {'series': {
            'type': 'string',
            'description': 'the worktree of the series in the work area, '
            'e.g. v6.12-rt (see list_series)'}}
        one = {'properties': series, 'required': ['series']}

        def step(name: str, args: list[str], text: str,
                 destructive: bool = False) -> Tool:
            return Tool(name, text, one,
                        lambda a: self._step(a, args), destructive=destructive)

        publish = ('Only a dry run unless the server runs with '
                   '--allow-publish and dry_run is false.')
        return [
            Tool('list_series',
                 'The series of the work area (worktrees with -patches or '
                 '-rebase next to them) and their prepared release.',
                 {}, self._list_series, read_only=True),
            Tool('status',
                 'The prepared release of the series: old and new tag, the '
                 'steps done, warnings (published already, newer release, '
                 'newer upstream) and the next step.',
                 one, self._status, read_only=True),
            Tool('check',
                 'Sanity checks between the trees of the release, each once '
                 'its step is done: upstream, queue (patches added, dropped '
                 'or changed beyond hunk offsets), rebase, merge message, '
                 'release tree, delta, files, signatures. ok, warn, fail '
                 'or skip.',
                 one, self._check, read_only=True),
            Tool('queue_diff',
                 'The refreshed patch queue against the queue of the last '
                 'release (git diff of patches/), to review it.',
                 one, self._queue_diff, read_only=True),
            Tool('prep',
                 'Prepare the next release: update the upstream worktree '
                 '(git pull --ff-only) and record old and new tag.',
                 {'properties': {**series, 'no_pull': {
                     'type': 'boolean', 'default': False,
                     'description': "don't update the upstream worktree"}},
                  'required': ['series']},
                 self._prep),
            Tool('prep_clear',
                 'Forget the prepared release, e.g. when status says it is '
                 'stale. The tags and commits stay.',
                 one, lambda a: self._step(a, ['prep', '--clear']),
                 destructive=True),
            Tool('refresh',
                 'Refresh the patch queue on the new upstream release. '
                 'A patch upstream contains already stops the refresh, '
                 'unless drop_applied (ask the maintainer first).',
                 {'properties': {**series, 'drop_applied': {
                     'type': 'boolean', 'default': False,
                     'description': 'drop patches upstream contains'}},
                  'required': ['series']},
                 self._refresh),
            Tool('queue_draft',
                 'The announcement srt generates for the queue commit, for '
                 'the maintainer to complete.',
                 one, self._queue_draft, read_only=True),
            Tool('queue',
                 'Commit and tag the patch queue with the announcement as '
                 'message (the generated one without message).',
                 {'properties': {**series, 'message': {
                     'type': 'string',
                     'description': 'the completed announcement'}},
                  'required': ['series']},
                 self._queue),
            step('rebase', ['-y', 'quilt', 'rebase'],
                 'Reset -rebase to the upstream release, import the queue '
                 'and tag it.'),
            step('merge', ['quilt', 'merge'],
                 'Merge the upstream release into the series and apply the '
                 'added patches. A conflict stops it: the maintainer '
                 'resolves it.'),
            step('release', ['-y', 'quilt', 'release'],
                 'Commit and tag the release, after checking its tree is '
                 'the one of -rebase. Then the maintainer tests it.'),
            step('undo', ['-y', 'quilt', 'undo'],
                 'Undo queue..release as long as nothing is pushed: delete '
                 'the local tags, reset the series, keep the refreshed '
                 'patches.', destructive=True),
            step('create', ['create'],
                 'Write the patch and the tarball of the release.'),
            step('sign', ['sign'],
                 'Sign the patch and the tarball with the maintainer\'s '
                 'GPG key.'),
            Tool('announce',
                 'The release announcement as mail, for the maintainer to '
                 'send. Sends nothing.',
                 one, self._announce),
            Tool('upload',
                 'Upload the patch and the tarball to kernel.org with '
                 'kup. ' + publish,
                 self._publish_schema(series), lambda a: self._publish(
                     a, 'upload'), destructive=True, open_world=True),
            Tool('push',
                 'Push the release branches and tags. ' + publish,
                 self._publish_schema(series), lambda a: self._publish(
                     a, 'push'), destructive=True, open_world=True),
        ]

    @staticmethod
    def _publish_schema(series: dict[str, Any]) -> dict[str, Any]:
        return {'properties': {**series, 'dry_run': {
            'type': 'boolean', 'default': True,
            'description': 'only show what would happen'}},
            'required': ['series']}

    # --- tools --------------------------------------------------------------

    def _worktree(self, args: dict[str, Any]) -> str:
        name = args.get('series')
        if not isinstance(name, str) or not _SERIES.fullmatch(name):
            raise ToolError('series must be the name of a worktree, e.g. '
                            'v6.12-rt')
        path = os.path.join(self.root, name)
        if not os.path.exists(os.path.join(path, '.git')):
            raise ToolError(f'{name} is not a worktree in {self.root}')
        return path

    def _srt(self, path: str, args: list[str],
             ok: tuple[int, ...] = (0,)) -> Result:
        r = self.opts.run(args, path)
        if r.exit_code not in ok:
            raise ToolError(f'srt {" ".join(args)} failed with exit code '
                            f'{r.exit_code}:\n{_clip(r.stdout)}'
                            f'{_clip(r.stderr)}')
        return r

    def _json(self, path: str, args: list[str],
              ok: tuple[int, ...] = (0,)) -> Any:
        r = self._srt(path, args, ok)
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError as err:
            raise ToolError(f'srt {" ".join(args)} failed with exit code '
                            f'{r.exit_code} and no JSON ({err}):\n'
                            f'{_clip(r.stdout)}{_clip(r.stderr)}') from err

    def _status_of(self, path: str) -> dict[str, Any]:
        info: dict[str, Any] = self._json(path, ['status', '--json'])
        return info

    def _step(self, args: dict[str, Any], srt_args: list[str]) -> \
            dict[str, Any]:
        path = self._worktree(args)
        r = self._srt(path, srt_args)
        output = r.stdout + r.stderr
        return {
            'command': 'srt ' + ' '.join(srt_args),
            'output': _clip(output),
            'next': _next(output),
            'status': self._status_of(path),
        }

    def _list_series(self, args: dict[str, Any]) -> dict[str, Any]:
        names = sorted(os.listdir(self.root))
        series = []
        for name in names:
            path = os.path.join(self.root, name)
            if not os.path.exists(os.path.join(path, '.git')):
                continue
            if not any(f'{name}{s}' in names for s in ('-patches', '-rebase')):
                continue
            series.append({'series': name, 'status': self._status_of(path)})
        return {'root': self.root, 'series': series}

    def _status(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._status_of(self._worktree(args))

    def _check(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._worktree(args)
        # 1: a check failed, the checks are the result
        checks = self._json(path, ['check', '--json'], ok=(0, 1))
        return {'checks': checks,
                'failed': [c['name'] for c in checks if c['result'] == 'fail']}

    def _queue_diff(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._worktree(args)
        info = self._status_of(path)
        if not info.get('prepared'):
            raise ToolError('no release prepared: prep first')
        patches = path + '-patches'
        if not os.path.isdir(patches):
            raise ToolError(f'{patches} does not exist (quilt workflow only)')
        old = f"{info['old_tag']}-patches"
        cmd = ['git', '-C', patches, 'diff', old]
        queued = any(s['step'] == 'srt quilt queue' and s['done']
                     for s in info['steps'])
        if queued:
            cmd.append(f"{info['new_tag']}-patches")
        cmd += ['--', 'patches']
        p = subprocess.run(cmd, capture_output=True, encoding='utf-8',
                           errors='replace')
        if p.returncode:
            raise ToolError(f'{" ".join(cmd)} failed: {p.stderr}')
        return {'command': ' '.join(cmd), 'diff': _clip(p.stdout)}

    def _prep(self, args: dict[str, Any]) -> dict[str, Any]:
        no_pull = args.get('no_pull', False)
        if not isinstance(no_pull, bool):
            raise ToolError('no_pull must be a boolean')
        return self._step(args, ['prep'] + (['--no-pull'] if no_pull else []))

    def _refresh(self, args: dict[str, Any]) -> dict[str, Any]:
        drop = args.get('drop_applied', False)
        if not isinstance(drop, bool):
            raise ToolError('drop_applied must be a boolean')
        return self._step(args, (['-y'] if drop else []) +
                          ['quilt', 'refresh'])

    def _queue_draft(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._worktree(args)
        r = self._srt(path, ['quilt', 'queue', '--draft'])
        return {'announcement': r.stdout}

    def _queue(self, args: dict[str, Any]) -> dict[str, Any]:
        message = args.get('message')
        if message is None:
            return self._step(args, ['-y', 'quilt', 'queue', '--no-edit'])
        if not isinstance(message, str) or not message.strip():
            raise ToolError('message must be the announcement text')
        with tempfile.NamedTemporaryFile('w', suffix='.txt',
                                         delete=False) as f:
            f.write(message if message.endswith('\n') else message + '\n')
        try:
            return self._step(args, ['-y', 'quilt', 'queue', '-F', f.name])
        finally:
            os.remove(f.name)

    def _announce(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._worktree(args)
        r = self._srt(path, ['announce'])
        return {'mail': _clip(r.stdout), 'next': _next(r.stderr)}

    def _publish(self, args: dict[str, Any], what: str) -> dict[str, Any]:
        dry_run = args.get('dry_run', True)
        if not isinstance(dry_run, bool):
            raise ToolError('dry_run must be a boolean')
        if not dry_run and not self.opts.allow_publish:
            raise ToolError(f'srt {what} is not allowed: the server runs '
                            'without --allow-publish. Ask the maintainer to '
                            f'run "srt {what}" or to restart the server '
                            'with --allow-publish.')
        return self._step(args, [what, '--dry-run'] if dry_run
                          else ['-y', what])

    # --- protocol -----------------------------------------------------------

    def handle(self, msg: Any) -> dict[str, Any] | None:
        """The response to msg, None for a notification."""
        if not isinstance(msg, dict) or msg.get('jsonrpc') != '2.0':
            return _error(None, INVALID_REQUEST, 'not a JSON-RPC 2.0 message')
        method, mid = msg.get('method'), msg.get('id')
        if 'id' not in msg:
            return None  # notifications/initialized and the like
        if not isinstance(method, str):
            return _error(mid, INVALID_REQUEST, 'no method')
        params = msg.get('params') or {}
        if not isinstance(params, dict):
            return _error(mid, INVALID_PARAMS, 'params must be an object')
        if method == 'initialize':
            return _result(mid, self._initialize(params))
        if method == 'ping':
            return _result(mid, {})
        if method == 'tools/list':
            return _result(mid, {'tools': [t.describe()
                                           for t in self.tools.values()]})
        if method == 'tools/call':
            return self._call(mid, params)
        return _error(mid, METHOD_NOT_FOUND, f'unknown method {method}')

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        asked = params.get('protocolVersion')
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {
            'protocolVersion': version,
            'capabilities': {'tools': {'listChanged': False}},
            'serverInfo': {'name': 'srt', 'version': about.__version__},
            'instructions': INSTRUCTIONS,
        }

    def _call(self, mid: Any, params: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(params.get('name', ''))
        if tool is None:
            return _error(mid, INVALID_PARAMS,
                          f"unknown tool {params.get('name')}")
        args = params.get('arguments') or {}
        if not isinstance(args, dict):
            return _error(mid, INVALID_PARAMS, 'arguments must be an object')
        unknown = set(args) - set(tool.schema.get('properties', {}))
        if unknown:
            return _error(mid, INVALID_PARAMS,
                          f'unknown arguments: {sorted(unknown)}')
        try:
            out = tool.run(args)
        except (ToolError, OSError, subprocess.SubprocessError) as err:
            return _result(mid, {'content': [{'type': 'text',
                                              'text': str(err)}],
                                 'isError': True})
        return _result(mid, {
            'content': [{'type': 'text', 'text': json.dumps(out)}],
            'structuredContent': out,
            'isError': False,
        })

    def serve(self, rd: IO[str], wr: IO[str]) -> None:
        """Answer the messages from rd on wr until rd ends."""
        for line in rd:
            if not line.strip():
                continue
            resp: dict[str, Any] | None
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as err:
                resp = _error(None, PARSE_ERROR, str(err))
            else:
                resp = self.handle(msg)
            if resp is not None:
                wr.write(json.dumps(resp) + '\n')
                wr.flush()


def _result(mid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def _error(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {'jsonrpc': '2.0', 'id': mid,
            'error': {'code': code, 'message': message}}


def add_argparser(parser: SubParsers) -> argparse.ArgumentParser:
    prs = parser.add_parser('mcp',
                            help='serve the release steps to an agent '
                            '(MCP over stdin and stdout)')
    prs.add_argument('--dir', default=os.curdir,
                     help='the work area, the parent of the worktrees '
                     '(default: the current directory)')
    prs.add_argument('--allow-publish', action='store_true',
                     help='let the agent run srt upload and srt push for '
                     'real, not only as dry run')
    return prs


def execute(args: argparse.Namespace) -> None:
    if not os.path.isdir(args.dir):
        sys.exit(f'{args.dir} is not a directory')
    server = Server(Options(root=args.dir, allow_publish=args.allow_publish))
    # the client is gone
    with contextlib.suppress(KeyboardInterrupt, BrokenPipeError):
        server.serve(sys.stdin, sys.stdout)
