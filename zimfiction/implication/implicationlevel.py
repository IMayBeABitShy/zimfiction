"""
Definition of implication levels.
"""
from enum import IntEnum


# TODO: it is probably a fundamentally bad idea to implement
# this as an enum

class ImplicationLevel(IntEnum):
    """
    The implication level indicates how sure we are of that a story has a tag/category.

    We seperate implication levels by L{ImplicationLevel.MIN_IMPLIED}.
    Any association with a level below this value is considered explicit
    and any value above makes use consider the association as implied.

    Only explicit tags/... are shown in the UI, implied tags/... are mostly used to ensure that the search is more flexible.

    @var MIN_IMPLIED: implication levels above this value are considered implied.

    @var SOURCE: implication level of a tag/... directly from the source of the story
    @var MAX_SHOW: only show tags with implication levels below this in summaries.
    @var MAX_LIST_INCLUDE: only include stories in lists of tags with a lower implication level

    @var UNKNOWN: implication level is unknown.
    @var DEDUCED: implication level indication that the tag was proceduraly deduced from existing tags
    @var MERGER: implication level indicating that this is the result of a tag merger
    @var MENTIONED: implication level indicating that this tag was mentioned in the story description
    @var QUALIFIED: implication level indicating this tag was implied from a reliable source
    @var STRONGLY_DEDUCED: implication level indicating that this tag was proceduarly deduced in such a way that it is pretty much guaranteed to be correct
    """
    MIN_IMPLIED = 100
    MAX_SHOW = 20
    MAX_LIST_INCLUDE = 60

    SOURCE = 0
    QUALIFIED = 30
    MENTIONED = 70
    UNKNOWN = -1
    STRONGLY_DEDUCED = 50;
    DEDUCED = 110
    MERGER = 150
