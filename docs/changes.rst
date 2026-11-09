Changes
=======

2.0
---

The quilt workflow release is now a sequence of named ``srt quilt``
steps, modelled on the linux-6.18.y-rt releases. See :doc:`quilt-workflow`.
srt sets up work areas, takes over series from other maintainers, needs a
much shorter configuration, and is no longer tied to PREEMPT_RT.

New
~~~

- ``srt quilt refresh``, ``queue``, ``rebase``, ``merge`` and ``release``
  replace ``srt patches`` and the manual steps (``git add -u``,
  ``git reset --hard`` + ``git quiltimport``, ``git merge``, editing
  ``localversion-rt``, comparing the trees by hand). The steps can be run
  from any of the worktrees and every step can be rerun.
- Adding and dropping patches is supported: ``srt quilt refresh`` detects
  patches which stable already contains and offers to drop them,
  ``srt quilt merge`` applies added patches on -rt with ``git am``, and
  ``srt quilt release`` refuses to release if the -rt tree differs from
  -rebase.
- ``srt quilt undo`` undoes a release which is not pushed yet, e.g. when a
  test fails, keeping the refreshed patches.
- ``srt status`` shows the prepared release and the next step.
- ``srt setup`` creates or checks the work area of a series: repository,
  remotes and worktrees, and adds the series to ``srt.conf`` from its
  options. With ``--from`` it starts a series from other branches, e.g. to
  continue a series of another maintainer under a new name, and tells how
  to publish it.
- The release suffix is configurable (``SUFFIX``, default ``rt``), srt
  works for any out-of-tree patch series.
- One configuration group per series, shared settings in ``[DEFAULT]``.
  ``WORKFLOW = quilt`` replaces ``quilt_workflow = true``.
  ``LOCALVERSION``, ``GPG_KEY_ID``, ``SENDER`` and ``NAME`` have defaults
  from the suffix and git's configuration.
- srt converts ``srt.conf`` files of srt 1.x on the first run and keeps the
  old file as ``srt.conf.bak``.
- srt is fully type annotated, checked with ``mypy --strict``, and ships
  ``py.typed``.
- ``srt prep`` updates the stable worktree (``--no-pull`` to skip it) and
  records the worktrees of the quilt workflow.

Fixed
~~~~~

- The package didn't contain the templates, ``srt announce`` failed after
  ``pip install .``.
- ``srt quilt`` refreshed the patches in the format of the user's
  ``~/.quiltrc``, rewriting every patch header.
- ``srt commit`` and ``srt tag`` lost the environment
  (``HOME``, ``PATH``, gpg agent) when setting ``GNUPGHOME``; git failed
  without a configured identity.
- The announcement in the patch queue named the previous release as
  "Head SHA1". It names the release tag now.
- A second ``srt quilt`` run incremented the localversion again.
- ``SrtContext`` used the directory of the time srt was imported.
- ``srt announce`` mailed the Signed-off-by of the patch queue commit.
- ``srt prep`` took any tag without -rt as a stable release, e.g.
  ``v6.12-rc7``.
- ``srt commit`` exited with 0 when the tree was dirty.
- Tags ending in ``-rebase`` could not be parsed.
- ``srt create`` and ``srt sign`` ignored failures of ``git diff``, ``xz``
  and ``gpg``; a failed signature went unnoticed. A failing command of the
  pipeline is reported now.
- ``srt create``, ``sign``, ``upload``, ``push`` and ``announce`` carried on
  when a tag they need was missing.
- A closed stdin ended srt with a traceback at a confirmation prompt; it
  counts as "no" now.
- The announcements could show the fingerprint of another key than
  ``GPG_KEY_ID`` when the keyring has several keys.
- ``srt upload`` exited with 0 when kup failed.
- The rc review mails passed the ``--to`` addresses to git send-email with
  quotes as part of the address.

Incompatible changes
~~~~~~~~~~~~~~~~~~~~

- ``srt.conf`` is converted to the 2.0 format on the first run, see
  :doc:`userguide`. The original is kept as ``srt.conf.bak``.
- Python 3.12 or newer is required. The package is described in
  ``pyproject.toml``, ``setup.py`` is gone.
- The configuration lookup order is fixed: ``$SRT_CONF``, the current
  directory, ``~/.config``, ``~`` and ``/etc/srt``, the first one wins.
  Before, ``/etc/srt/srt.conf`` overrode the user configuration.
- ``srt patches`` is removed, use the ``srt quilt`` steps.
- The commit template (``COMMIT_TMPL``) gets ``{release_tag}`` and
  ``{series_changes}``. ``srt quilt queue`` commits the queue before the
  release commit exists, so ``{branch_head}`` is not available there.
- Release candidates are not supported by the quilt workflow.
- The templates use https instead of git:// URLs for git.kernel.org.
- srt calls ``gpg`` instead of ``gpg2``.
- The rc review mails are made without ``git filter-branch``, which git
  discourages, and without checking out a temporary branch.
