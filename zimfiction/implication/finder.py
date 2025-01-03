"""
This module contains the L{ImplicationFinder} class, which is used as a
base class for classes that find implications for a story.
"""


class ImplicationFinder(object):
    """
    Base class for implication finders.

    Implementations of this class are responsible for scanning a story
    for implied tags, categories, ...
    """
    def get_implied_tags(self, story, implied_tags):
        """
        Find implied tags for a story.

        Tags returned by this method are allowed to overlap with the
        explicit tags, the L{zimfiction.implication.implicator.Implicator} will
        take care of this.

        @param story: story to scan for tag implications
        @type story: L{bool}
        @param implied_tags: list of newly implied tags from other finders
        @type implied_tags: L{list} of L{tuple} of (L{str}, L{str}, L{zimfiction.implication.ImplicationLevel})
        @return: a list of implied tags as tuples of (type, name, implication_level)
        @rtype: L{list} of L{tuple} of (L{str}, L{str}, L{zimfiction.implication.ImplicationLevel})
        """
        return []

    def get_implied_categories(self, story, implied_categories):
        """
        Find implied categories for a story.

        Categories returned by this method are allowed to overlap with the
        explicit categories, the L{zimfiction.implication.implicator.Implicator}
        will take care of this.

        @param story: story to scan for category implications
        @type story: L{bool}
        @param implied_categories: list of newly implied categories from other finders
        @type implied_categories: L{list} of L{tuple} of (L{str}, L{str}, L{zimfiction.implication.ImplicationLevel})
        @return: a list of implied categories as tuples of (publisher, name, implication_level)
        @rtype: L{list} of L{tuple} of (L{str}, L{str}, L{zimfiction.implication.ImplicationLevel})
        """
        return []
