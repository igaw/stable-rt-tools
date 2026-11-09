#!/usr/bin/env python3
"""Print the docs/changes.rst section of a version as GitHub markdown.

Usage: release-notes.py VERSION [CHANGES_RST]
"""

import re
import sys

DOCS = 'https://stable-rt-tools.readthedocs.io/en/latest'


def section(lines: list[str], version: str) -> list[str]:
    """Return the lines of the section titled version, without its title."""
    def is_title(i: int, char: str) -> bool:
        return (i + 1 < len(lines) and lines[i].strip() != ''
                and re.fullmatch(re.escape(char) + '{3,}', lines[i + 1])
                is not None)

    start = None
    for i in range(len(lines)):
        if not is_title(i, '-'):
            continue
        if start is not None:
            return lines[start:i]
        if lines[i].strip() == version:
            start = i + 2
    if start is None:
        sys.exit(f'release-notes: no section {version} in the changelog')
    return lines[start:]


def to_markdown(lines: list[str]) -> str:
    out: list[str] = []
    skip = False
    for i, line in enumerate(lines):
        if skip:
            skip = False
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ''
        if line.strip() and re.fullmatch(r'~{3,}', nxt):
            # a ~~~ underline would start a code block in markdown
            out.append(f'### {line.strip()}')
            skip = True
            continue
        line = re.sub(r':doc:`([^`<]+)`',
                      lambda m: f'[{m[1]}]({DOCS}/{m[1]}.html)', line)
        line = re.sub(r'`([^`<]+?) <([^>]+)>`_', r'[\1](\2)', line)
        out.append(line)
    return '\n'.join(out).strip() + '\n'


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    version = sys.argv[1].removeprefix('v')
    path = sys.argv[2] if len(sys.argv) == 3 else 'docs/changes.rst'
    with open(path) as f:
        lines = f.read().splitlines()
    print(to_markdown(section(lines, version)), end='')


if __name__ == '__main__':
    main()
