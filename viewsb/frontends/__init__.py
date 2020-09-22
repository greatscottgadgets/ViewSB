from os.path import dirname, basename, isfile, join
import glob

# Autodetect all files in this directory, so they can be automatically
# imported by 'from <module> import *'.
modules = glob.glob(dirname(__file__)+"/*.py")
dir_modules = glob.glob(join(dirname(__file__), '*', '__init__.py'))
__all__ = [
    basename(f)[:-3] for f in modules if isfile(f)
] + [
    basename(dirname(f)) for f in dir_modules if isfile(f)
]
