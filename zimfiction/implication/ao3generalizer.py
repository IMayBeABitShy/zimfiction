"""
An L{zimfiction.implication.finder.ImplicationFinder} for finding
generalized categories on ao3.

Each of the following categories:

    - A
    - A (Movie)
    - A - B.C.
    - A & Related Fandoms

will imply "A & Related Fandoms - All Media Types".
"""
from ..normalize import get_ao3_category_generalized_name
from .finder import ImplicationFinder
from .implicationlevel import ImplicationLevel
from .ao3dumpfinder import AO3_PUBLISHER


class Ao3GeneralizationFinder(ImplicationFinder):
    """
    An ImplicationFinder finding generalized categories.
    """
    def get_implied_categories(self, story, implied_categories):
        if story.publisher.name != AO3_PUBLISHER:
            # story is not from ao3, do not process
            return []
        # create list of all categories
        categories = []
        for ca in story.category_associations:
            categories.append((ca.category.publisher.name, ca.category.name, ca.implication_level))
        categories += implied_categories
        # find lowest implication levels
        min_implication_levels = {}
        for publisher_name, category_name, implication_level in categories:
            category_key = (publisher_name, category_name)
            if category_key in min_implication_levels:
                if min_implication_levels[category_key] < implication_level:
                    min_implication_levels[category_key] = implication_level
            else:
                min_implication_levels[category_key] = implication_level
        # now, determine generalized categories
        found = []
        for publisher_name, category_name, _ in categories:
            category_key = (publisher_name, category_name)
            min_implication_level = min_implication_levels[category_key]
            # find the appropiate implication level
            if min_implication_level < ImplicationLevel.MIN_IMPLIED:
                # deduced from a non-implied source
                implication_level = ImplicationLevel.STRONGLY_DEDUCED
            else:
                # deduced from an implied source
                implication_level = ImplicationLevel.DEDUCED
            generalized_name = get_ao3_category_generalized_name(category_name)
            found.append((publisher_name, generalized_name, implication_level))
        return found
