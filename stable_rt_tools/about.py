# stable-rt-tools - support out of tree patch workflows
#
# Copyright (c) Daniel Wagner <dwagner@suse.de>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
    Setup script for stable-rt-tools, a tool to support out of
    tree patch workflows
"""

__all__ = [
    '__version__',
    '__title__',
    '__summary__',
    '__uri__',
    '__doc_uri__',
    '__author__',
    '__email__',
    '__license__',
    '__copyright__',
]

__version__ = '1.4'

__title__ = 'stable-rt-tools'
__summary__ = 'Support out of tree patch workflows'
__uri__ = 'https://github.com/igaw/stable-rt-tools/' \
    'releases/archive/{version}.tar.gz'.format(version=__version__)
__doc_uri__ = 'https://stable-rt-tools.readthedocs.io'

__author__ = "Daniel Wagner"
__email__ = 'dwagner@suse.de'

__license__ = 'MIT'
__copyright__ = 'Copyright (c) {} <{}>'.format(__author__, __email__)
