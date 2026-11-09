Quilt workflow
==============

The quilt workflow maintains the RT patches as a quilt series. It uses
v6.12-rt as example.

Branches and layout
-------------------

The workflow uses four worktrees which must be siblings of each other. The
names matter: ``srt prep`` finds ``../v6.12`` and ``../v6.12-rt-patches``
relative to the ``v6.12-rt`` worktree::

  rt/
  ├── linux               main repository
  ├── v6.12               stable tree, tracks stable/linux-6.12.y
  ├── v6.12-rt            tracks stable-rt/v6.12-rt
  ├── v6.12-rt-patches    tracks stable-rt/v6.12-rt-patches
  └── v6.12-rt-rebase     tracks stable-rt/v6.12-rt-rebase

``v6.12``
    The stable tree. The RT quilt series is pushed onto it with
    ``srt quilt`` to refresh the patches.
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

.. code-block:: console

  $ cd v6.12
  $ git pull

  $ cd ../v6.12-rt
  $ srt prep

  $ cd ../v6.12
  $ srt quilt

  $ cd ../v6.12-rt-patches
  $ git add -u
  $ srt patches

  $ cd ../v6.12-rt-rebase
  $ git reset --hard stable/linux-6.12.y
  $ git quiltimport --patches ../v6.12-rt-patches/patches
  $ srt patches

  $ cd ../v6.12-rt
  $ git merge stable/linux-6.12.y
  $ vim localversion-rt
  $ git diff v6.12-rt-rebase
  $ git add -u
  $ srt patches

  $ srt create
  $ srt sign
  $ srt upload
  $ srt push

  $ srt announce > ../announce-rt
  $ mutt -H ../announce-rt

The ``srt prep`` command stores release state in git metadata shared by the
worktrees. Commands such as ``srt patches``, ``srt create``, ``srt sign``,
``srt upload`` and ``srt push`` read this state automatically when tags are
not provided explicitly. ``srt push`` clears the state after a successful push.
If a workflow gets interrupted, clear it manually with ``srt prep --clear``.
