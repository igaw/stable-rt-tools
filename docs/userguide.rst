User Guide
==========

stable-rt-tools (``srt``) supports two release workflows:

- :doc:`git-workflow`: merge based workflow using ``-rt``, ``-rt-rebase``
  and ``-rt-next`` branches (last used for v4.19-rt).
- :doc:`quilt-workflow`: quilt based workflow using ``-rt``,
  ``-rt-patches`` and ``-rt-rebase`` branches (used for v6.12-rt).

This page covers what both workflows have in common: installation,
prerequisites and configuration.

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

- ``git`` including ``git send-email`` (``srt announce``)
- ``gpg`` (GnuPG 2) with your kernel.org signing key (``srt tag``, ``srt sign``,
  ``srt quilt``, ``srt announce``)
- ``kup`` (``srt upload``)
- ``make``, ``gcc``, ``flex`` and ``bison`` to determine the kernel release
  (``srt commit``)
- ``tar`` and ``xz`` (``srt create``, ``srt sign``)
- ``quilt`` and ``patch`` (quilt workflow only, ``srt quilt``)
- optionally ``msmtp`` or ``mutt`` to send the announcement

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
