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
    # Major credit to Mikaela Szekely (@qyriad). See the commit logs for full info.
    author='Katherine J. Temkin',
    author_email='k@ktemkin.com',
    tests_require=[''],

    # FIXME: don't require all of the backends; move some to 'extras_require'
    install_requires= [
        'construct',
        'bitstruct',
        'tableprint',
        'facedancer',
        'greatfet',
        'pyopenvizsla',
        'urwid'
    ],
    dependency_links=['git+https://git@github.com/usb-tools/pyopenvizsla.git@master#egg=pyopenvizsla'],
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
    extras_require={}
)
