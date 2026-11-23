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
  release and the checks as JSON, ``srt log --json`` the history of the
  series (see :doc:`userguide`).
- Every command ends with the next step, ``next: ...``.

The status as JSON
------------------

``srt status --json`` (and the ``status`` tool of the MCP server) prints:

``prepared``
    true while a release is in progress: prepared with ``srt prep``, or
    found in the trees with a step not done. false when nothing is in
    progress; ``next`` says what to do then, and when there is a last
    release, the keys below describe it.
``source``
    ``state`` (prepared with ``srt prep``) or ``trees`` (found in the
    trees, without the state, e.g. after ``srt push``).
``workflow``, ``old_tag``, ``new_tag``, ``dropped``, ``added``
    The release; ``dropped`` and ``added`` (the patches of the queue) in
    the quilt workflow only.
``steps``
    The steps in order, ``{"step": "srt quilt refresh", "done": true}``,
    up to ``srt create``, ``srt sign``, ``srt upload``, ``srt push`` and
    ``srt announce``. ``done`` is ``null`` when srt can't tell: ``srt
    upload`` asks kernel.org with ``kup ls``, which needs kup and access
    to kernel.org, ``srt announce`` looks in a local clone of the archive
    of the mailing list (``INBOX``), which it fetches at most every 10
    minutes; neither asks with ``--offline``. ``unknown`` then says why.
    Treat it as "ask the maintainer", not as done or not done. ``srt
    push`` is done when the remote-tracking branch of the series has the
    release: srt push updates it, fetch to see a push made elsewhere. ``srt announce`` is done when the archive has the
    announcement (``[ANNOUNCE] <tag>``, with or without the ``v``), then
    ``mail`` has its ``subject``, ``date``, ``sender``, ``message_id`` and
    ``link``:

    .. code-block:: json

       {"step": "srt announce", "done": true,
        "mail": {"subject": "[ANNOUNCE] v6.12.118-rt24",
                 "date": "2026-11-21T13:57:47+01:00",
                 "sender": "Daniel Wagner <wagi@monom.org>",
                 "message_id": "<5f522636-3555-4694-ac55-923c981eab3f@kernel.org>",
                 "link": "https://lore.kernel.org/stable-rt/5f522636-3555-4694-ac55-923c981eab3f@kernel.org/"}}

    The release is complete (``prepared`` false) once it is announced.
``warnings``, ``next``
    Why the release doesn't fit the fetched branches, and the next step.

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
``log``
    The history of the series (``srt log --json``, the last ``count``
    steps): what srt did when and by whom, e.g. to see what happened
    since the agent last looked or what the maintainer did on the host.
    Where a release stands is what ``status`` says, not the history.
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
``test``
    A dry run: the phases ``srt test`` would run (``TEST_COMMAND``,
    ``TEST_WAIT``, ``TEST_CHECK``). It runs them only if the server runs
    with ``--allow-test`` and the call asks for it (``again``, or
    ``only`` the ``wait`` or the ``check``); it returns the output, the
    exit code and the result the check wrote to ``SRT_TEST_RESULT``, if
    it did. It uses your test lab: an agent runs it only when you ask.
    Like every tool it stops after an hour: run a ``TEST_WAIT`` which
    waits for a test round by hand, or, without ``TEST_WAIT``, let the
    agent submit and check later.

The server needs what srt needs: the configuration (``SRT_CONF`` or
``~/.config/srt.conf``) and, for ``sign`` and the tags, a GPG agent which
has the key unlocked, there is no terminal for a passphrase. Testing the
release stays with the maintainer: ``test`` runs only with
``--allow-test``.

Signing keys
------------

``srt quilt queue``, ``rebase`` and ``release`` create signed tags, and
``srt sign`` signs the release files, all with ``GPG_KEY_ID``. Which key
that is depends on the configuration the srt process gets, and for
``srt mcp`` that is the environment it was registered with, not your
shell's:

.. code-block:: console

  $ claude mcp get srt
  ...
    Environment:
      SRT_CONF=/home/user/.local/share/srt/test
      GNUPGHOME=/home/user/.local/share/srt/test/gnupg

A server registered like this signs with the key of that test
configuration. Such a sandbox key is good for trying the steps; a release
signed with it is not one to publish: undo it (``srt quilt undo``) before
anything is pushed. The announcement names the fingerprint of
``GPG_KEY_ID``, so it would announce the sandbox key as well.

Before the first signing step of a release, compare the key with the one
of the last release:

.. code-block:: console

  $ git -C v6.12-rt verify-tag --raw v6.12.117-rt23 2>&1 | grep -E 'SIG '
  $ GNUPGHOME=... gpg --fingerprint <GPG_KEY_ID in the srt.conf of the server>

The release key changes only when you decide so (and then it's in
pgpkeys.git), never because an agent ran with another configuration.

Agent in a sandbox
~~~~~~~~~~~~~~~~~~

An agent often runs in a sandbox, e.g. a
`Litterbox <https://github.com/Gerharddc/Litterbox>`_ container, which
shares the work area with the host but not your keys. Litterbox passes
SSH keys through its own agent, with a confirmation for each use, but no
GPG keys. Forwarding the host's gpg-agent by hand would let anything
running in the sandbox sign with your release key while the passphrase is
cached, without asking; don't, until the sandbox can confirm each
signature the way Litterbox does for SSH keys.

Until then, split the release between the sandbox and the host, where
your key is. The work area is the same directory on both, so each side
sees what the other did; ``srt status`` and ``srt check`` tell where the
release stands.

1. In the sandbox the agent runs ``prep``, ``refresh``, ``check`` and
   ``queue_diff`` to review the queue, and ``queue_draft`` for the
   announcement. Then it stops.

2. On the host you create the signed tags:

   .. code-block:: console

     $ cd v6.12-rt
     $ srt quilt queue --no-edit     # or -F FILE with the completed one
     $ srt -y quilt rebase
     $ srt quilt merge
     $ srt -y quilt release

3. In the sandbox the agent runs ``check``: the trees, and that the tags
   are signed with the key of the last release. Then you test the release.

4. On the host you sign the release files:

   .. code-block:: console

     $ srt create
     $ srt sign

5. In the sandbox the agent runs ``check`` and the dry runs of ``upload``
   and ``push``.

6. On the host you upload and push (``srt upload``, ``srt push``); the
   agent's ``announce`` returns the mail for you to send.

The agent checks the signatures with the keyring of its configuration. If
the server runs with a sandbox ``GNUPGHOME``, import your public key there
(``gpg --export <key> | GNUPGHOME=... gpg --import``); a public key gives
nothing away. Without it ``srt check`` reports the signatures as bad.

Keep a sandbox key only in a test configuration with a short expiry, for
trying the steps.

Claude Code skill
-----------------

The repository contains a Claude Code skill,
``.claude/skills/srt-release``, which describes the release for an agent:
the rules, the steps of both workflows and where it has to stop for the
maintainer. Copy it to ``~/.claude/skills`` to use it outside of the
repository.
