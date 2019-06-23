from os.path import dirname, basename, isfile
import glob

# Autodetect all backends in this directory, so they can be automatically
# imported by 'from backends import *'.
modules = glob.glob(dirname(__file__)+"/*.py")
__all__ = [ basename(f)[:-3] for f in modules if isfile(f)]
