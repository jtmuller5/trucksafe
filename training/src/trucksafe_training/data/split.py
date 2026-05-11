"""Build a held-out eval split, stratified by truck and driver.

TODO: stratification keeps the eval set from leaking driver- or
truck-specific cues into the training set. Implementation pending the
metadata format.
"""

from __future__ import annotations


def build_splits() -> None:
    raise NotImplementedError
