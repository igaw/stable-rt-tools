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
__version__ = 1.3

HERE = path.abspath(path.dirname(__file__))
with open(path.join(HERE, 'README.rst')) as f:
    LONG_DESCRIPTION = f.read()


setup(
    name='stable-rt-tools',
    version=__version__,

    description='Support out of tree patch workflows',
    long_description=LONG_DESCRIPTION,

    maintainer='Daniel Wagner',
    maintainer_email='dwagner@suse.de',

    url='https://stable-rt-tools.readthedocs.io',
    download_url=('https://github.com/igaw/stable-rt-tools/releases'
                  '/archive/{version}.tar.gz'.format(version=__version__)),

    license='MIT',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 5 - Production/Stable',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    keywords='Linux development',

    packages=find_packages(),

    entry_points={
        'console_scripts': [
            'srt=stable_rt_tools.srt:main',
        ],
    },

    package_data={'': ['stable_rt_tools/*.txt']},
    include_package_data=True,

    install_requires=[
    ],

    extras_require={':python_version<"3.9"': ['importlib-resources']},

    test_suite='nose2.collector.collector',
    tests_require=['nose2'],
)
