Developer Guide
===============

Deploy for development
----------------------

The package is described in ``pyproject.toml`` and needs Python 3.12 or
newer. Create a virtual environment and install srt in editable mode with
the development tools::

    $ python3 -m venv .venv
    $ . .venv/bin/activate
    $ pip install -e '.[dev]'

``srt`` in the virtual environment then runs the code of the checkout.

Run the linter, the type checker and the tests::

    $ ruff check .
    $ mypy
    $ pytest

The package is fully annotated and checked with ``mypy --strict``, the
tests are checked without requiring annotations. Configuration for all
three tools is in ``pyproject.toml``.

The tests need ``git``, ``gpg``, ``quilt`` and ``patch``; without quilt
the quilt workflow tests are skipped. ``test_srt.py`` runs a complete git
workflow release and ``test_srt_quilt_workflow.py`` a complete quilt
workflow release, both step by step with temporary repositories and a
temporary GPG key. These end to end tests take most of the time of the
test suite, they are marked ``e2e``; for a quick run leave them out::

    $ pytest -m 'not e2e'

The tests don't depend on the machine they run on: they don't read your
git configuration (``~/.gitconfig``, the system one), your GPG keyring,
your ``srt.conf`` or ``OLD_TAG``/``NEW_TAG`` from the environment. Each
test has an empty ``HOME`` and commits as the owner of the test key
(``tests/conftest.py``); a test which needs a setting sets it itself.
The GPG key is generated once per test run, each test signs with a copy
of the keyring (``tests/helpers.py``).

The tests never reach the network. To check the ``srt announce`` step
against the real announcements as well, point ``SRT_TEST_INBOX`` at a
clone of the stable-rt public inbox (``git clone --mirror
https://lore.kernel.org/stable-rt/0``), the one setting of the
environment the tests use.

Build the documentation and the package::

    $ sphinx-build -b html docs docs/_build/html
    $ python -m build

The version is set in ``stable_rt_tools/about.py``. Pushing a ``v*`` tag
publishes the package on PyPI.


Known limitations
-----------------

Open questions, kept here so a problem that shows up has its background.

The release suffix without a prepared release
    Without the state of ``srt prep`` (e.g. after ``srt push``, which
    clears it) ``SrtContext`` finds the tags in the history of HEAD
    (``get_last_release()``, ``get_previous_release()``) and accepts any
    release suffix: ``SrtContext`` has no configuration, so it doesn't
    know ``SUFFIX``. It takes the suffix from the tag it finds.
    ``srt prep`` and ``srt commit`` use ``SUFFIX``.

    This can go wrong on a branch whose first-parent history holds
    releases of another series with another suffix, e.g. a series made
    on top of another one (``v4.4.144-cip13-rt134``: the nearest tag
    could be a ``-cip`` release). srt would then announce or upload the
    wrong release. Not seen so far.

    If it happens: give the tags (``srt announce OLD_TAG NEW_TAG``) or
    set ``OLD_TAG``/``NEW_TAG``. The fix would be to pass the suffix of
    the configuration to ``SrtContext`` (most commands call
    ``get_config()`` right after it) and use it in
    ``get_last_release()``.

Release candidates in the status without a prepared release
    Without the state of ``srt prep`` ``srt status`` works out the
    release from the trees (``tree_status_info()`` in
    ``srt_status.py``): the release after the last one on the branch if
    one of its steps is done, else the last release. It doesn't look for
    release candidates (``-rcN`` on the ``-next`` branch of the git
    workflow), so an rc in progress isn't shown: ``srt status`` then
    describes the last release. Only the git workflow has release
    candidates, and it is not in use at the moment (the quilt workflow has
    none).

    ``OLD_TAG``/``NEW_TAG`` don't help: ``srt status`` doesn't read them,
    and the state of ``srt prep`` names the release, not an rc. If it is
    needed, the fix would be to look for an rc tag of the next
    release on the ``-next`` branch (``get_last_release(rc=True)``) in
    ``tree_status_info()``, with the steps of the git workflow for an rc
    (commit -r, tag -r, announce = the review mails, push to -next).

Community Resources
-------------------

Project home:

 - https://github.com/igaw/stable-rt-tools

Source code:

 - https://github.com/igaw/stable-rt-tools.git
 - git@github.com:igaw/stable-rt-tools.git

Documentation:

 - https://stable-rt-tools.readthedocs.org

Mailing list:

  - stable-rt@vger.kernel.org

  - Subscription:

    - send an email with "subscribe stable-rt" in the body to majordomo@vger.kernel.org
    - http://vger.kernel.org/vger-lists.html

  - Archives

    - (none)

Class reference documentation
-----------------------------

``stable_rt_tools.srt_announce`` Module
.......................................

.. automodule:: stable_rt_tools.srt_announce
   :members:


``stable_rt_tools.srt_review`` Module
.....................................

.. automodule:: stable_rt_tools.srt_review
   :members:
