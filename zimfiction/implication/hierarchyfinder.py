"""
An L{zimfiction.implication.finder.ImplicationFinder} for implying hierarchical orderings.
"""
from .finder import ImplicationFinder
from .implicationlevel import ImplicationLevel


AF_PUBLISHER = ".adult-fanfiction.org"


class HierarchyFinder(ImplicationFinder):
    """
    An ImplicationFinder finding category hierarchies.
    """
    def get_implied_categories(self, story, implied_categories):
        all_categories = [(ca.category.publisher.name, ca.category.name, ca.implication_level) for ca in story.category_associations] + implied_categories
        categories = []
        if story.publisher.name.endswith(AF_PUBLISHER):
            for publisher_name, category_name, implication_level in all_categories:
                category_name = category_name.strip()
                if implication_level <= ImplicationLevel.MIN_IMPLIED:
                    new_implication_level = ImplicationLevel.STRONGLY_DEDUCED
                else:
                    new_implication_level = ImplicationLevel.DEDUCED
                subsplit = category_name.split(" > ")
                for i in range(len(subsplit)):
                    c = " > ".join(subsplit[:i+1])
                    if c and (c not in categories):
                        categories.append((publisher_name, c, new_implication_level))
        return categories

