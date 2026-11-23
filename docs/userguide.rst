User Guide
==========

stable-rt-tools (``srt``) supports two release workflows:

- :doc:`git-workflow`: merge based workflow using ``-rt``, ``-rt-rebase``
  and ``-rt-next`` branches (last used for v4.19-rt).
- :doc:`quilt-workflow`: quilt based workflow using ``-rt``,
  ``-rt-patches`` and ``-rt-rebase`` branches (used for v6.12-rt).

This page covers what both workflows have in common: installation,
prerequisites and configuration. :doc:`commands` describes each command.

Installation
------------

srt needs Python 3.12 or newer and has no Python dependencies. Install it
with pip, or pipx to keep it in its own environment, to get the ``srt``
command::

    $ pipx install git+https://github.com/igaw/stable-rt-tools.git

or from a checkout::

    $ pip install .

Prerequisites
-------------

SRT needs kup installed and working.  This means you have write access to
some parts of kernel.org's directory structures and thus have a kernel.org
trusted GPG key and account.

Find kup here: `https://git.kernel.org/pub/scm/utils/kup/kup.git
<https://git.kernel.org/pub/scm/utils/kup/kup.git>`_.

Use kup 0.4 or newer: older versions exit with 0 even when an upload
fails, so ``srt upload`` cannot tell. Since 0.4 kup-server also refuses
signatures of revoked or expired keys.

srt also calls the following external tools:

- ``git`` 2.38 or newer, including ``git send-email`` (``srt announce``)
- ``gpg`` (GnuPG 2) with your kernel.org signing key (``srt tag``, ``srt sign``,
  ``srt quilt``, ``srt announce``)
- ``kup`` (``srt upload``)
- ``tar`` and ``xz`` (``srt create``, ``srt sign``)
- ``quilt`` and ``patch`` (quilt workflow only, ``srt quilt``)
- optionally a mail client (``mutt``, Thunderbird, ...) or ``msmtp`` to
  send the announcement, see ``MAILER``

Repository layout
-----------------

SRT assumes that every branch is checked out in its own git worktree and that
all worktrees are siblings of each other (some commands find the other trees
by relative path, e.g. ``../v6.12-rt-patches``). The workflow pages describe
the exact layout.

The main repository needs a remote called ``origin``. Its URL is only used to
derive the configuration group name (see below), so it does not matter much
what it points to; Linus' tree is a good choice::

    $ git clone https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git linux

Each workflow branch must track the stable-rt branch of the same name, e.g.
the local branch ``v6.12-rt`` tracks ``stable-rt/v6.12-rt``.

Configuration
-------------

srt reads ``srt.conf`` from the first of these directories that has one,
later files fill in what earlier ones leave out::

   $SRT_CONF
   .
   ~/.config
   ~
   /etc/srt

It is an INI file with one group per patch series. The group is named after
the repository, the remote and the branch of the series::

    [<origin basename>/<remote>/<series branch>]

``<origin basename>`` is the last path component of the ``origin`` URL
without ``.git``. For example with::

    origin    https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
    v6.12-rt  tracking stable-rt/v6.12-rt

the group is ``[linux/stable-rt/v6.12-rt]``. The ``-patches``, ``-rebase``
and ``-next`` branches of the series use the same group unless they have one
of their own. Settings shared by all series go into ``[DEFAULT]``.
``srt -d <command>`` prints the group srt is looking for.

A complete configuration for the v6.12-rt series:

.. code-block:: ini

   [DEFAULT]
   GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
   MAIL_TO = LKML <linux-kernel@vger.kernel.org>,<linux-rt-users@vger.kernel.org>,<stable-rt@vger.kernel.org>
   UPSTREAM_GIT_URL = https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
   UPSTREAM_REMOTE = stable
   ORIGIN_GIT_URL = https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
   PRJ_GIT_URL = https://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-stable-rt.git
   PRJ_GIT_TREE = git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt

   [linux/stable-rt/v6.12-rt]
   WORKFLOW = quilt
   UPSTREAM_BRANCH = linux-6.12.y
   PRJ_DIR = /pub/linux/kernel/projects/rt/6.12

The settings:

``WORKFLOW``
    ``quilt`` or ``git`` (default), see :doc:`quilt-workflow` and
    :doc:`git-workflow`. ``quilt_workflow = true`` from srt 1.x still works.
``SUFFIX``
    The release suffix, default ``rt``: releases are tagged
    ``vX.Y.Z-<suffix>N`` and the series branches are named
    ``vX.Y-<suffix>``.
``LOCALVERSION``
    The localversion file, default ``localversion-<suffix>``.
``GPG_KEY_ID``
    The key to sign tags and uploads with, default git's
    ``user.signingkey``. Your key for all the series you work on, so set it
    in ``[DEFAULT]``.
``GNUPGHOME``
    The GnuPG home directory, default ``$GNUPGHOME`` or ``~/.gnupg``.
``SENDER``, ``NAME``
    Your name and email address for the announcements, and your first name
    or nickname for the greeting. Default from git's ``user.name`` and
    ``user.email``.
``MAIL_TO``
    The addresses the announcements and review mails are sent to.
``MAILER``
    The mail client ``srt announce --mail`` opens the announcement in,
    and ``srt push`` offers after the push. Your client for all series,
    so set it in ``[DEFAULT]``. The command line is split like a shell
    splits it (no shell runs it), then in each word ``{mail}`` is
    replaced with the file with the whole mail (``announce-<tag>`` in a
    new directory in ``$TMPDIR`` or ``/tmp``, kept for clients which read
    it after srt is done),
    ``{body}`` with a file with only the body, ``{from}``, ``{to}``,
    ``{cc}`` and ``{subject}`` with the headers. For example:

    .. code-block:: ini

       MAILER = mutt -H {mail}
       MAILER = neomutt -H {mail}
       MAILER = thunderbird -compose "to='{to}',cc='{cc}',subject='{subject}',from='{from}',message='{body}',format=text"

    mutt opens the mail as it is, headers included. Thunderbird takes the
    headers as arguments and the body from the file; ``from`` must be one
    of your Thunderbird identities.
``PRJ_GIT_URL``
    The URL the tree of the series is fetched from (``srt setup``).
``PRJ_GIT_TREE``
    The URL the series is pushed to (``srt push``, ``srt setup``).
``PRJ_DIR``
    The kup directory the release is uploaded to.
``UPSTREAM_GIT_URL``, ``UPSTREAM_BRANCH``
    The tree and branch the series is based on, e.g. stable and
    ``linux-6.12.y`` (``srt setup``).
``UPSTREAM_REMOTE``
    The name of the upstream remote, default ``upstream`` (``srt setup``).
``ORIGIN_GIT_URL``
    What the repository is cloned from, default ``UPSTREAM_GIT_URL``
    (``srt setup``). Its basename is the first part of the group name.
``INBOX``
    The public inbox of the mailing list the announcements go to, default
    ``https://lore.kernel.org/stable-rt``. ``srt status`` shows ``srt
    announce`` as done when its archive has the announcement. srt keeps a
    clone of the archive's git repository (``INBOX/0``) in
    ``$XDG_CACHE_HOME/srt/inbox/<name>.git`` (default
    ``~/.cache/srt/inbox/stable-rt.git``), a cache you can remove any
    time. It clones it the first time a pushed release is looked for and
    fetches it only when the announcement isn't in it yet, at most every 10
    minutes, never with ``srt status --offline``; it never uses the search
    or the web pages of the archive. The same for all series, so set it in
    ``[DEFAULT]``; empty turns the step off (unknown).
``TEST_COMMAND``, ``TEST_WAIT``, ``TEST_CHECK``
    How you test a release in your test lab, in up to three phases,
    each a shell command: ``TEST_COMMAND`` submits the tests (it is what
    makes ``srt test`` work), ``TEST_WAIT`` waits for them and
    ``TEST_CHECK`` judges them; the last two are optional. ``srt test``
    runs them one after the other with ``sh -c`` in the worktree of the
    series (:ref:`cmd-test`). srt also prints them when it is time to
    test, after ``srt quilt release`` and ``srt tag -r N`` (a release
    candidate of the git workflow), and ``srt status`` shows them while
    testing is the next step.

    srt replaces ``{tag}`` with the release (``v6.12.119-rt25``, or
    ``v4.19.291-rt127-rc1``), ``{old_tag}`` with the release before it,
    ``{upstream}`` with the upstream release it is made on
    (``v6.12.119``), ``{series}`` with the series (``v6.12-rt``) and
    ``{worktree}`` with the worktree of the series; other braces, e.g. a
    shell's ``${VAR}``, stay as they are. The commands get the same
    values as ``SRT_TAG``, ``SRT_OLD_TAG``, ``SRT_UPSTREAM``,
    ``SRT_SERIES`` and ``SRT_WORKTREE`` in the environment.

    Why phases: a test round takes hours. srt notes each phase in the
    history, and ``srt test`` run again goes on where it stopped: after
    a dead terminal or a reboot it doesn't submit a second round, it
    waits again. A check alone (``srt test --check``) judges again after
    a job was run again. The check decides: ``srt test`` exits with its
    exit code (without ``TEST_CHECK`` the wait's, without that the
    submit's); a wait that exits with an error doesn't stop the check.
    Without ``TEST_WAIT``, ``srt test`` returns after the submit, and run
    again when the tests are done, it goes on with the check.

    Several lines in a phase are fine: indent the lines after the first.
    Write ``%`` as ``%%`` (``srt.conf`` is read with Python's
    configparser); ``$HOME`` and ``$VAR`` need nothing. A lab for all
    series goes into ``[DEFAULT]``, one for a series into its group.
    ``srt test`` runs as long as its phases, for a whole test round
    hours, so run it in ``tmux`` or ``screen``.

    With `srt-build <https://github.com/igaw/srt-build>`_ and LAVA (its
    ``docs/release-testing.rst``, "With srt test"), srt-build in a
    checkout of its own rather than on ``PATH``:

    .. code-block:: ini

       [linux/stable-rt/v6.12-rt]
       PRJ_DIR = /pub/linux/kernel/projects/rt/6.12
       WORKFLOW = quilt
       TEST_COMMAND =
           cd {worktree}
           $HOME/rt/srt-build/srt-build round start --notes "{tag}" --yes
       TEST_WAIT = $HOME/rt/srt-build/srt-build round wait --report
       TEST_CHECK = $HOME/rt/srt-build/srt-build round compare --check --result "$SRT_TEST_RESULT"

    ``round start`` builds, installs and submits the release round,
    ``round wait --report`` waits for it and fetches it (and exits with
    1 for known problems too: that doesn't decide), and ``round compare
    --check`` compares it with the release round before: it fails only
    for a latency at least 40 % and 20 us longer than before or a job
    that didn't complete. Check the entry without running anything, in
    the worktree of the series::

       $ srt test --dry-run
       testing v6.12.118-rt24 (after v6.12.117-rt23) in .../rt/v6.12-rt
       test with:
           submit:
               cd /home/wagi/rt/v6.12-rt
               $HOME/rt/srt-build/srt-build round start --notes "v6.12.118-rt24" --yes
           wait:
               $HOME/rt/srt-build/srt-build round wait --report
           check:
               $HOME/rt/srt-build/srt-build round compare --check --result "$SRT_TEST_RESULT"

    Building and testing on another machine: the release steps stay
    where the release is made, the phases can run anywhere ``ssh``
    reaches. The release's tags are local until ``srt push``, so give
    the build machine the release first through a remote of its own,
    e.g. ``TEST_COMMAND = git push builder refs/tags/{tag} && ssh
    builder "cd rt/v6.12-rt && git checkout {tag} && srt-build round
    start --notes {tag} --yes"``. A private remote is fine before the
    release is published; never push to the public one before ``srt
    push``.

    For scripts there is a small contract next to the shell commands.
    ``SRT_RELEASE`` is the path of a JSON file with the release:
    ``tag``, ``old_tag``, ``upstream``, ``series``, ``worktree``,
    ``workflow`` (``quilt`` or ``git``) and ``rc`` (``true`` for a
    release candidate). The check gets ``SRT_TEST_RESULT``, the path of
    an empty file it may write its result to, a JSON object with the
    optional fields ``status`` (``pass``, ``fail`` or another word),
    ``summary`` (one line) and ``url``, and any other keys, which srt
    keeps as they are; srt-build's ``round compare --result`` writes it.
    srt notes the result in the history, ``srt status`` shows its
    status, summary and url below ``srt test``. Nothing written: only
    the exit code counts, as without the contract; no JSON: a warning.
    The exit code decides either way; srt warns when ``status`` says
    otherwise. srt removes both files afterwards. A check of your own
    lab could end with:

    .. code-block:: sh

       echo '{"status": "pass", "summary": "54 jobs, no regressions",
              "url": "https://lab.example/round/25"}' > "$SRT_TEST_RESULT"

``ANNOUNCE``, ``RC_TEXT``, ``COMMIT_TMPL``
    Own templates for the announcement, the review mails and the patch
    queue commit, instead of the ones srt ships.

Set up a work area
------------------

``srt setup`` creates the work area of a series as its group describes it:
the repository, the remotes and the worktrees with the right tracking
branches, next to each other in the current directory (or ``--dir``):

.. code-block:: console

  $ mkdir rt && cd rt
  $ srt setup linux/stable-rt/v6.12-rt
  clone https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git into .../rt/linux
  add   remote stable https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
  add   remote stable-rt https://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-stable-rt.git
  set   remote stable-rt push URL git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
  fetch
  add   worktree .../rt/v6.12 (linux-6.12.y tracking stable/linux-6.12.y)
  add   worktree .../rt/v6.12-rt (v6.12-rt tracking stable-rt/v6.12-rt)
  add   worktree .../rt/v6.12-rt-patches (v6.12-rt-patches tracking stable-rt/v6.12-rt-patches)
  add   worktree .../rt/v6.12-rt-rebase (v6.12-rt-rebase tracking stable-rt/v6.12-rt-rebase)
  next: cd .../rt/v6.12-rt && srt prep

Without a group in ``srt.conf`` srt setup takes the settings as options
and adds the group to ``srt.conf`` (``$SRT_CONF`` or ``~/.config``). In an
existing work area the URLs default to the ones of its remotes:

.. code-block:: console

  $ srt setup linux/stable-rt/v6.12-rt --workflow quilt \
        --upstream-branch linux-6.12.y --upstream-remote stable \
        --upstream-url https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git \
        --origin-url https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git \
        --prj-url https://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-stable-rt.git \
        --push-url git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt \
        --prj-dir /pub/linux/kernel/projects/rt/6.12

``srt setup --help`` lists the options. Options which differ from an
existing group are reported, edit ``srt.conf`` to change it.

srt setup can be rerun: existing parts are checked, a remote with another
URL or a worktree on another branch is reported, not changed. Run it in an
existing work area to check it, or to add another series to it. To take
work on a series of another maintainer see :doc:`quilt-workflow`.

Configuration from srt 1.x
--------------------------

The first srt command converts the ``srt.conf`` files it reads to this
format and keeps the old file as ``srt.conf.bak``: ``quilt_workflow =
true`` becomes ``WORKFLOW = quilt``, groups of ``-patches``, ``-rebase``
and ``-next`` branches with the settings of their series and
``LOCALVERSION`` settings with the default value are dropped, your
settings (``GPG_KEY_ID``, ``GNUPGHOME``, ``SENDER``, ``NAME``) and settings
which are the same in all groups move to ``[DEFAULT]``. srt prints what it
changed. Comments are only kept in the backup.

History of a series
-------------------

Every step which changes something adds a line to the history of its
series when it succeeds: ``srt prep`` and ``srt prep --clear``, the
``srt quilt`` steps (``refresh``, ``queue``, ``rebase``, ``merge``,
``release``, ``undo``), ``srt commit``, ``srt tag``, ``srt create``,
``srt sign``, ``srt upload``, ``srt push``, the review mails of a release
candidate sent by ``srt announce`` and the announcement opened in the mail
client by ``srt announce --mail``. Dry runs, drafts, ``srt status``,
``srt check`` and a plain ``srt announce``, which only prints the mail,
change nothing and leave no line, except that ``srt status`` adds
``announced`` once it finds the announcement of a release in the archive
of the mailing list (``INBOX``). A step srt didn't do, e.g. a merge
conflict you resolved by hand, isn't in it either.

``srt log`` shows the history of the series of the current worktree, oldest
first, the time in UTC: a line with the step, the release and who, its
details below; ``-n N`` only the last N steps, ``--json`` all fields for
scripts:

.. code-block:: console

  $ srt log -n 2
  2026-11-21 10:12  quilt release  v6.12.118-rt24 (from v6.12.117-rt23)  by Daniel Wagner
      tag     v6.12.118-rt24
      commit  3f1c0a9e2b7d

  2026-11-21 11:40  create         v6.12.118-rt24 (from v6.12.117-rt23)  by Daniel Wagner
      dir     .../rt/v6.12-rt/patches/v6.12.118-rt24
      files   patch-6.12.118-rt24.patch.xz patches-6.12.118-rt24.tar.xz

The history is for people to read: where a release stands comes from
the trees (``srt status``). The one exception: ``srt status`` takes an
announcement it found once from the ``announced`` line instead of looking
in the archive again, the archive can always tell it again.
It lives in the git directory shared by the worktrees, next to the
prepared release, one file per series:
``<git common dir>/srt/<series>.log``, e.g. ``linux/.git/srt/v6.12-rt.log``.
It can't be recreated from the trees: keep it with the repository, e.g. in
your backups. ``srt prep --clear`` and ``srt push`` forget the prepared
release, not the history. If the history can't be written, srt warns and
the step is done anyway.

Each line is a JSON object (JSON Lines), easy to parse:

``time``
    When the step finished, ISO 8601 in UTC.
``series``
    The series, e.g. ``v6.12-rt``.
``step``
    The command, e.g. ``prep``, ``quilt queue``, ``tag``, ``push``,
    ``announce --mail``.
``release``
    The release the step is about, e.g. ``v6.12.118-rt24`` (also for its
    ``-rebase`` and ``-patches`` tags) or ``v6.12.118-rt24-rc1``.
``old``
    The release before it, if srt knows it (``srt commit`` and ``srt tag``
    only after ``srt prep``).
``srt``
    The version of srt.
``user``
    Who ran the step: git's ``user.name``.

and the details of the step, left out when empty:

- ``prep``: ``workflow``, ``upstream`` (the upstream release).
- ``quilt refresh``: ``upstream``, the ``dropped`` and ``added`` patches.
- ``quilt queue``, ``quilt rebase``, ``quilt release``, ``tag``: ``tag``
  and its ``commit``; ``commit``: ``commit``, ``branch`` and ``subject``.
- ``quilt merge``: ``merged`` (the upstream release), the ``applied``
  patches, ``commit``. Only when it changed something.
- ``quilt undo``: the ``deleted`` tags, ``reset`` (the branch the series
  was reset to), ``queue_commit``, ``removed`` (the directory of the
  files).
- ``create``, ``sign``: ``dir`` and ``files``; ``sign`` also ``key``.
- ``upload``: ``dir`` on kernel.org (``PRJ_DIR``), the ``files``
  uploaded and the ``removed`` ones of the previous release.
- ``push``: ``remote`` and ``refs`` (the arguments of ``git push``),
  ``force`` for a release candidate.
- ``announce``: ``result``, the number of ``mails``, ``to`` and the
  ``message_id`` of the cover letter, as far as git send-email reports it;
  ``announce --mail``: ``result`` (``mail opened``: whether it was sent is
  up to you and the mail client), ``mailer``, ``mail`` (the file) and
  ``message_id``.
- ``announced`` (by ``srt status``): the announcement in the archive of
  the mailing list, its ``subject``, ``date``, ``sender``, ``message_id``
  and ``link`` (to the archive, for people).

Troubleshooting
---------------

srt fails with "Could not retrieve configuration": check that ``origin``
exists, that the current branch tracks the branch of the series
(``git branch -vv``) and that ``srt.conf`` contains the matching group.
``srt -d`` prints the group name srt is looking for. ``srt setup <group>``
checks the whole work area.

srt announce fails: it takes your name and email from git's ``user.name``
and ``user.email``. Set them or ``SENDER`` and ``NAME`` in ``srt.conf``.

srt upload fails: verify kup works following the README in kup, then check
your ``srt.conf`` has the appropriate ``PRJ_DIR`` for the series you are
working with. If that fails check you have proper access to the
``PRJ_DIR`` on kernel.org through the helpdesk.

The ``-d`` option turns on debug tracing for all commands.
