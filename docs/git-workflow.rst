Git workflow
============

The git workflow maintains the RT patches as merges on top of the stable
tree. It uses v4.19-rt as example; this was the last tree maintained with
this workflow.

Branches
--------

The workflow uses three branches, ``v<version>-rt``, ``v<version>-rt-rebase``
and ``v<version>-rt-next``, e.g.:

``v4.19-rt``
    The released stable-rt tree, stable releases are merged into it.
``v4.19-rt-rebase``
    The RT patches rebased on top of the latest stable release.
``v4.19-rt-next``
    Release candidates. The kernelci bot monitors the -next branches and
    triggers builds.

Setup
-----

Add the stable and stable-rt remotes to the main repository (see
:doc:`userguide` for ``origin``)::

  $ cd linux
  $ git remote add stable https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
  $ git remote add stable-rt https://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-stable-rt.git
  $ git remote set-url --push stable-rt git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt.git
  $ git fetch --all --tags

Create a worktree for each branch, tracking the stable-rt branch of the same
name::

  $ git worktree add --track -b v4.19-rt        ../v4.19-rt        stable-rt/v4.19-rt
  $ git worktree add --track -b v4.19-rt-rebase ../v4.19-rt-rebase stable-rt/v4.19-rt-rebase
  $ git worktree add --track -b v4.19-rt-next   ../v4.19-rt-next   stable-rt/v4.19-rt-next

Configuration
-------------

Add a group for each branch to ``srt.conf``:

.. code-block:: ini

   [linux/stable-rt/v4.19-rt]
   LOCALVERSION = localversion-rt
   GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
   PRJ_GIT_TREE = git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
   PRJ_DIR = /pub/linux/kernel/projects/rt/4.19

   [linux/stable-rt/v4.19-rt-rebase]
   LOCALVERSION = localversion-rt
   GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
   PRJ_GIT_TREE = git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
   PRJ_DIR = /pub/linux/kernel/projects/rt/4.19

   [linux/stable-rt/v4.19-rt-next]
   LOCALVERSION = localversion-rt
   GPG_KEY_ID = 0C0C8220A7FB009385B9D8C492ADC0F369646112
   PRJ_GIT_TREE = git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
   PRJ_DIR = /pub/linux/kernel/projects/rt/4.19

Release candidate
-----------------

A release candidate is always created and pushed to the -next branch first.
Publish this branch and do your local testing. Announce the candidate on the
mailing list and do the proper release after a week or so.

.. code-block:: console

  $ cd v4.19-rt-next
  $ git fetch --all
  $ git reset --hard v4.19-rt

  $ git tag -l --sort=v:refname v4\.19\.\* | tail -10
  v4.19.285
  v4.19.286
  v4.19.287
  v4.19.288
  v4.19.288-rt126
  v4.19.288-rt126-rc1
  v4.19.288-rt126-rebase
  v4.19.289
  v4.19.290
  v4.19.291

  $ git merge v4.19.291        [fixup conflicts]

  $ srt commit
  git commit -m Linux 4.19.291-rt127
  OK to commit? (y/n): y

  $ srt tag -r 1
  tagging as v4.19.291-rt127-rc1 with message 'Linux 4.19.291-rt127-rc1'
  OK to tag? (y/n): y

  [do local testing]

  $ srt announce
  [...]
  Result: OK
  OK to send patches? (y/n): y

  $ srt push
  Dry run
  git push -f -n git@gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt   v4.19.291-rt127-rc1^{}:v4.19-rt-next tag v4.19.291-rt127-rc1
  To gitolite.kernel.org:pub/scm/linux/kernel/git/rt/linux-stable-rt
     83db5d9eb0ed..0b2e2eb20a90  v4.19.291-rt127-rc1^{} -> v4.19-rt-next
   * [new tag]                   v4.19.291-rt127-rc1 -> v4.19.291-rt127-rc1
  OK to push? (y/n): y
  [...]

Release
-------

.. code-block:: console

  $ cd v4.19-rt
  $ git merge --ff-only v4.19-rt-next
  $ srt tag

  $ cd ../v4.19-rt-rebase
  $ git rebase v4.19.291       [fixup conflicts]
  $ srt commit
  $ srt tag

  $ cd ../v4.19-rt
  $ srt create
  $ srt sign
  $ srt announce > ../announce-rt
  $ srt upload
  $ srt push

  $ cat ../announce-rt | msmtp -t --
  or
  $ mutt -H ../announce-rt
