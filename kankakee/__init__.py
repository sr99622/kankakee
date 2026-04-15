from importlib.metadata import version, PackageNotFoundError
import sys

from .kankakee import *
from .kankakee import __doc__

try:
    __version__ = version("kankakee")
except PackageNotFoundError:
    __version__ = "unknown"

