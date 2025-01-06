"""
An L{zimfiction.implication.finder.ImplicationFinder} for finding crossovers.
"""
from ..normalize import get_ao3_category_base_name
from .finder import ImplicationFinder
from .implicationlevel import ImplicationLevel
from .ao3dumpfinder import AO3_PUBLISHER
from .hierarchyfinder import AF_PUBLISHER


AO3_IGNORED_CATEGORIES = ["original work", "no fandom"]
CROSSOVER_TAG = ("genre", "special:crossover", ImplicationLevel.DEDUCED)

FICTIONPRESS_PUBLISHER = "www.fictionpress.com"


class CrossoverFinder(ImplicationFinder):
    """
    An ImplicationFinder finding crossovers.
    """
    def get_implied_tags(self, story, implied_tags):
        # check if story already has a crossover tag
        all_tags = [t.name for t in story.explicit_tags] + [t[1] for t in implied_tags]
        for tag_name in all_tags:
            if tag_name.lower() in ("crossover", "crossovers", "x-over", "x-overs"):
                # already marked as a crossover, add the tag to be sure it's tagged uniformly
                return [CROSSOVER_TAG]
        # find all category names
        category_names = [c.name for c in story.explicit_categories] #  + [c[1] for c in implied_categories]
        # check if it is a crossover depending on the publisher
        if story.publisher.name == AO3_PUBLISHER:
            # on ao3, we identiy crossovers by checking if there are at
            # least two categories with different base name, excluding
            # categories like "No Fandom" and "Original Work"
            basenames = []
            for category_name in category_names:
                if category_name.lower().strip() in AO3_IGNORED_CATEGORIES:
                    continue
                basename = get_ao3_category_base_name(category_name)
                if basename not in basenames:
                    basenames.append(basename)
            is_crossover = (len(basenames) > 1)
        elif story.publisher.name == FICTIONPRESS_PUBLISHER:
            # assume no crossovers on fictionpress
            is_crossover = False
        elif story.publisher.name.endswith(AF_PUBLISHER):
            # also assume there are no crossovers on this site
            is_crossover = False
        else:
            # on all other sites, assume crossover if we have at least two categories
            is_crossover = len(category_names) >= 2
        # add tag if required
        if is_crossover:
            return [CROSSOVER_TAG]
        else:
            return []
