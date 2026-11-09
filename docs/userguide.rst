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

srt also calls the following external tools:

- ``git`` including ``git send-email`` (``srt announce``)
- ``gpg2`` with your kernel.org signing key (``srt tag``, ``srt sign``,
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

srt looks for a config file called ``srt.conf`` in the following
directories::

   $SRT_CONF
   .
   ~/.config
   ~
   /etc/srt

It is an INI type configuration file. Each group encodes the repository name
and the upstream branch the current branch tracks::

    [<origin basename>/<upstream remote>/<upstream branch>]

``<origin basename>`` is the last path component of the ``origin`` URL
without a ``.git`` suffix. For example with::

    origin    https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
    v6.12-rt  tracking stable-rt/v6.12-rt

the group is called::

    [linux/stable-rt/v6.12-rt]

You need a group for each workflow branch. Use ``srt -d <command>`` to see
which group srt is looking for.

srt uses the following keys:

``LOCALVERSION``
    The filename of the localversion file, ``localversion-rt``
``GPG_KEY_ID``
    ID of the GPG key used to sign tags and to upload to kernel.org
``PRJ_GIT_TREE``
    URL of the stable-rt git repository to push to
``PRJ_DIR``
    kup folder to upload the release to
``MAIL_TO``
    Email addresses to which the announcement/patches are sent
``SENDER``
    Your name and email address
``NAME``
    Your first name or nickname
``ANNOUNCE`` (optional)
    Email template for a release
``RC_TEXT`` (optional)
    Email template for a release candidate
``quilt_workflow`` (optional)
    Set to ``true`` to enable the quilt workflow, see :doc:`quilt-workflow`

Keys shared by all groups (``MAIL_TO``, ``SENDER``, ``NAME``) can be placed
in the ``[DEFAULT]`` group:

.. code-block:: ini

   [DEFAULT]
   MAIL_TO = LKML <linux-kernel@vger.kernel.org>,<linux-rt-users@vger.kernel.org>,<stable-rt@vger.kernel.org>,Steven Rostedt <rostedt@goodmis.org>,Thomas Gleixner <tglx@linutronix.de>,Sebastian Andrzej Siewior <bigeasy@linutronix.de>,Clark Williams <williams@redhat.com>
   NAME = Daniel
   SENDER = Daniel Wagner <wagi@monom.org>

The workflow pages contain examples of the per branch groups.

Troubleshooting
---------------

srt fails with "Could not retrieve configuration": check that ``origin``
exists, that the current branch tracks the right stable-rt branch
(``git branch -vv``) and that ``srt.conf`` contains the matching group.
``srt -d`` prints the group name srt is looking for.

srt announce fails: it attempts to figure out your name and email from
specific configurations you might not have (say if you are using Ubuntu). If
srt announce fails try adding ``SENDER`` and ``NAME`` to your ``srt.conf``.

srt upload fails: verify kup works following the README in kup, then check
your ``srt.conf`` has the appropriate ``PRJ_DIR`` for the stable-rt version
you are working with. If that fails check you have proper access to the
``PRJ_DIR`` on kernel.org through the helpdesk.

The ``-d`` option turns on debug tracing for all commands.
