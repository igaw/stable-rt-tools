Quilt workflow
==============

The quilt workflow maintains the patches as a quilt series. It uses the
PREEMPT_RT series v6.12-rt as example; for a series with another ``SUFFIX``
replace ``rt`` in the names and tags.

Branches and layout
-------------------

The workflow uses four worktrees which must be siblings of each other. The
names matter: ``srt prep`` finds ``../v6.12``, ``../v6.12-rt-patches`` and
``../v6.12-rt-rebase`` relative to the ``v6.12-rt`` worktree::

  rt/
  ├── linux               main repository
  ├── v6.12               stable tree, tracks stable/linux-6.12.y
  ├── v6.12-rt            tracks stable-rt/v6.12-rt
  ├── v6.12-rt-patches    tracks stable-rt/v6.12-rt-patches
  └── v6.12-rt-rebase     tracks stable-rt/v6.12-rt-rebase

``v6.12``
    The stable tree. The RT quilt series is pushed onto it with
    ``srt quilt refresh`` to refresh the patches.
``v6.12-rt``
    The released stable-rt tree, stable releases are merged into it.
``v6.12-rt-patches``
    The RT quilt series (``patches/``).
``v6.12-rt-rebase``
    The quilt series imported on top of the latest stable release.

Configuration
-------------

One group describes the series, see :doc:`userguide` for all settings:

.. code-block:: ini

  [linux/stable-rt/v6.12-rt]
  WORKFLOW = quilt
  UPSTREAM_BRANCH = linux-6.12.y
  PRJ_DIR = /pub/linux/kernel/projects/rt/6.12

with the URLs in ``[DEFAULT]`` as in the example there.

Set up a work area
------------------

For a series which exists on kernel.org already:

.. code-block:: console

  $ mkdir rt && cd rt
  $ srt setup linux/stable-rt/v6.12-rt

This clones the repository, adds the remotes (fetching via https, pushing
via gitolite) and creates the four worktrees. Nothing is pushed. Rerun it to
check an existing work area.

Work on a series of another maintainer
--------------------------------------

The series of the maintainer group are in the shared stable-rt tree, e.g.
linux-6.18.y-rt, linux-6.18.y-rt-patches and linux-6.18.y-rt-rebase. To help
out on one, add it to your work area like any series:

.. code-block:: console

  $ cd rt
  $ srt setup linux/stable-rt/linux-6.18.y-rt --workflow quilt \
        --upstream-branch linux-6.18.y --prj-dir /pub/linux/kernel/projects/rt/6.18

``srt setup`` adds the group to ``srt.conf``, with the URLs of the work
area's remotes, and creates the worktrees of the series next to the ones
you have already.

To continue a series under a new name, e.g. as v6.18-rt, start it from the
existing branches with ``--from``:

.. code-block:: console

  $ srt setup linux/stable-rt/v6.18-rt --workflow quilt \
        --upstream-branch linux-6.18.y --prj-dir /pub/linux/kernel/projects/rt/6.18 \
        --from linux-6.18.y-rt
  ...
  new   .../rt/v6.18-rt (v6.18-rt from stable-rt/linux-6.18.y-rt)
  new   .../rt/v6.18-rt-patches (v6.18-rt-patches from stable-rt/linux-6.18.y-rt-patches)
  new   .../rt/v6.18-rt-rebase (v6.18-rt-rebase from stable-rt/linux-6.18.y-rt-rebase)
  publish the series on stable-rt (srt setup pushes nothing):
    git -C .../rt/v6.18-rt push -u --follow-tags stable-rt v6.18-rt
    git -C .../rt/v6.18-rt-patches push -u --follow-tags stable-rt v6.18-rt-patches
    git -C .../rt/v6.18-rt-rebase push -u --follow-tags stable-rt v6.18-rt-rebase

``srt setup`` creates the branches and prints how to publish them; it
pushes nothing. ``--from`` is not stored, after the push ``srt setup
linux/stable-rt/v6.18-rt`` checks the series like any other. Branches of
another tree, e.g. rt-devel, are given as ``--from
rt-devel/linux-6.18.y-rt`` and, if the remote does not exist yet,
``--from-url``.

Create a new release
--------------------

The release is made in a fixed sequence of steps. ``srt prep`` records the
release (``OLD_TAG``, ``NEW_TAG`` and the worktrees) and every ``srt quilt``
step works on the right worktree itself, so all commands are run from
``v6.12-rt``. ``srt status`` shows the steps done and the next one:

.. code-block:: console

  $ cd v6.12-rt
  $ srt prep
  Updating .../rt/v6.12 (git pull --ff-only)
  OLD_TAG=v6.12.111-rt21
  NEW_TAG=v6.12.116-rt22
  next: srt quilt refresh

  [add or drop patches, see below]

  $ srt quilt refresh
  $ srt check
  $ git -C ../v6.12-rt-patches diff
  $ srt quilt queue
  $ srt quilt rebase
  $ srt quilt merge
  $ srt quilt release

  [test the release, see below]

  $ srt create
  $ srt sign
  $ srt check
  $ srt upload
  $ srt push                 # with MAILER: opens the announcement
                             # or: srt announce --mail
  # without MAILER:
  $ srt announce > ../announce-rt
  $ mutt -H ../announce-rt

The steps follow the linux-6.18.y-rt releases. The tags are created in the
order ``-patches``, ``-rebase``, release.

``srt prep``
    Updates ``v6.12`` with ``git pull --ff-only`` (skip it with
    ``--no-pull``) and determines the new release from the latest stable
    tag, e.g. ``v6.12.116-rt22``. A release without a new stable release
    (only RT changes) gets the same stable version and the next -rt number.

``srt quilt refresh``
    Pushes the RT series onto ``v6.12`` one patch at a time, refreshes each
    patch, sets ``localversion-rt`` and pops the series again. It ignores
    ``~/.quiltrc`` and refreshes the patches in the format the RT series
    uses (``-p ab --no-index --no-timestamps``, GNU diff function context),
    so only hunk offsets and the localversion change. A patch which stable
    already contains is detected and srt offers to drop it from the series.
    If a patch doesn't apply, fix it in ``v6.12`` (``quilt push -f``,
    edit, ``quilt refresh``) and rerun ``srt quilt refresh``.

``srt quilt queue``
    Commits ``patches/`` in ``v6.12-rt-patches``, including added and removed
    patch files, with the announcement as commit message and tags it
    ``v6.12.116-rt22-patches``. The editor is opened to complete the
    announcement; the dropped and added patches are listed already.
    Without an editor: ``--draft`` prints the generated announcement,
    ``-F FILE`` commits the completed one from a file, ``--no-edit``
    commits the generated one as it is.
    ``srt announce`` prints this announcement with the mail headers, the
    shortlog since the last release and the delta patch appended.

``srt quilt rebase``
    Resets ``v6.12-rt-rebase`` to ``v6.12.116``, imports the tagged patch
    queue with ``git quiltimport`` and tags it ``v6.12.116-rt22-rebase``.

``srt quilt merge``
    Merges the ``v6.12.116`` tag into ``v6.12-rt`` with a sign-off and
    applies the added patches with ``git am``. On a conflict resolve it,
    ``git commit -s`` (or ``git am --continue``) and rerun
    ``srt quilt merge``.

``srt quilt release``
    Sets ``localversion-rt``, checks that the tree is identical to
    ``v6.12.116-rt22-rebase``, commits ``v6.12.116-rt22`` and tags it. If the
    trees differ, e.g. because stable picked up an RT patch in a different
    form, srt shows the difference; commit a fixup in ``v6.12-rt`` and rerun
    ``srt quilt release``.

``srt create``
    Writes ``patch-6.12.116-rt22.patch.xz``, the diff from ``v6.12.116`` to
    the release, and ``patches-6.12.116-rt22.tar.xz``, the ``patches/``
    directory of ``v6.12.116-rt22-patches`` as it is (series file,
    comments and patch names), to ``patches/v6.12.116-rt22``.

``srt check``
    Sanity checks between the trees, each once its step is done: the
    refreshed queue against the one of ``v6.12.111-rt21-patches`` (patches
    added, dropped, or changed beyond their hunk offsets, with the
    ``git diff`` to review them), ``-rebase`` is ``v6.12.116`` with the
    patches of the queue in order, the stable merge message, the release
    has the tree of ``-rebase``, the delta of the release without the stable
    update, the patch and the tarball match the tags, and the signatures.
    It exits with 1 if a check fails; ``--json`` prints the checks for
    scripts. Run it any time, at the latest before ``srt upload``.

Every step can be rerun: finished work is detected and skipped.
``srt quilt undo`` undoes the steps as long as nothing is pushed.

Test the release
~~~~~~~~~~~~~~~~

Test the release after ``srt quilt release`` and before ``srt create``,
``srt sign``, ``srt upload`` and ``srt push``. At this point ``v6.12-rt``
holds exactly what gets released, and nothing has left the machine yet:
the tags are local, the tarballs are not created and nothing is pushed.

Build and boot ``v6.12-rt`` with your test setup and run the RT tests on
the target boards, e.g. with `srt-build <https://github.com/igaw/srt-build>`_
and LAVA, from within the ``v6.12-rt`` worktree. srt itself doesn't run
tests.

If a test fails, undo the release with ``srt quilt undo``, fix the patch
queue and redo the release:

.. code-block:: console

  $ srt quilt undo
  undo the v6.12.116-rt22 release:
    delete tag v6.12.116-rt22
    delete tag v6.12.116-rt22-rebase
    delete tag v6.12.116-rt22-patches
    reset .../rt/v6.12-rt to stable-rt/v6.12-rt, dropping:
      74e55e127cb5 v6.12.116-rt22
      2eb339592977 Merge tag 'v6.12.116' into v6.12-rt
    undo the queue commit in .../rt/v6.12-rt-patches, keeping the patches
  OK to undo? (y/n): y

  [fix or add the patch in ../v6.12-rt-patches/patches]

  $ srt quilt refresh
  $ srt quilt queue
  $ srt quilt rebase
  $ srt quilt merge
  $ srt quilt release

  [test again]

``srt quilt undo`` deletes the local release tags, resets ``v6.12-rt`` to
its upstream branch and undoes the queue commit, keeping the refreshed
patches staged. ``srt quilt rebase`` resets ``v6.12-rt-rebase`` itself, so
it needs no cleanup. ``srt quilt undo`` refuses to undo anything which is
pushed already. It works the same way to abandon a release at any step.

Add or drop patches
~~~~~~~~~~~~~~~~~~~

The patch queue is edited in ``v6.12-rt-patches/patches`` before
``srt quilt refresh``. srt compares the series with the one of
``OLD_TAG-patches`` to find the added and dropped patches.

To add a patch, put it in ``patches/`` and add it to ``series``. Use the
mail format with ``From:``, ``Date:`` and ``Subject:``, e.g. for an
upstream commit:

.. code-block:: console

  $ git format-patch -1 --stdout --no-signature --zero-commit 5f339c46f153 \
        > ../v6.12-rt-patches/patches/printk-Postpone-kthread-startup.patch
  $ vim ../v6.12-rt-patches/patches/series

``srt quilt merge`` applies it on ``v6.12-rt`` with ``git am``.

To drop a patch, remove it from ``series`` and delete the file. A patch
which stable picked up is found by ``srt quilt refresh``. On ``v6.12-rt``
the stable merge usually brings in the same change; if the trees differ
afterwards, ``srt quilt release`` asks for a fixup commit.

Release state
~~~~~~~~~~~~~

The ``srt prep`` command stores release state in git metadata shared by the
worktrees, one release per series: a work area with v6.12-rt and v6.18-rt
can have a release prepared for each. ``srt quilt``, ``srt status``, ``srt create``, ``srt sign``,
``srt upload`` and ``srt push`` read this state automatically when tags are
not provided explicitly. ``srt push`` clears the state after a successful push;
the history of the series, ``srt log``, stays (see :doc:`userguide`).
If a workflow gets interrupted, clear it manually with ``srt prep --clear``.

``srt status`` shows the steps done, ``srt create``, ``srt sign``,
``srt upload`` and ``srt push`` included, and the next step. It warns when
the prepared release doesn't fit the fetched branches anymore: the release
was published already, e.g. by another maintainer of the group, the series
has a newer release than the one the release was prepared on, or upstream
has a newer release before ``srt quilt refresh``. ``srt status --json``
prints the same for scripts.

The steps are found in the trees, the state only names the release:

- ``srt quilt refresh``: the localversion patch of the queue in
  ``v6.12-rt-patches/patches`` sets the localversion of the release
  (``-rt22``, ``srt quilt refresh`` writes it last), or the ``-patches``
  tag exists. After ``srt quilt undo``, which keeps the refreshed patches,
  the state says they need a refresh again.
- ``srt quilt queue``, ``rebase`` and ``release``: their tags.
  ``srt quilt merge``: upstream is merged and the added patches are
  applied.
- ``srt create`` and ``srt sign``: their files in ``patches/<tag>``.
- ``srt upload``: ``kup ls PRJ_DIR/older`` lists the files and their
  signatures. It is only asked once the files are signed; without kup,
  network or access to kernel.org the step is unknown (``[?]``), as with
  ``srt status --offline``, which doesn't ask.
- ``srt push``: the remote-tracking branch of the series has the release
  tag. It shows the last fetch: fetch first to see a push of another
  maintainer.

Without the state, e.g. after ``srt push`` or when it got lost, ``srt
status`` finds the release in the trees: the release after the last one
on the branch (``HEAD``) if one of its steps is done (a tag of it exists or
the queue is refreshed for it), else the last release itself. When all
steps of the last release are done, nothing is in progress: it shows that
release and ``next: srt prep`` once upstream has a newer release.

Release candidates are not supported by the quilt workflow.
