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
workflow release, both with temporary repositories and a temporary GPG
key.

Build the documentation and the package::

    $ sphinx-build -b html docs docs/_build/html
    $ python -m build

The version is set in ``stable_rt_tools/about.py``. Pushing a ``v*`` tag
publishes the package on PyPI.


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

