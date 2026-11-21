Changes
=======

2.2
---

New
~~~

- ``srt announce --mail`` writes the announcement to a temporary file
  and opens it in your mail client, the new
  ``MAILER`` setting (e.g. ``mutt -H {mail}`` or Thunderbird's
  ``-compose``). With ``MAILER`` set, ``srt push`` offers to do it right
  after the push.
- ``-y``/``--yes`` answers all questions with yes, before or after the
  command (``srt -y push``, ``srt quilt undo --yes``), for scripts.
- ``srt quilt queue`` works without an editor: ``--draft`` prints the
  generated announcement, ``-F FILE`` commits the announcement from a
  file, ``--no-edit`` commits the generated announcement as it is.
- ``srt upload --dry-run`` shows the kup command, ``srt push --dry-run``
  runs ``git push -n``; neither asks or changes anything.
- All commands tell the next step (``next: srt sign``), like the
  ``srt quilt`` steps, in the git workflow too. ``srt quilt release``
  reminds to test the release before ``srt create``. ``srt sign`` lists
  the signatures, ``srt prep --clear`` says whether it cleared a release.
- ``srt status`` shows ``srt create`` and ``srt sign`` as steps, and
  warns when the prepared release was published already (e.g. by another
  maintainer), when the series has a newer release than the prepared one
  starts from, or when upstream has a newer release than the prepared one.
  It trusted the tags only, so a release published elsewhere looked half
  done. ``srt status --json`` prints the status for scripts.
- ``srt check`` runs the reviews of the documentation as sanity checks
  between the trees: the refreshed queue against the last one (patches
  added, dropped or changed beyond hunk offsets, with the ``git diff`` to
  review them), ``-rebase`` against the queue, the stable merge message,
  the release against ``-rebase``, the delta of the release, the files of
  ``srt create`` against the tags and the signatures.
- ``srt mcp`` serves the release steps to an agent as MCP server, with
  upload and push as dry runs unless it runs with ``--allow-publish``. The
  repository has a Claude Code skill for making a release. The Agents
  page of the documentation describes both.
- The Agents page and the skill describe which key an agent signs with
  (the configuration ``srt mcp`` runs with), to compare it with the key of
  the last release before the first signed tag, and how to split a release
  between an agent in a sandbox without the release key and the host,
  where the maintainer creates the tags and signatures.

Fixed
~~~~~

- ``srt check`` needed the state of ``srt prep``: after ``srt push``
  (which clears it) it stopped with "No release prepared". It finds the
  release like the other commands now, from ``OLD_TAG NEW_TAG``, the
  environment, the state or the history, and checks the stable merge of
  the release tag instead of HEAD.
- A setting missing in ``srt.conf`` (e.g. ``PRJ_DIR`` for ``srt upload``
  or ``MAIL_TO`` for ``srt announce``) ended the command with a Python
  traceback (``KeyError``). It names the setting and the group of
  ``srt.conf`` to add it to now, and for ``GPG_KEY_ID``, ``SENDER`` and
  ``NAME`` the git setting they default to.
- ``srt announce`` after ``srt push`` mailed an empty shortlog, diffstat
  and delta: without the state of the release (``srt push`` clears it)
  the old release was the last published one, the new one itself. It is
  the release before the new one now.
- ``srt prep`` and the commands run without a prepared release asked the
  remote for the last release (``git ls-remote``), which failed offline,
  and took the last tag of the branch, which could be a merged stable
  tag. They look at the local history of the branch now (``HEAD``),
  without the merged stable tags, ``-rebase`` and ``-patches``:
  ``srt prep`` takes the last release as the old one, the other commands
  take it (or a release candidate) as the new one and the release before
  it as the old one.
- The name of the upstream branch was its second ``/`` part: the branch
  ``stable/v6.12-rt`` on ``origin`` was ``stable``, every branch of a
  remote named ``kernel/org`` was ``org``. It is the branch name on the
  remote now, in ``srt prep``, ``srt commit``, ``srt push``,
  ``srt announce`` and the check of the prepared release.
- ``srt quilt merge`` kept the signature of the stable tag as comment
  lines (``# -----BEGIN PGP SIGNATURE-----`` ... ``# gpg: ...``) in the
  message of the stable merge, e.g. in v6.12.116-rt22 and v6.12.117-rt23.
  The message is cleaned up and signed off now, like the merges of
  linux-6.18.y-rt.
- ``srt create`` put the patches of the release in the tarball as
  renumbered ``git format-patch`` mails in the quilt workflow too
  (``0001-...`` to ``0041-...``), without the sections and comments of the
  series. It contains the quilt queue of the ``-patches`` tag now, like
  the tarballs of linux-6.18.y-rt.
- The release state of ``srt prep`` was one for the whole work area, while
  ``srt setup`` puts several series into one. ``srt prep`` in v6.18-rt
  replaced a release prepared in v6.12-rt, ``srt status`` in v6.18-rt
  showed the v6.12-rt release, and the other commands asked to clear it.
  Each series has its own release state now; the state of srt 2.1 moves to
  its series when the series reads it.
- ``srt quilt undo`` left the files of ``srt create`` and ``srt sign``
  of the undone release behind; it removes them now. Files of a
  release which isn't tagged (e.g. left over by the ``srt quilt undo`` of
  srt 2.1) make ``srt status`` warn and ``srt check`` fail, and don't
  count as ``srt create`` and ``srt sign`` done.
- A failing git (or other) command ended srt with a Python traceback,
  and the error message of the command was lost. srt prints the command,
  its exit code and its error message now (``srt -d`` keeps the
  traceback), and Ctrl-C ends srt without a traceback.
- ``srt quilt release`` refused a changed, not yet added localversion
  file as uncommitted change ``ocalversion-rt``: the first letter of the
  first changed file was cut off.
- Errors all go to stderr now: ``srt upload`` printed a missing file of
  ``srt create`` on stdout, ``srt sign`` and a missing configuration
  group came as ``ERROR:root:`` log lines.
- ``srt tag -r N`` after ``srt commit -r N`` tagged ``-rcN-rcN``: the
  release candidate was in the commit already. It tags ``-rcN`` once
  now and refuses another N than the one of the commit. ``srt tag`` on
  a commit which is no release commit (``Linux 6.12.118-rt24``) says so
  instead of doing nothing, and a stable release commit
  (``Linux 6.12.118``) is no release commit for ``srt tag`` and
  ``srt commit`` anymore.

2.1
---

Everything added to a series since the last release is reviewed and
announced: the review mails of a release candidate and the release
announcement contain the patches before and after the stable merge and
the conflict resolutions of the merge, but not the stable update. The
release announcement is the same for the git and the quilt workflow.

New
~~~

- The releases of stable-rt-tools are published on GitHub too, with the
  changelog as release notes.

Fixed
~~~~~

- The review mails of a release candidate left out the conflict
  resolutions of the stable merge, ``git format-patch`` skips merges. The
  merge is a mail of the series now, with the resolution as shown by
  ``git show --remerge-diff``. A clean merge gets no mail.
- The review mails of a release candidate started at the last merge,
  patches committed before the stable merge were not mailed. The mails
  contain everything added to the series since the last release now. The
  cover letter lists all mails; its diffstat is left out when the series
  contains a stable merge, it would show the stable update.
- ``srt announce`` of a release in the quilt workflow printed only the
  announcement of the queue commit: no ``Message-ID``, no shortlog, no
  delta, and an error message instead of failing when the tag was missing.
  Both workflows print the same now: the announcement (the ``ANNOUNCE``
  template, the queue commit in the quilt workflow), the shortlog since the
  last release, the diffstat and the delta patch. The delta is the series'
  own change against the old release with the new stable release merged
  in: patches before and after the stable merge, conflict resolutions and
  the release commit, not the stable update. The default ``COMMIT_TMPL``
  says that the delta patch is appended.

Incompatible changes
~~~~~~~~~~~~~~~~~~~~

- git 2.38 or newer is required (``git show --remerge-diff``,
  ``git merge-tree --write-tree``).

2.0
---

The quilt workflow release is now a sequence of named ``srt quilt``
steps, modelled on the linux-6.18.y-rt releases. See :doc:`quilt-workflow`.
srt sets up work areas, continues series of other maintainers, needs a
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
