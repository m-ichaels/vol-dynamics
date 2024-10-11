"""The surface engine is Project H's (`optmm`: Black prices and Greeks, the implied-vol solver, SSVI slices, the eSSVI
surface, implied forwards from parity).  This module finds it: an installed `optmm`, then the sibling checkout
../ProjectH, then the copy vendored under voldyn/_optmm for continuous integration (Project H's repository is private;
the vendored files are byte-for-byte those of ProjectH at the commit named in _optmm/VERSION and are never edited here)."""
from __future__ import annotations

import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIBLING = os.path.join(os.path.dirname(ROOT), "ProjectH")


def _load():
    try:
        return importlib.import_module("optmm"), "installed"
    except ImportError:
        pass
    if os.path.isdir(os.path.join(SIBLING, "optmm")):
        sys.path.insert(0, SIBLING)
        try:
            return importlib.import_module("optmm"), "sibling"
        except ImportError:
            sys.path.pop(0)
    sys.path.insert(0, os.path.join(ROOT, "voldyn", "_optmm"))
    return importlib.import_module("optmm"), "vendored"


optmm, SOURCE = _load()
bs = importlib.import_module("optmm.bs")
ssvi = importlib.import_module("optmm.surface")

black = bs.black
greeks = bs.greeks
implied_vol = bs.implied_vol
fit_slice = ssvi.fit_slice
fit_surface = ssvi.fit_surface
forward_from_parity = ssvi.forward_from_parity
