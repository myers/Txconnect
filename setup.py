#!/usr/bin/env python

import sys
from setuptools import setup, find_packages

try:
    import twisted
except ImportError:
    raise SystemExit('twisted not found.  Make sure you '
                     'have installed the Twisted core package.')

def refresh_plugin_cache():
    from twisted.plugin import IPlugin, getPlugins
    list(getPlugins(IPlugin))

if __name__ == '__main__':
    
    setup(
        name='Txconnect',
        version='1.0',
        description='Twisted Python DirectConnect Client',
        author='Myers Carpenter',
        author_email='myers@maski.org',
        url='http://github.com/myers/Txconnect/',
        packages=find_packages() + ['twisted.plugins'],
        include_package_data=True,
        package_data={
            'twisted': ['plugins/txconnect_plugin.py'],
        },
        classifiers=[
            'Development Status :: 5 - Production/Stable',
            'Framework :: Twisted',
            'Intended Audience :: End Users/Desktop',
            'License :: OSI Approved :: GNU General Public License (GPL)',
            'Natural Language :: English',
            'Operating System :: MacOS :: MacOS X',
            'Operating System :: POSIX',
            'Environment :: No Input/Output (Daemon)',
            'Environment :: Web Environment',
            'Programming Language :: Python',
            'Programming Language :: JavaScript',
            'Topic :: Communications :: File Sharing',
            'Topic :: Software Development :: Libraries :: Python Modules',
        ],
        install_requires=[
            'twisted>=10.1',
            'louie',
            'django',
            'lxml',
            'mocker',
        ]
    )
    
    refresh_plugin_cache()
