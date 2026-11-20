Agents
======

srt can be driven by an agent, e.g. Claude Code, while the maintainer keeps
the decisions: what goes into the queue, the announcement, the tests, and
everything which leaves the machine.

Without a terminal
------------------

Every command works without a terminal:

- ``-y``/``--yes`` answers the questions with yes. Without it and without a
  terminal a question counts as no and the step stops.
- ``srt quilt queue --draft`` prints the generated announcement,
  ``-F FILE`` commits the completed one, ``--no-edit`` the generated one.
- ``srt upload --dry-run`` and ``srt push --dry-run`` show what would
  happen.
- ``srt status --json`` and ``srt check --json`` print the state of the
  release and the checks as JSON.
- Every command ends with the next step, ``next: ...``.

MCP server
----------

``srt mcp`` serves the release steps as an
`MCP <https://modelcontextprotocol.io>`_ server on stdin and stdout. It
runs in the work area, the parent of the worktrees, and each tool names its
series, so one server covers all series of the work area:

.. code-block:: console

  $ claude mcp add srt -- srt mcp --dir ~/rt

The tools run srt in the worktree of the series, without a terminal, and
return its output, the next step and the status afterwards:

``list_series``, ``status``, ``check``, ``queue_diff``, ``queue_draft``
    Read the state of a release, check its trees, review the refreshed
    queue and get the generated announcement, with the one of the previous
    release to keep its wording. They change nothing.
``prep``, ``refresh``, ``queue``, ``rebase``, ``merge``, ``release``, ``create``, ``sign``
    The local steps of the quilt workflow. ``refresh`` stops at a patch
    upstream contains already, unless ``drop_applied`` is given; ``queue``
    takes the completed announcement as ``message``.
``undo``, ``prep_clear``
    Take a release back as long as nothing is pushed, forget a prepared
    release.
``announce``
    Returns the release announcement; it sends nothing.
``upload``, ``push``
    Dry runs. They upload and push only if the server runs with
    ``--allow-publish`` and the call asks for it (``dry_run`` false).

The server needs what srt needs: the configuration (``SRT_CONF`` or
``~/.config/srt.conf``) and, for ``sign`` and the tags, a GPG agent which
has the key unlocked, there is no terminal for a passphrase. Testing the
release stays with the maintainer, the server has no tool for it.

Claude Code skill
-----------------

The repository contains a Claude Code skill,
``.claude/skills/srt-release``, which describes the release for an agent:
the rules, the steps of both workflows and where it has to stop for the
maintainer. Copy it to ``~/.claude/skills`` to use it outside of the
repository.
