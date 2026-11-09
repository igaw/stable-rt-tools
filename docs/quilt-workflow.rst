Quilt workflow
==============

The quilt workflow maintains the RT patches as a quilt series. It uses
v6.12-rt as example.

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

Add a group for each branch to ``srt.conf`` and enable the quilt workflow in
the ``-rt`` group:

.. code-block:: ini

  [linux/stable-rt/v6.12-rt]
  quilt_workflow = true
  LOCALVERSION = localversion-rt
  GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
  PRJ_GIT_TREE = git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
  PRJ_DIR = /pub/linux/kernel/projects/rt/6.12

  [linux/stable-rt/v6.12-rt-patches]
  LOCALVERSION = localversion-rt
  GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
  PRJ_GIT_TREE = git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
  PRJ_DIR = /pub/linux/kernel/projects/rt/6.12

  [linux/stable-rt/v6.12-rt-rebase]
  LOCALVERSION = localversion-rt
  GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
  PRJ_GIT_TREE = git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
  PRJ_DIR = /pub/linux/kernel/projects/rt/6.12

Set up a work area
------------------

Use this to set up a work area for a stable-rt series which already exists
on kernel.org. Nothing is pushed.

Clone the main repository and add the remotes. Fetch via https (unlike
``git://``, https can be load balanced on the kernel.org side) and push to
stable-rt via gitolite:

.. code-block:: console

  $ mkdir rt && cd rt
  $ git clone https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git linux
  $ cd linux
  $ git remote add stable    https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
  $ git remote add rt-devel  https://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-rt-devel.git
  $ git remote add stable-rt https://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-stable-rt.git
  $ git remote set-url --push stable-rt git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt.git
  $ git fetch --all --tags

Create the worktrees. Each branch tracks the stable-rt branch of the same
name, which is what srt uses to find its configuration group:

.. code-block:: console

  $ git worktree add --track -b linux-6.12.y     ../v6.12            stable/linux-6.12.y
  $ git worktree add --track -b v6.12-rt         ../v6.12-rt         stable-rt/v6.12-rt
  $ git worktree add --track -b v6.12-rt-patches ../v6.12-rt-patches stable-rt/v6.12-rt-patches
  $ git worktree add --track -b v6.12-rt-rebase  ../v6.12-rt-rebase  stable-rt/v6.12-rt-rebase

Verify the setup:

.. code-block:: console

  $ git branch -vv
  + linux-6.12.y     5c40a1750f44 (.../rt/v6.12) [stable/linux-6.12.y] Linux 6.12.116
  + v6.12-rt         7de70ccdb398 (.../rt/v6.12-rt) [stable-rt/v6.12-rt] v6.12.111-rt21
  + v6.12-rt-patches 480df8daae60 (.../rt/v6.12-rt-patches) [stable-rt/v6.12-rt-patches] [ANNOUNCE] 6.12.111-rt21
  + v6.12-rt-rebase  3c7c6f61c0e8 (.../rt/v6.12-rt-rebase) [stable-rt/v6.12-rt-rebase] Add localversion for -RT release

Bootstrap a new series from rt-devel
------------------------------------

Use this only once, when a new stable-rt series is started from the rt-devel
tree. It publishes the branches and tags on stable-rt.

.. code-block:: console

  $ cd linux
  $ git worktree add --track -b linux-6.12.y ../v6.12 stable/linux-6.12.y

  $ git worktree add -b v6.12-rt-patches ../v6.12-rt-patches rt-devel/linux-6.12.y-rt-patches
  $ git worktree add -b v6.12-rt-rebase  ../v6.12-rt-rebase  rt-devel/linux-6.12.y-rt-rebase
  $ git worktree add -b v6.12-rt         ../v6.12-rt         rt-devel/linux-6.12.y-rt

  $ git tag | grep -E '^v6\.12\..*-rt[^-]*-.*$' | xargs -r git push stable-rt

  $ cd ../v6.12-rt-patches
  $ git push -u stable-rt v6.12-rt-patches
  $ git push --dry-run stable-rt $(git tag --merged rt-devel/linux-6.12.y-rt-patches)

  $ cd ../v6.12-rt-rebase
  $ git push -u stable-rt v6.12-rt-rebase

  $ cd ../v6.12-rt
  $ git push -u stable-rt v6.12-rt

``git push -u`` sets the upstream of each branch to stable-rt, which srt
needs to find the configuration group.

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
  $ git -C ../v6.12-rt-patches diff
  $ srt quilt queue
  $ srt quilt rebase
  $ srt quilt merge
  $ srt quilt release

  [test the release, see below]

  $ srt create
  $ srt sign
  $ srt upload
  $ srt push

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

``srt quilt rebase``
    Resets ``v6.12-rt-rebase`` to ``v6.12.116``, imports the tagged patch
    queue with ``git quiltimport`` and tags it ``v6.12.116-rt22-rebase``.

``srt quilt merge``
    Merges the ``v6.12.116`` tag into ``v6.12-rt`` and applies the added
    patches with ``git am``. On a conflict resolve it, ``git commit`` (or
    ``git am --continue``) and rerun ``srt quilt merge``.

``srt quilt release``
    Sets ``localversion-rt``, checks that the tree is identical to
    ``v6.12.116-rt22-rebase``, commits ``v6.12.116-rt22`` and tags it. If the
    trees differ, e.g. because stable picked up an RT patch in a different
    form, srt shows the difference; commit a fixup in ``v6.12-rt`` and rerun
    ``srt quilt release``.

Every step can be rerun: finished work is detected and skipped.

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

If a test fails, fix the patch queue and redo the release. As long as
nothing is pushed, delete the release tags, drop the release commits on
``v6.12-rt`` and undo the queue commit, keeping the refreshed patches:

.. code-block:: console

  $ git tag -d v6.12.116-rt22 v6.12.116-rt22-rebase v6.12.116-rt22-patches
  $ git reset --hard @{u}
  $ git -C ../v6.12-rt-patches reset --soft HEAD~1

  [fix or add the patch in ../v6.12-rt-patches/patches]

  $ srt quilt refresh
  $ srt quilt queue
  $ srt quilt rebase
  $ srt quilt merge
  $ srt quilt release

  [test again]

``srt quilt rebase`` resets ``v6.12-rt-rebase`` itself, it needs no
cleanup.

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
worktrees. ``srt quilt``, ``srt status``, ``srt create``, ``srt sign``,
``srt upload`` and ``srt push`` read this state automatically when tags are
not provided explicitly. ``srt push`` clears the state after a successful push.
If a workflow gets interrupted, clear it manually with ``srt prep --clear``.

Release candidates are not supported by the quilt workflow.

``srt patches`` is deprecated. It still works as before in the worktree it
is called in, but prints the ``srt quilt`` step to use instead.
