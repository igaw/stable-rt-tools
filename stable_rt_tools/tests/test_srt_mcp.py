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

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from shutil import rmtree
from typing import Any

from stable_rt_tools.srt_mcp import Options, Result, Server

STATUS = {'prepared': True, 'workflow': 'quilt', 'old_tag': 'v6.12.117-rt23',
          'new_tag': 'v6.12.118-rt24',
          'steps': [{'step': 'srt quilt refresh', 'done': True},
                    {'step': 'srt quilt queue', 'done': False}],
          'warnings': [], 'next': 'srt quilt queue'}


class FakeSrt:
    """Records the srt commands, answers them from a table."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []
        self.files: dict[str, str] = {}
        self.answers: dict[tuple[str, ...], Result] = {}

    def __call__(self, args: list[str], cwd: str) -> Result:
        self.calls.append((args, cwd))
        if '-F' in args:
            with open(args[args.index('-F') + 1]) as f:
                self.files['-F'] = f.read()
        if args == ['status', '--json']:
            return Result(0, json.dumps(STATUS), '')
        return self.answers.get(tuple(args),
                                Result(0, 'done\nnext: srt quilt merge\n', ''))

    def commands(self) -> list[list[str]]:
        return [a for a, _ in self.calls if a != ['status', '--json']]


class TestMcpServer(unittest.TestCase):

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        self.addCleanup(rmtree, self.root)
        for d in ('linux', 'v6.12', 'v6.12-rt', 'v6.12-rt-patches',
                  'v6.12-rt-rebase'):
            os.makedirs(os.path.join(self.root, d, '.git'))
        os.mkdir(os.path.join(self.root, 'not-a-worktree'))
        self.srt = FakeSrt()
        self.server = Server(Options(root=self.root, run=self.srt))

    def server_publishing(self) -> Server:
        return Server(Options(root=self.root, allow_publish=True,
                              run=self.srt))

    def call(self, name: str, server: Server | None = None,
             **args: Any) -> dict[str, Any]:
        resp = (server or self.server).handle(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
             'params': {'name': name, 'arguments': args}})
        assert resp is not None and 'result' in resp, resp
        result: dict[str, Any] = resp['result']
        return result

    def ok(self, name: str, server: Server | None = None,
           **args: Any) -> dict[str, Any]:
        result = self.call(name, server, **args)
        self.assertFalse(result['isError'], result['content'][0]['text'])
        out: dict[str, Any] = result['structuredContent']
        return out

    def error(self, name: str, server: Server | None = None,
              **args: Any) -> str:
        result = self.call(name, server, **args)
        self.assertTrue(result['isError'])
        text: str = result['content'][0]['text']
        return text

    def test_initialize(self) -> None:
        resp = self.server.handle({
            'jsonrpc': '2.0', 'id': 0, 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26'}})
        assert resp is not None
        self.assertEqual(resp['result']['protocolVersion'], '2025-03-26')
        self.assertIn('STOP', resp['result']['instructions'])
        resp = self.server.handle({'jsonrpc': '2.0', 'id': 0,
                                   'method': 'initialize',
                                   'params': {'protocolVersion': '1999'}})
        assert resp is not None
        self.assertEqual(resp['result']['protocolVersion'], '2025-06-18')

    def test_tools_annotations(self) -> None:
        resp = self.server.handle({'jsonrpc': '2.0', 'id': 1,
                                   'method': 'tools/list'})
        assert resp is not None
        tools = {t['name']: t for t in resp['result']['tools']}
        for name in ('list_series', 'status', 'check', 'queue_diff',
                     'queue_draft'):
            self.assertTrue(tools[name]['annotations']['readOnlyHint'], name)
        for name in ('upload', 'push', 'undo', 'prep_clear'):
            self.assertTrue(tools[name]['annotations']['destructiveHint'],
                            name)
        self.assertTrue(tools['push']['annotations']['openWorldHint'])
        for t in tools.values():
            self.assertFalse(t['inputSchema']['additionalProperties'])

    def test_unknown_tool_and_argument(self) -> None:
        resp = self.server.handle({'jsonrpc': '2.0', 'id': 1,
                                   'method': 'tools/call',
                                   'params': {'name': 'nope'}})
        assert resp is not None
        self.assertIn('unknown tool', resp['error']['message'])
        resp = self.server.handle({'jsonrpc': '2.0', 'id': 1,
                                   'method': 'tools/call',
                                   'params': {'name': 'status', 'arguments':
                                              {'series': 'v6.12-rt',
                                               'force': True}}})
        assert resp is not None
        self.assertIn('unknown arguments', resp['error']['message'])

    def test_series_must_be_a_worktree(self) -> None:
        for series in ('../etc', 'not-a-worktree', 'missing', ''):
            self.assertIn('series' if series in ('../etc', '')
                          else 'not a worktree',
                          self.error('status', series=series))
        self.assertEqual(self.srt.calls, [])

    def test_list_series(self) -> None:
        out = self.ok('list_series')
        self.assertEqual([s['series'] for s in out['series']], ['v6.12-rt'])
        self.assertEqual(out['series'][0]['status'], STATUS)

    def test_status(self) -> None:
        self.assertEqual(self.ok('status', series='v6.12-rt'), STATUS)
        self.assertEqual(self.srt.calls,
                         [(['status', '--json'],
                           os.path.join(self.root, 'v6.12-rt'))])

    def test_check_with_a_failure(self) -> None:
        checks = [{'name': 'files', 'result': 'fail', 'text': 'x',
                   'details': []}]
        self.srt.answers[('check', '--json')] = \
            Result(1, json.dumps(checks), '')
        out = self.ok('check', series='v6.12-rt')
        self.assertEqual(out['failed'], ['files'])

    def test_json_failure_shows_srt_error(self) -> None:
        self.srt.answers[('check', '--json')] = \
            Result(1, '', 'Traceback ...\nCalledProcessError: git diff\n')
        text = self.error('check', series='v6.12-rt')
        self.assertIn('exit code 1 and no JSON', text)
        self.assertIn('CalledProcessError: git diff', text)

    def test_step(self) -> None:
        out = self.ok('rebase', series='v6.12-rt')
        self.assertEqual(self.srt.commands(), [['-y', 'quilt', 'rebase']])
        self.assertEqual(out['next'], 'srt quilt merge')
        self.assertEqual(out['status'], STATUS)

    def test_failed_step(self) -> None:
        self.srt.answers[('quilt', 'merge')] = \
            Result(1, 'merge v6.12.118\n', 'merge conflict: resolve it\n')
        text = self.error('merge', series='v6.12-rt')
        self.assertIn('exit code 1', text)
        self.assertIn('merge conflict: resolve it', text)

    def test_refresh(self) -> None:
        self.ok('refresh', series='v6.12-rt')
        self.ok('refresh', series='v6.12-rt', drop_applied=True)
        self.assertEqual(self.srt.commands(), [['quilt', 'refresh'],
                                               ['-y', 'quilt', 'refresh']])

    def test_queue(self) -> None:
        self.ok('queue', series='v6.12-rt')
        self.ok('queue', series='v6.12-rt',
                message='[ANNOUNCE] 6.12.118-rt24\n\nHello RT-list!')
        cmds = self.srt.commands()
        self.assertEqual(cmds[0], ['-y', 'quilt', 'queue', '--no-edit'])
        self.assertEqual(cmds[1][:4], ['-y', 'quilt', 'queue', '-F'])
        self.assertEqual(self.srt.files['-F'],
                         '[ANNOUNCE] 6.12.118-rt24\n\nHello RT-list!\n')
        # the message file is gone
        self.assertFalse(os.path.exists(cmds[1][4]))
        self.assertIn('message', self.error('queue', series='v6.12-rt',
                                            message=' '))

    def test_publish_is_a_dry_run(self) -> None:
        for what in ('upload', 'push'):
            self.ok(what, series='v6.12-rt')
            self.assertIn('--allow-publish',
                          self.error(what, series='v6.12-rt', dry_run=False))
        self.assertEqual(self.srt.commands(), [['upload', '--dry-run'],
                                               ['push', '--dry-run']])

    def test_publish_allowed(self) -> None:
        server = self.server_publishing()
        self.ok('upload', server, series='v6.12-rt', dry_run=False)
        self.ok('push', server, series='v6.12-rt', dry_run=False)
        self.assertEqual(self.srt.commands(), [['-y', 'upload'],
                                               ['-y', 'push']])

    def test_announce(self) -> None:
        self.srt.answers[('announce',)] = \
            Result(0, 'Subject: [ANNOUNCE] v6.12.118-rt24\n',
                   'next: send the announcement\n')
        out = self.ok('announce', series='v6.12-rt')
        self.assertIn('Subject: [ANNOUNCE]', out['mail'])
        self.assertEqual(out['next'], 'send the announcement')

    def test_serve(self) -> None:
        rd = io.StringIO(
            'not json\n'
            '{"jsonrpc": "2.0", "method": "notifications/initialized"}\n'
            '\n'
            '{"jsonrpc": "2.0", "id": 7, "method": "ping"}\n')
        wr = io.StringIO()
        self.server.serve(rd, wr)
        lines = [json.loads(line) for line in wr.getvalue().splitlines()]
        self.assertEqual(lines[0]['error']['code'], -32700)
        self.assertEqual(lines[1], {'jsonrpc': '2.0', 'id': 7, 'result': {}})
        self.assertEqual(len(lines), 2)


class TestMcpProcess(unittest.TestCase):

    def test_srt_mcp(self) -> None:
        """srt mcp answers on stdout, nothing else goes there."""
        with tempfile.TemporaryDirectory() as root:
            msgs = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                     'params': {}},
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                    {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                     'params': {'name': 'list_series'}}]
            p = subprocess.run(
                [sys.executable, '-m', 'stable_rt_tools.srt', 'mcp',
                 '--dir', root],
                input=''.join(json.dumps(m) + '\n' for m in msgs),
                capture_output=True, encoding='utf-8', check=True,
                env=dict(os.environ, SRT_CONF=root))
        out = [json.loads(line) for line in p.stdout.splitlines()]
        self.assertEqual([m['id'] for m in out], [1, 2, 3])
        self.assertEqual(out[0]['result']['serverInfo']['name'], 'srt')
        self.assertIn('push', [t['name'] for t in out[1]['result']['tools']])
        self.assertEqual(out[2]['result']['structuredContent']['series'], [])
