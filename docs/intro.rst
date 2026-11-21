Introduction
============

srt maintains out-of-tree patch series on top of upstream releases, e.g.
on top of the stable kernel releases. It started as the release tool of the
stable PREEMPT_RT trees (hence the name) and is used for other patch series
as well.

What srt does
-------------

A patch series lives outside of the upstream tree and follows its
releases: each time upstream releases, e.g. stable v6.12.118, the series
is brought up to date and released again, e.g. as v6.12.118-rt24. srt
makes such a release step by step, in the git trees of the series: it
refreshes or rebases the patches, commits and tags the release, writes
and signs the release files, uploads them to kernel.org with kup, pushes
the branches and tags and prepares the announcement for the mailing
list.

PREEMPT_RT is the main user and the examples use it, but nothing is
specific to it: the release suffix (``SUFFIX``, default ``rt``) names
the tags and branches, and the announcement and commit messages come from
templates you can replace (see :doc:`userguide`).

The two workflows
-----------------

srt supports two ways to keep the series, chosen per series with
``WORKFLOW`` in ``srt.conf``:

:doc:`quilt-workflow`
    The patches are a quilt queue in their own branch (``-patches``).
    For a release the queue is refreshed on the new upstream release and
    imported on top of it (``-rebase``), and the upstream release is
    merged into the released tree, which must end up identical to
    ``-rebase``. srt does each step with ``srt quilt``. Used for v6.12-rt.
:doc:`git-workflow`
    The patches are commits in the released tree, upstream releases are
    merged into it; a ``-rebase`` branch has the patches rebased on the
    upstream release, release candidates go to a ``-next`` branch. You
    merge and rebase with git, srt commits and tags the release. Last used
    for v4.19-rt.

The release at a glance
-----------------------

.. code-block:: none

   srt prep               find the release, OLD_TAG and NEW_TAG
   srt quilt refresh      quilt: refresh the queue on the upstream release
   srt quilt queue               commit and tag the queue (-patches)
   srt quilt rebase              import the queue on upstream (-rebase)
   srt quilt merge               merge upstream into the series
   srt quilt release             commit and tag the release
   git merge, git rebase  git: merge upstream, rebase -rebase
   srt commit, srt tag           commit and tag the release and -rebase
   srt check              sanity checks between the trees
   (test the release)
   srt create             write the patch and the tarball
   srt sign               sign them
   srt upload             upload them to kernel.org
   srt push               push the branches and tags
   srt announce --mail    send the announcement (srt push offers it)

``srt status`` shows at any time which steps are done and the next one,
every command ends with the next step (``next: ...``). :doc:`commands`
has a table of the steps of both workflows.

What stays local, what is published
-----------------------------------

Everything up to ``srt sign`` stays on your machine: tags, commits and
release files are local and can be redone; ``srt quilt undo`` takes a
release of the quilt workflow back. Three steps publish the release and
cannot be taken back with srt:

- ``srt upload`` puts the files on kernel.org,
- ``srt push`` pushes the branches and tags to the tree of the series,
- sending the announcement (or the review mails of a release candidate
  with ``srt announce``).

Each of them shows what it will do and asks first; ``srt upload`` and
``srt push`` have a ``--dry-run``. Test the release before them.

Where srt keeps its state
-------------------------

Most of what srt knows comes from the git trees: the tags, branches and
patch queue tell which steps are done, ``srt status`` reads them each
time. Besides that:

- the state of ``srt prep``, ``<git common dir>/srt/<series>.json``,
  names the release in progress for the following commands. It is a
  cache: ``srt push`` and ``srt prep --clear`` remove it, without it srt
  finds the release in the trees.
- the history of the series, ``<git common dir>/srt/<series>.log``, is
  what srt did, when and by whom (``srt log``). For people to read, srt
  doesn't depend on it, but it cannot be recreated: keep it with the
  repository.
- the clone of the archive of the mailing list in ``~/.cache/srt/inbox``
  tells ``srt status`` whether a release is announced. A cache, remove it
  any time.
- ``srt.conf`` holds the configuration of the series, see
  :doc:`userguide`.

Where to go next
----------------

- :doc:`userguide`: installation, prerequisites, configuration and the
  work area.
- :doc:`quilt-workflow` and :doc:`git-workflow`: a release from start to
  end.
- :doc:`commands`: each command in detail, :doc:`command-line` the
  options and environment variables.
- :doc:`agents`: srt without a terminal and for an agent (``srt mcp``).
