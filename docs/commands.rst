Commands
========

This page describes each srt command: what it is for, when it runs in a
release, what it reads and changes, what it asks and what it prints. The
workflow pages, :doc:`quilt-workflow` and :doc:`git-workflow`, show the
commands in the order of a release; :doc:`command-line` lists all
options as ``srt --help`` shows them.

The examples use the PREEMPT_RT series v6.12-rt (quilt workflow) and
v4.19-rt (git workflow) in the work area ``rt/`` of :doc:`userguide`.
``...`` stands for the path of the work area.

.. _which-command:

Which command for which step
----------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 26 32 20

   * - Step
     - Quilt workflow
     - Git workflow
     - Leaves the machine
   * - Set up the work area
     - ``srt setup``
     - ``srt setup``
     - no
   * - Prepare the release
     - ``srt prep``
     - ``srt prep`` (optional)
     - no
   * - Update the patches
     - edit the queue, ``srt quilt refresh``
     - ``git merge`` the upstream release in ``-next``, fix conflicts
     - no
   * - Commit the patch queue
     - ``srt quilt queue``
     - (none)
     - no
   * - The ``-rebase`` branch
     - ``srt quilt rebase``
     - ``git rebase``, ``srt commit``, ``srt tag``
     - no
   * - Merge upstream into the series
     - ``srt quilt merge``
     - ``git merge --ff-only`` the ``-next`` branch
     - no
   * - Commit and tag the release
     - ``srt quilt release``
     - ``srt commit`` (in ``-next``), ``srt tag``
     - no
   * - Release candidate
     - (none)
     - ``srt commit``, ``srt tag -r N``, ``srt announce``, ``srt push``
     - review mails, push
   * - Check the trees
     - ``srt check``
     - ``srt check``
     - no
   * - Test the release
     - ``srt test`` (``TEST_COMMAND``), or your test setup
     - ``srt test`` (``TEST_COMMAND``), or your test setup
     - your test lab
   * - Take the release back
     - ``srt quilt undo``
     - by hand (``git tag -d``, ``git reset``)
     - no
   * - Write the release files
     - ``srt create``
     - ``srt create``
     - no
   * - Sign them
     - ``srt sign``
     - ``srt sign``
     - no
   * - Upload them to kernel.org
     - ``srt upload``
     - ``srt upload``
     - yes
   * - Push branches and tags
     - ``srt push``
     - ``srt push``
     - yes
   * - Announce the release
     - ``srt push`` or ``srt announce --mail``
     - ``srt push`` or ``srt announce --mail``
     - yes, the mail
   * - Where the release stands
     - ``srt status``, ``srt log``
     - ``srt status``, ``srt log``
     - no

Everything up to ``srt sign`` is local and can be redone. ``srt
upload``, ``srt push`` and sending the announcement publish the release:
srt cannot take them back.

.. _release-lookup:

How a command finds the release
-------------------------------

``srt create``, ``srt sign``, ``srt upload``, ``srt push``, ``srt
announce`` and ``srt check`` work on one release, ``OLD_TAG`` ->
``NEW_TAG``, e.g. ``v6.12.117-rt23`` -> ``v6.12.118-rt24``. They take
each tag from the first of:

1. the arguments, ``srt create OLD_TAG NEW_TAG``. A single tag is
   ``NEW_TAG``: ``srt create v6.12.118-rt24`` takes the release before
   it as ``OLD_TAG``.
2. the environment variables ``OLD_TAG`` and ``NEW_TAG``.
3. the state of ``srt prep``, the release prepared for the series of the
   current worktree.
4. the history of the branch: ``NEW_TAG`` is the last release or release
   candidate on the first parents of ``HEAD``, ``OLD_TAG`` the release
   before ``NEW_TAG`` on its first parents. The merged upstream tags,
   ``-rebase`` and ``-patches`` tags don't count, release candidates
   don't count for ``OLD_TAG``. This is local, nothing is fetched.

The history finds a release once it is tagged, so after ``srt push``,
which forgets the prepared release, the commands still find it. If
there is no release tag on ``HEAD``, srt asks for the tags::

  no release tag on HEAD, give the tags: srt <command> OLD_TAG NEW_TAG

Then srt checks that ``OLD_TAG`` and ``NEW_TAG`` differ and that the tags
exist: both, the upstream release of ``NEW_TAG`` (``v6.12.118``) and,
except for a release candidate, ``NEW_TAG-rebase``.

The other commands don't take tags:

- the ``srt quilt`` steps need the state of ``srt prep``, without it they
  stop with "No release prepared".
- ``srt commit`` and ``srt tag`` work on ``HEAD``: the localversion file
  and the release commit.
- ``srt status`` shows the release prepared with ``srt prep``, else the
  release the trees show (see :ref:`cmd-status`). It doesn't read
  ``OLD_TAG`` and ``NEW_TAG``.

The state of ``srt prep`` lives in the git directory shared by the
worktrees, one file per series: ``<git common dir>/srt/<series>.json``,
e.g. ``linux/.git/srt/v6.12-rt.json``. It only names the release and the
worktrees; which steps are done comes from the trees.

.. _questions:

Questions and ``--yes``
-----------------------

Steps which change something others see or which are hard to undo ask
first, e.g. ``OK to tag? (y/n):``. Each command below says what it asks.
Answer ``y`` or ``n``; Ctrl-C or the end of the input (stdin closed)
mean no.

``-y``/``--yes`` answers every question with yes and prints the question
with the answer, e.g. ``OK to tag? (y/n): y (--yes)``. It can be given
before or after the command: ``srt -y quilt release``, ``srt quilt
release --yes``.

A no stops the command with exit status 1 and a message on stderr
(``not committed``, ``not tagged``, ``not uploaded``, ``not pushed``,
``not sent``, ``aborted``), so a script can tell. Nothing is changed:
``srt commit`` resets the localversion file. Rerun the command to
continue. The one question that is not a step, ``srt push`` offering to
open the announcement in the mail client, ends without an error on no.

Without a terminal, e.g. in a script or for an agent (see
:doc:`agents`), use ``--yes`` or the dry runs. ``srt push`` offers to
open the announcement in the mail client only to a person at a terminal,
not with ``--yes``.

.. _output:

Output
------

srt prints what it does and the commands it runs where they matter
(``git push -n ...``, the kup command), on stdout. Every command which
completes a step ends with the next step::

  next: srt quilt queue

``srt announce`` prints the mail on stdout and the ``next:`` line on
stderr, so ``srt announce > ../announce-rt`` writes only the mail. ``srt
status --json``, ``srt check --json`` and ``srt log --json`` print JSON
for scripts.

Errors go to stderr and end the command with exit status 1: a message
which says what to do, e.g. ``run "srt quilt refresh" first``, or for a
failed external command ``srt: <command> failed (exit N)`` with its error
output. ``-d`` prints debug messages, the commands srt runs and a Python
traceback instead. Ctrl-C ends srt with 130, a wrong option with 2.

Each step which changes something adds a line to the history of its
series when it succeeds, see :ref:`cmd-log`.

.. _cmd-setup:

srt setup
---------

Creates or checks the work area of a series, before the first release
and whenever you want to check a work area.

srt setup reads the group of the series in ``srt.conf``, e.g.
``linux/stable-rt/v6.12-rt``, and creates in the current directory (or
``--dir``): the repository (cloned from ``ORIGIN_GIT_URL``), the remotes
of upstream and the series (with ``PRJ_GIT_TREE`` as push URL), and one
worktree per branch, next to each other, each tracking its remote branch.
The quilt workflow gets the upstream worktree ``v6.12`` and ``v6.12-rt``,
``v6.12-rt-patches`` and ``v6.12-rt-rebase``, the git workflow the series
and its ``-rebase`` and ``-next`` branches as far as they exist. It
fetches all remotes with tags.

Existing parts are checked, not changed: a remote with another URL or a
worktree on another branch is an error. Without the group in
``srt.conf``, srt setup takes the settings from the options and appends
the group to ``$SRT_CONF/srt.conf`` or ``~/.config/srt.conf``; options
which differ from an existing group are reported. ``--from`` starts a
series which doesn't exist on the remote yet from other branches. srt
setup asks nothing and pushes nothing; it prints how to publish new
branches.

.. code-block:: console

  $ srt setup linux/stable-rt/v6.12-rt
  ok    .../rt/linux (origin https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git)
  ok    remote stable https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
  ok    remote stable-rt https://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-stable-rt.git
  fetch
  ...
  ok    .../rt/v6.12-rt (v6.12-rt tracking stable-rt/v6.12-rt)
  ok    .../rt/v6.12-rt-patches (v6.12-rt-patches tracking stable-rt/v6.12-rt-patches)
  ok    .../rt/v6.12-rt-rebase (v6.12-rt-rebase tracking stable-rt/v6.12-rt-rebase)
  next: cd .../rt/v6.12-rt && srt prep

See :doc:`userguide` for a new work area and :doc:`quilt-workflow` for
``--from``.

.. _cmd-prep:

srt prep
--------

The first step of a release, run in the worktree of the series
(``v6.12-rt``).

srt prep finds the release: ``OLD_TAG`` is the last release on ``HEAD``,
``NEW_TAG`` the latest upstream release in the upstream worktree
(``../v6.12``) with the next release number. A release without a new
upstream release gets the same upstream version and the next number.
In the quilt workflow srt prep first checks that the four worktrees
exist and updates the upstream worktree with ``git pull --ff-only``
(``--no-pull`` skips that).

It stores the release as the state of srt prep, which the following
commands read (see :ref:`release-lookup`), and prints ``OLD_TAG`` and
``NEW_TAG``. It creates no tags or commits and asks nothing. Run it
again to prepare the release anew, e.g. when upstream has a newer
release.

``srt prep --clear`` forgets the prepared release, e.g. when ``srt
status`` says it is stale; tags, commits and the history stay. ``srt
push`` clears it after the push.

.. code-block:: console

  $ srt prep
  Updating .../rt/v6.12 (git pull --ff-only)
  git -C .../rt/v6.12 pull --ff-only
  OLD_TAG=v6.12.117-rt23
  NEW_TAG=v6.12.118-rt24
  next: srt quilt refresh

In the git workflow the next step is ``git merge v4.19.291, then srt
commit``. srt prep reads the upstream release from the upstream worktree
next to the series (``../v4.19``) in the git workflow too, which ``srt
setup`` creates only for the quilt workflow; the git workflow works
without srt prep.

.. _cmd-quilt:

srt quilt
---------

The release steps of the quilt workflow: ``refresh``, ``queue``,
``rebase``, ``merge`` and ``release``, and ``undo``. ``srt quilt``
without a step runs ``refresh``. The steps read the release prepared with
``srt prep`` and work on the worktrees of the series themselves, so all
of them run in ``v6.12-rt``. Each step checks that the one before is
done, and every step can be rerun: finished work is detected and
skipped. See :doc:`quilt-workflow` for the release as a whole.

.. _cmd-quilt-refresh:

srt quilt refresh
~~~~~~~~~~~~~~~~~

Refreshes the patch queue on the new upstream release, after ``srt prep``
and after you added or dropped patches in ``v6.12-rt-patches/patches``.

It pushes the queue onto the upstream worktree ``v6.12`` one patch at a
time and refreshes each patch in the format of the series
(``-p ab --no-index --no-timestamps``, GNU diff function context),
ignoring ``~/.quiltrc``. Then it writes the localversion of the new
release, e.g. ``-rt24``, into the last patch, the localversion patch, and
pops the queue again. Only hunk offsets and the localversion change.
``v6.12`` must be at the upstream release of ``NEW_TAG``.

It changes the patch files in ``v6.12-rt-patches/patches``, no commits or
tags. A patch upstream contains already is detected and srt asks ``Drop
it from the series? (y/n):``; yes removes it from ``series`` and deletes
the file. If a patch doesn't apply, srt stops: fix it in ``v6.12``
(``quilt push -f``, edit, ``quilt refresh``) and rerun.

.. code-block:: console

  $ srt quilt refresh
  added:   printk-Postpone-kthread-startup.patch
  review: srt check, git -C .../rt/v6.12-rt-patches diff
  next: srt quilt queue

.. _cmd-quilt-queue:

srt quilt queue
~~~~~~~~~~~~~~~

Commits the refreshed queue with the announcement of the release and
tags it, after ``srt quilt refresh`` and the review of the queue.

It commits ``patches/`` in ``v6.12-rt-patches``, added and removed files
included, signed off, and tags the commit ``v6.12.118-rt24-patches``,
signed with ``GPG_KEY_ID``. The commit message is the announcement,
generated from ``COMMIT_TMPL`` with the dropped and added patches (``-
none`` for an upstream update only). git opens it in the editor to
complete it. Without an editor:

``--draft``
    prints the generated announcement and changes nothing.
``-F FILE``
    commits the announcement in ``FILE`` as it is.
``--no-edit``
    commits the generated announcement as it is.

srt asks ``OK to tag? (y/n):`` before it tags. ``srt announce`` later
sends this announcement, with the shortlog and the delta appended.

.. code-block:: console

  $ srt quilt queue --no-edit
  [v6.12-rt-patches 3c5e0b1d2a4f] [ANNOUNCE] 6.12.118-rt24
   2 files changed, 2 insertions(+), 2 deletions(-)
  tagging HEAD of .../rt/v6.12-rt-patches as v6.12.118-rt24-patches
  OK to tag? (y/n): y
  next: srt quilt rebase

.. _cmd-quilt-rebase:

srt quilt rebase
~~~~~~~~~~~~~~~~

Builds the ``-rebase`` branch, after ``srt quilt queue``.

It resets ``v6.12-rt-rebase`` to the upstream release (``v6.12.118``),
imports the tagged queue with ``git quiltimport`` and tags the result
``v6.12.118-rt24-rebase``, signed. ``v6.12-rt-patches`` must be at the
queue tag and ``v6.12-rt-rebase`` clean. srt asks ``OK to reset?
(y/n):`` and ``OK to tag? (y/n):``.

.. code-block:: console

  $ srt quilt rebase
  reset .../rt/v6.12-rt-rebase to v6.12.118 and import the 42 patches of v6.12.118-rt24-patches
  OK to reset? (y/n): y
  tagging HEAD of .../rt/v6.12-rt-rebase as v6.12.118-rt24-rebase
  OK to tag? (y/n): y
  next: srt quilt merge

.. _cmd-quilt-merge:

srt quilt merge
~~~~~~~~~~~~~~~

Brings the series up to date, after ``srt quilt rebase``.

It merges the upstream release into ``v6.12-rt``, signed off, with the
signature of the upstream tag stripped from the message, and applies the
patches added to the queue with ``git am``. ``v6.12-rt`` must be clean.
On a conflict srt stops: resolve it (the result has to match
``-rebase``), ``git commit -s`` or ``git am --continue``, and rerun
``srt quilt merge``. It asks nothing and creates no tag.

.. code-block:: console

  $ srt quilt merge
  merge v6.12.118
  apply printk-Postpone-kthread-startup.patch
  next: srt quilt release

.. _cmd-quilt-release:

srt quilt release
~~~~~~~~~~~~~~~~~

Commits and tags the release, after ``srt quilt merge``.

It sets the localversion file of ``v6.12-rt`` (``localversion-rt``),
checks that the tree is the one of ``v6.12.118-rt24-rebase``, commits the
release with the subject ``v6.12.118-rt24`` and tags it, signed. If the
trees differ, e.g. because upstream took an RT patch in another form, srt
shows the difference and stops: commit a fixup in ``v6.12-rt`` and rerun.
srt asks ``OK to tag? (y/n):``.

Now ``v6.12-rt`` holds what gets released and nothing has left the
machine: test the release before ``srt create``. With ``TEST_COMMAND``
in ``srt.conf`` (:doc:`userguide`) srt prints how your lab tests it.

.. code-block:: console

  $ srt quilt release
  tagging HEAD of .../rt/v6.12-rt as v6.12.118-rt24
  OK to tag? (y/n): y
  test with:
      cd /home/wagi/rt/v6.12-rt
      srt-build round start --notes "v6.12.118-rt24"
  next: srt test, then srt create

.. _cmd-quilt-undo:

srt quilt undo
~~~~~~~~~~~~~~

Takes a release back as long as nothing is pushed, e.g. when a test
failed, at any step after ``srt quilt refresh``.

It deletes the local tags of the release (``NEW_TAG``, ``-rebase``,
``-patches``), resets ``v6.12-rt`` to its upstream branch, undoes the
queue commit and keeps the refreshed patches staged, and removes the
files of ``srt create`` and ``srt sign``. ``v6.12-rt-rebase`` needs no
cleanup, ``srt quilt rebase`` resets it. srt lists what it will do and
asks ``OK to undo? (y/n):``. It refuses when a tag or the queue commit is
pushed already. Then fix the queue and continue with ``srt quilt
refresh``.

.. code-block:: console

  $ srt quilt undo
  undo the v6.12.118-rt24 release:
    delete tag v6.12.118-rt24
    delete tag v6.12.118-rt24-rebase
    delete tag v6.12.118-rt24-patches
    reset .../rt/v6.12-rt to stable-rt/v6.12-rt, dropping:
      74e55e127cb5 v6.12.118-rt24
      2eb339592977 Merge tag 'v6.12.118' into v6.12-rt
    undo the queue commit in .../rt/v6.12-rt-patches, keeping the patches
  OK to undo? (y/n): y
  next: fix the patch queue, then srt quilt refresh

.. _cmd-commit:

srt commit
----------

Git workflow: commits the release, after the upstream release is merged
(or the ``-rebase`` branch rebased) and conflicts are fixed.

srt commit writes the next localversion to the localversion file
(``LOCALVERSION``, default ``localversion-rt``) and commits it, signed
off, as ``Linux <version>``, the version from the ``Makefile`` and the
localversion files:

- on the series or ``-next`` branch it increments the localversion,
  ``-rt126`` -> ``-rt127``.
- with ``-r N`` it commits release candidate N of the next release,
  ``-rt127-rcN``.
- on the ``-rebase`` branch it sets the number of the last release of
  the series, adds ``REBASE`` to the message and replaces a release
  commit at ``HEAD``.

The worktree must be clean. srt prints the commit and asks ``OK to
commit? (y/n):``; no resets the localversion file and exits with 1.

.. code-block:: console

  $ srt commit
  git commit -m Linux 4.19.291-rt127
  OK to commit? (y/n): y
  next: srt tag

.. _cmd-tag:

srt tag
-------

Git workflow: tags the release commit at ``HEAD``, after ``srt commit``.

The tag is named after the commit message: ``v4.19.291-rt127`` for
``Linux 4.19.291-rt127``, ``v4.19.291-rt127-rebase`` for the ``REBASE``
commit. ``-r N`` tags release candidate N, ``v4.19.291-rt127-rcN``. It
is signed with ``GPG_KEY_ID`` and stays local until ``srt push``. srt
asks ``OK to tag? (y/n):``. ``HEAD`` must be a release commit.

.. code-block:: console

  $ srt tag
  tagging as v4.19.291-rt127 with message 'Linux 4.19.291-rt127'
  OK to tag? (y/n): y
  next: in the -rebase worktree: git rebase the upstream release, srt commit and srt tag

After the ``-rebase`` tag the next step is ``srt create``, after a
release candidate testing, ``srt announce`` and ``srt push``.

.. _cmd-test:

srt test
--------

Tests the release in your test lab, with the commands ``TEST_COMMAND``
of ``srt.conf`` has (:doc:`userguide`): between ``srt quilt release``
and ``srt create``, in the git workflow for a release candidate after
``srt tag -r N``. It runs in any worktree of the series.

The release is a release candidate tagged at ``HEAD`` (git workflow),
else the release ``srt status`` shows. srt fills in the placeholders,
shows the command and asks ``OK to run? (y/n)``; ``--dry-run`` only
shows it. Then it runs the command with ``sh -c`` in the worktree of the
series, with ``SRT_TAG``, ``SRT_OLD_TAG``, ``SRT_UPSTREAM``,
``SRT_SERIES`` and ``SRT_WORKTREE`` in the environment, its output goes
to the terminal. ``SRT_RELEASE`` is a JSON file with the release, and
the command may write its result as JSON to ``SRT_TEST_RESULT``
(``status``, ``summary``, ``url``, see ``TEST_COMMAND`` in
:doc:`userguide`). srt test exits with the exit code of the command and
adds ``test`` with the exit code and the result to the history: ``srt
status`` shows ``srt test`` as done once it ran, whatever came out, with
the result's status, summary and url below it. Whether the release
passed is for you to judge. srt test is optional: ``srt create`` doesn't
need it, and without ``TEST_COMMAND`` srt test only says to set it.

It runs as long as the command does: a command which only submits the
jobs returns at once, one which waits for them takes as long as the
tests.

.. code-block:: console

  $ srt test
  testing v6.12.118-rt24 (after v6.12.117-rt23) in .../rt/v6.12-rt
  test with:
      cd /home/wagi/rt/v6.12-rt
      srt-build round start --notes "v6.12.118-rt24"
  OK to run? (y/n): y
  ...
  the test of v6.12.118-rt24 exited with 0
  result: pass - 54 jobs, no regressions
          https://lab.example/round/25

.. _cmd-create:

srt create
----------

Writes the files of the release, after the release is tagged and tested.
It works on the release of :ref:`release-lookup`.

srt create writes to ``patches/v6.12.118-rt24`` in the worktree:

``patch-6.12.118-rt24.patch.xz``
    ``git diff`` from the upstream release (``v6.12.118``) to the release.
``patches-6.12.118-rt24.tar.xz``
    the ``patches/`` directory of ``v6.12.118-rt24-patches`` as it is,
    series file and comments included (quilt workflow), or the commits of
    ``-rebase`` on the upstream release as ``git format-patch`` series
    (git workflow).

For a release candidate the patch is the diff from the upstream release
of ``OLD_TAG`` and the series the commits since ``OLD_TAG``. srt create
asks nothing and changes no tags or commits; rerun it to write the files
again. Review them, ``srt check`` compares them with the tags.

.. code-block:: console

  $ srt create
  Created the following files in .../rt/v6.12-rt/patches/v6.12.118-rt24
          .../rt/v6.12-rt/patches/v6.12.118-rt24/patch-6.12.118-rt24.patch.xz
          .../rt/v6.12-rt/patches/v6.12.118-rt24/patches-6.12.118-rt24.tar.xz
  Review them
  next: srt sign

.. _cmd-sign:

srt sign
--------

Signs the files of ``srt create`` for kernel.org.

srt sign signs the uncompressed content of the patch and the tarball
with ``GPG_KEY_ID`` (``GNUPGHOME``), as kup expects it: a detached,
armored signature next to each file, ``patch-6.12.118-rt24.patch.sign``
and ``patches-6.12.118-rt24.tar.sign``. gpg may ask for the passphrase.
srt asks nothing and changes no tags or commits.

.. code-block:: console

  $ srt sign
  signed .../rt/v6.12-rt/patches/v6.12.118-rt24/patch-6.12.118-rt24.patch.sign
  signed .../rt/v6.12-rt/patches/v6.12.118-rt24/patches-6.12.118-rt24.tar.sign
  next: srt upload

.. _cmd-check:

srt check
---------

Sanity checks between the trees of a release, any time during the
release, at the latest before ``srt upload``. It works on the release of
:ref:`release-lookup`, also an older one.

Each check runs once the step it checks is done, else it is skipped:

- quilt workflow: the upstream worktree is at the upstream release (until
  the refresh), the refreshed queue against the queue of ``OLD_TAG``
  (patches added, dropped, or changed beyond their hunk offsets, with the
  ``git diff`` to review them), ``-rebase`` is the upstream release with
  the patches of the queue in order, the message of the upstream merge,
  the release has the tree of ``-rebase``;
- git workflow: the release has the tree of ``-rebase``;
- both: the delta of the release without the upstream update, the patch
  and the tarball match the tags, the signatures are good (with the
  keyring of ``GNUPGHOME``).

Each check prints ``ok``, ``warn``, ``fail`` or ``skip``. srt check
changes nothing and exits with 1 if a check fails, a warning (e.g. a
changed patch) is for you to review. ``--json`` prints the checks as a
list of objects with ``name``, ``result``, ``text`` and ``details``.

.. code-block:: console

  $ srt check
  skip  upstream: the queue is refreshed already
  warn  queue: 1 added, 0 dropped, 0 changed beyond hunk offsets; review: git -C .../rt/v6.12-rt-patches diff v6.12.117-rt23-patches v6.12.118-rt24-patches -- patches/series
          added printk-Postpone-kthread-startup.patch
  ok    rebase: v6.12.118-rt24-rebase is v6.12.118 with the 42 patches of v6.12.118-rt24-patches
  ok    merge: v6.12.118 is merged
  ok    release: v6.12.118-rt24 has the tree of v6.12.118-rt24-rebase
  ok    delta: v6.12.117-rt23..v6.12.118-rt24 without the upstream update: 2 files changed, 40 insertions(+), 1 deletion(-)
           kernel/printk/printk.c | 39 +++++++++++++++++++++++++++++++++++++++
           localversion-rt        |  2 +-
  skip  files: srt create has not run yet
  skip  signatures: srt sign has not run yet

.. _cmd-upload:

srt upload
----------

Uploads the release files to kernel.org, after ``srt sign`` and ``srt
check``. It works on the release of :ref:`release-lookup`. This
publishes the files.

srt upload runs one kup command: it puts the patch, the tarball and their
signatures into ``PRJ_DIR/older``, links them into ``PRJ_DIR``, removes
the files of ``OLD_TAG`` from ``PRJ_DIR`` (they stay in ``older``) and
lists ``PRJ_DIR``. It prints the command and asks ``OK to upload?
(y/n):``, then prints the listing of ``PRJ_DIR`` kup ends with. If kup
fails, srt exits with its exit status (kup 0.4 or newer reports a failed
upload, see :doc:`userguide`).

``--dry-run`` (``-n``) prints the kup command and stops: it asks nothing
and uploads nothing.

.. code-block:: console

  $ srt upload --dry-run
  ['kup',
   'put',
   '.../rt/v6.12-rt/patches/v6.12.118-rt24/patch-6.12.118-rt24.patch.xz',
   '.../rt/v6.12-rt/patches/v6.12.118-rt24/patch-6.12.118-rt24.patch.sign',
   '/pub/linux/kernel/projects/rt/6.12/older/',
   '--',
   ...
   'rm',
   '/pub/linux/kernel/projects/rt/6.12/patch-6.12.117-rt23.patch.xz',
   '--',
   ...
   'ls',
   '/pub/linux/kernel/projects/rt/6.12']

Without ``--dry-run`` the same follows ``OK to upload? (y/n):`` and,
after the upload, the listing of ``PRJ_DIR`` and ``next: srt push``.

.. _cmd-push:

srt push
--------

Pushes the release to the tree of the series, after ``srt upload`` (or,
for a release candidate, after the review mails). It works on the
release of :ref:`release-lookup`. This publishes the release.

srt push pushes to ``PRJ_GIT_TREE``, through the remote that has it as
push URL (``srt setup`` sets the push URL of the series remote so). git
then updates the remote-tracking branches with the push, and ``srt
status`` sees it right away. Without such a remote srt pushes to the URL
and says to fetch it. It pushes:

- the release commit to the branch of the series and the tag
  ``NEW_TAG``,
- ``NEW_TAG-rebase`` to the ``-rebase`` branch (forced, it is rebased
  every release) and its tag,
- in the quilt workflow the ``-patches`` branch and the tag
  ``NEW_TAG-patches``,
- for a release candidate only the tag and the commit, forced, to the
  branch of the worktree (``-next``).

It first runs the push with ``git push -n`` and shows it, then asks ``OK
to push? (y/n):``. After the push it forgets the prepared release (the
history stays) and, for a release, offers the announcement: with
``MAILER`` set it asks ``Open the announcement in the mail client?
(y/n):`` (only at a terminal, not with ``--yes``) and opens it as ``srt
announce --mail`` does; else it tells how to send it.

``--dry-run`` (``-n``) shows the ``git push -n`` and stops.

.. code-block:: console

  $ srt push
  Dry run
  git push -n git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt v6.12.118-rt24^{}:v6.12-rt +v6.12.118-rt24-rebase^{}:v6.12-rt-rebase tag v6.12.118-rt24 tag v6.12.118-rt24-rebase v6.12-rt-patches tag v6.12.118-rt24-patches
  To gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
  ...
  OK to push? (y/n): y
  Open the announcement in the mail client? (y/n): y
  wrote /tmp/srt-announce-k2j3h4/announce-v6.12.118-rt24
  mutt -H /tmp/srt-announce-k2j3h4/announce-v6.12.118-rt24

.. _cmd-announce:

srt announce
------------

The announcement of a release, after ``srt push``; for a release
candidate the review mails, before ``srt push``. It works on the release
of :ref:`release-lookup`.

For a release srt announce prints the announcement as a mail, headers
included, to stdout, and sends nothing:

- the subject ``[ANNOUNCE] 6.12.118-rt24``, ``From:`` ``SENDER``,
  ``To:`` ``MAIL_TO``;
- the text: the announcement of the queue commit (quilt workflow,
  ``srt quilt queue``) or the ``ANNOUNCE`` template (git workflow);
- the shortlog since ``OLD_TAG``, the diffstat and the delta patch: the
  series' own change, with the upstream update left out.

Send it yourself, ``srt announce > ../announce-rt`` and ``mutt -H
../announce-rt``, or with ``--mail`` (``-m``): srt writes it to
``announce-<tag>`` in a new directory in ``$TMPDIR`` (default ``/tmp``)
and opens it in ``MAILER`` (see :doc:`userguide`). Whether the mail is
sent is up to you and the mail client.

For a release candidate srt announce writes the review mails to
``patches/<tag>/mails``: a cover letter from the ``RC_TEXT`` template and
one mail per commit added to the series since ``OLD_TAG``, including the
upstream merge with its conflict resolution if it had one. It shows
``git send-email --dry-run`` and asks ``OK to send patches? (y/n):``
before it sends them to ``MAIL_TO``. ``--suppress-cc`` (``-s``) doesn't
add the addresses of the patches as Cc, e.g. for a test.

.. code-block:: console

  $ srt announce > ../announce-rt
  next: send the announcement, e.g. srt announce > ../announce and mutt -H ../announce, or set MAILER in srt.conf for srt announce --mail
  $ head -2 ../announce-rt
  From: Maintainer Name <maintainer@example.org>
  Subject: [ANNOUNCE] 6.12.118-rt24

``srt status`` shows the announcement as done once the archive of the
mailing list (``INBOX``) has it.

.. _cmd-status:

srt status
----------

Where the release of the series stands and the next step, any time, in
any worktree of the series.

srt status shows the release prepared with ``srt prep``. Without it,
e.g. after ``srt push``, it finds the release in the trees: the release
after the last one on ``HEAD`` if one of its steps is done, else the last
release. The steps come from the trees, not from the history: the tags
and the patch queue, the files of ``srt create`` and ``srt sign``, ``kup
ls`` on kernel.org for ``srt upload``, the fetched branch of the series
for ``srt push`` (fetch first to see a push of another maintainer) and
the archive of the mailing list for ``srt announce``. Each step is done
(``[x]``), not done (``[ ]``) or unknown (``[?]``), e.g. ``srt upload``
without access to kernel.org. Warnings say when the prepared release
doesn't fit the fetched branches anymore.

srt status changes nothing in the trees. It runs ``kup ls`` once the
files are signed and clones or fetches the archive of the mailing list
into ``~/.cache/srt/inbox`` once the release is pushed, at most every 10
minutes; ``--offline`` does neither. When it finds the announcement it
adds ``announced`` to the history. ``--json`` prints the same for
scripts, see :doc:`agents`. :doc:`quilt-workflow` describes how each
step is found.

.. code-block:: console

  $ srt status
  v6.12.117-rt23 -> v6.12.118-rt24
    added:   printk-Postpone-kthread-startup.patch
    [x] srt quilt refresh
    [x] srt quilt queue
    [x] srt quilt rebase
    [x] srt quilt merge
    [x] srt quilt release
    [ ] srt test
    [ ] srt create
    [ ] srt sign
    [ ] srt upload
    [ ] srt push
    [ ] srt announce
  test with:
      cd /home/wagi/rt/v6.12-rt
      srt-build round start --notes "v6.12.118-rt24"
  next: srt test, then srt create

With ``TEST_COMMAND`` set, ``srt test`` is a step (quilt workflow),
done once it ran, with its exit code in ``--json``; it is optional, the
next step after it is ``srt create`` either way. ``test with:`` and, in
``--json``, ``test`` are there while testing is the next step.

Without a release in progress it prints ``No release in progress, the
last one:`` with the steps of the last release and ``next: srt prep``
once upstream has a newer release. Without any release on ``HEAD`` it
prints ``No release prepared.``

.. _cmd-log:

srt log
-------

The history of the series of the current worktree: what srt did, when
and by whom, oldest first, the time in UTC. ``-n N`` shows the last N
steps, ``--json`` all fields. It changes nothing.

Every step which changes something adds a line when it succeeds; dry
runs, drafts, ``srt status`` (except ``announced``), ``srt check`` and a
plain ``srt announce`` don't. :doc:`userguide` describes the fields and
where the history is kept.

.. code-block:: console

  $ srt log -n 2
  2026-11-21 10:12  quilt release  v6.12.118-rt24 (from v6.12.117-rt23)  by Daniel Wagner
      tag     v6.12.118-rt24
      commit  3f1c0a9e2b7d

  2026-11-21 11:40  create         v6.12.118-rt24 (from v6.12.117-rt23)  by Daniel Wagner
      dir     .../rt/v6.12-rt/patches/v6.12.118-rt24
      files   patch-6.12.118-rt24.patch.xz patches-6.12.118-rt24.tar.xz

.. _cmd-mcp:

srt mcp
-------

Serves the release steps to an agent as an MCP server on stdin and
stdout. Run it in the work area, the parent of the worktrees, or give
``--dir``; the agent's client starts it:

.. code-block:: console

  $ claude mcp add srt -- srt mcp --dir ~/rt

Each tool names its series and runs srt in its worktree, without a
terminal. ``upload`` and ``push`` are dry runs unless the server runs
with ``--allow-publish`` and the call asks for it; ``announce`` returns
the mail and sends nothing. :doc:`agents` describes the tools and the
signing key the server uses.
