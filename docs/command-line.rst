Command line usage
==================

The options of all commands, as ``srt --help`` and ``srt <command>
--help`` show them. :doc:`commands` describes what each command does.

.. argparse::
    :module: stable_rt_tools.srt
    :func: srt_get_argparser
    :prog: srt


.. _environment-variables:

Environment variables
---------------------

srt reads these environment variables:

``OLD_TAG``, ``NEW_TAG``
    The release ``srt create``, ``srt sign``, ``srt upload``, ``srt
    push``, ``srt announce`` and ``srt check`` work on, when it isn't
    given as arguments. They come before the state of ``srt prep`` and
    the history of the branch, see :ref:`release-lookup`. ``srt status``
    and the ``srt quilt`` steps don't read them.
``SRT_CONF``
    A directory which is searched for ``srt.conf`` first, before the
    current directory, ``~/.config``, ``~`` and ``/etc/srt`` (see
    :doc:`userguide`). ``srt setup`` adds a new group to
    ``$SRT_CONF/srt.conf`` instead of ``~/.config/srt.conf``. Useful for
    a test configuration, e.g. for ``srt mcp`` (see :doc:`agents`).
``GNUPGHOME``
    The GnuPG home directory, unless ``srt.conf`` sets ``GNUPGHOME``;
    default ``~/.gnupg``. srt passes it to gpg and to the git commands
    which sign or commit (``srt tag``, ``srt commit``, the ``srt quilt``
    steps); ``srt sign``, ``srt check`` and ``srt announce`` (the
    fingerprint of the key) call gpg with it.
``XDG_CACHE_HOME``
    Where ``srt status`` keeps its clone of the archive of the mailing
    list (``INBOX``): ``$XDG_CACHE_HOME/srt/inbox``, default
    ``~/.cache/srt/inbox``. A cache, remove it any time.
``TMPDIR``
    Where ``srt announce --mail`` (and ``srt push``, when it opens the
    announcement) writes the mail: ``announce-<tag>`` in a new directory
    ``srt-announce-*`` in ``$TMPDIR``, default ``/tmp``. srt leaves it
    there for the mail client. ``srt quilt queue`` writes the generated
    commit message to a temporary file there for git.
``GIT_EDITOR``, ``VISUAL``, ``EDITOR``
    Not read by srt itself: ``srt quilt queue`` runs ``git commit
    --edit``, and git chooses the editor (``GIT_EDITOR``,
    ``core.editor``, ``VISUAL``, ``EDITOR``). ``srt mcp`` runs srt with
    ``GIT_EDITOR=true``, so the editor never opens there.
``HOME``
    For ``~/.config/srt.conf``, ``~/srt.conf``, ``~/.gnupg`` and
    ``~/.cache``, and for git (``~/.gitconfig``: ``user.name``,
    ``user.email``, ``user.signingkey``).

srt sets some variables for the programs it runs:

``QUILT_PATCHES``, ``QUILT_DIFF_OPTS``
    ``srt quilt refresh`` sets them for quilt, to the patch queue of the
    ``-patches`` worktree and the diff options of the series, and runs
    quilt with ``--quiltrc -``: your settings for quilt don't apply.
``GIT_TERMINAL_PROMPT=0``
    For the clone and fetch of the archive of the mailing list, and in
    ``srt mcp`` for all of srt: git doesn't ask for credentials.

Everything else is passed on to git, gpg, kup and ssh as it is, e.g.
``GPG_TTY`` or ``SSH_AUTH_SOCK``.

The tests use ``SRT_TEST_INBOX``, see :doc:`devguide`; srt itself
doesn't read it.
