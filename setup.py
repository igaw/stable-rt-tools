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

from os import path
from setuptools import setup, find_packages


__license__ = 'MIT'
__copyright__ = 'Copyright (c) Daniel Wagner <dwagner@suse.de>'
__version__ = 0.1

HERE = path.abspath(path.dirname(__file__))
with open(path.join(HERE, 'README')) as f:
    LONG_DESCRIPTION = f.read()


setup(
    name='stable-rt-tools',
    version=__version__,

    description='Support out of tree patch workflows',
    long_description=LONG_DESCRIPTION,

    maintainer='Daniel Wagner',
    maintainer_email='dwagner@suse.de',

    url='git@github.com:igaw/stable-rt-tools.git',
    download_url=('https://github.com/igaw/stable-rt-tools/releases'
                  '/archive/{version}.tar.gz'.format(version=__version__)),

    license='MIT',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
   ],
    keywords='Linux development',

    packages=find_packages(),

    entry_points={
        'console_scripts': [
            'srt=stable_rt_tools.srt:main',
        ],
    },

    install_requires=[
    ],

    extras_require={':python_version<"3.9"': ['importlib-resources']},

    # At least python 3.4 is needed for asyncio:
    python_requires='>=3.4',

    test_suite='nose2.collector.collector',
    tests_require=['nose2'],
)
