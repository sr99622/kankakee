from importlib.metadata import version, PackageNotFoundError
import sys

if sys.platform == "win32":
    from kankakee import *
    from kankakee import __doc__
else:
    from .kankakee import *
    from .kankakee import __doc__

try:
    __version__ = version("kankakee")
except PackageNotFoundError:
    __version__ = "unknown"

