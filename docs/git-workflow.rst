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

Configuration
-------------

One group describes the series, see :doc:`userguide` for all settings:

.. code-block:: ini

   [linux/stable-rt/v4.19-rt]
   UPSTREAM_BRANCH = linux-4.19.y
   PRJ_DIR = /pub/linux/kernel/projects/rt/4.19

with the URLs in ``[DEFAULT]`` as in the example there. ``WORKFLOW``
defaults to ``git``.

Setup
-----

.. code-block:: console

  $ srt setup linux/stable-rt/v4.19-rt

creates the repository, the remotes and a worktree for the series and its
``-rebase`` and ``-next`` branches.

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

The review mails contain the patches since the last release and, if the
stable merge had conflicts, the merge with its conflict resolution
(``git show --remerge-diff``): the conflicts git left on the ``-`` lines,
the merge as committed on the ``+`` lines.

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
