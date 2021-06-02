#!/usr/bin/env python3

"""
This file is part of ViewSB
Copyright (C) 2019 Katherine J. Temkin, Mikaela Szekely

ViewSB is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later
version.
"""

from setuptools import setup, find_packages

setup(
    name='viewsb',
    version='0.0.1',
    url='https://github.com/usb-tools/viewsb',
    license='BSD',
    entry_points={
        'console_scripts': [
            'viewsb = viewsb.commands.viewsb:main',
        ],
    },

    # Current maintainer; but not sole author. :)
    # Major credit to Mikaela Szekely (@Qyriad). See the commit logs for full info.
    author='Katherine J. Temkin',
    author_email='k@ktemkin.com',
    tests_require=[''],
    install_requires= [
        'construct',
        'bitstruct',
        'tableprint',
        'urwid',
        'usb_protocol',
    ],
    extras_require={
        'qt': ['pyside6', 'qt-material'],
        'luna': ['luna'],
        'openvizla': ['pyopenvizsla'],
        'phywhisperer': ['phywhisperer'],
        'rhododendron': ['greatfet'],
        'usbproxy': ['facedancer'],
    },
    dependency_links=[
        'git+https://git@github.com/usb-tools/pyopenvizsla.git@master#egg=pyopenvizsla',
        'git+https://git@github.com/usb-tools/python-usb-protocol.git@master#egg=usb_protocol',
    ],
    description='python-based USB Analyzer toolkit (and USB analyzer)',
    long_description='python-based USB Analyzer toolkit (and USB analyzer)', # FIXME
    packages=find_packages(),
    include_package_data=True,
    platforms='any',
    classifiers = [
        'Programming Language :: Python',
        'Development Status :: 1 - Planning',
        'Natural Language :: English',
        'Environment :: Console',
        'Environment :: Plugins',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Topic :: Scientific/Engineering',
        'Topic :: Security',
        ],
)
