"""
Definition of implication levels.
"""
from enum import IntEnum


class ImplicationLevel(IntEnum):
    """
    The implication level indicates how sure we are of that a story has a tag/category.

    We seperate implication levels by L{ImplicationLevel.MIN_IMPLIED}.
    Any association with a level below this value is considered explicit
    and any value above makes use consider the association as implied.

    Only explicit tags/... are shown in the UI, implied tags/... are mostly used to ensure that the search is more flexible.

    @var MIN_IMPLIED: implication levels above this value are considered implied.
    @var SOURCE: implication level of a tag/... directly from the source of the story
    @var UNKNOWN: implication level is unknown.
    @var DEDUCED: implication level indication that the tag was proceduraly deduced from existing tags
    @var MERGER: implication level indicating that this is the result of a tag merger
    @var MENTIONED: implication level indicating that this tag was mentioned in the story description
    """
    MIN_IMPLIED = 100
    SOURCE = 0
    MENTIONED = 50
    UNKNOWN = -1
    DEDUCED = 110
    MERGER = 150
