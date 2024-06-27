"""
This module contains an L{zimfiction.implication.finder.ImplicationFinder}
for processing AO3 published tag dumps and utilizing merger IDs to add
tags as implied tags.

One such dump can be found here: https://archiveofourown.org/admin_posts/18804

@var AO3_CATEGORY_TAG_TYPES: a list of tag types that should be considered a category
@type AO3_CATEGORY_TAG_TYPES: L{list} of L{str}
@var AO3_TYPE_TO_ZIMFICTION_TYPE: a dict mapping ao3 tag types to the types used by zimfiction
@type AO3_TYPE_TO_ZIMFICTION_TYPE: L{dict} of L{str} -> (L{str} or L{None})
@var AO3_PUBLISHER: name of the publisher, stories from other publishers will be ignored
@type AO3_PUBLISHER: L{str}
"""
import csv

from ..util import add_to_dict_list
from .finder import ImplicationFinder


AO3_CATEGORY_TAG_TYPES = ["Category", "Media", "Fandom"]
AO3_TYPE_TO_ZIMFICTION_TYPE = {
    "UnsortedTag": "genre",
    "Relationship": "relationship",
    "Rating": None,  # we don't need this one
    "ArchiveWarning": "warning",
    "Character": "character",
    "Freeform": "genre",
}
AO3_PUBLISHER = "archiveofourown.org"


class Ao3MergerFinder(ImplicationFinder):
    """
    An ImplicationFinder finding implied tags using AO3's merger IDs from
    their oficial dumps.

    @ivar path: path to the "tags" CSV file
    @type path: L{str}
    @ivar category2canon: a dict of category name -> canon category name unless category has no variations
    @type category2canon: L{dict} of L{str} -> L{str}
    @ivar category_implications: a dict of canon category name -> other category names of same category
    @type category_implications: L{dict} of L{str} -> L{list} of L{str}
    @ivar tag2canon: a dict of (tagtype, tagname) -> canon (tagtype, tagname) unless tag has not variations
    @type tag2canon: L{dict} of (L{str}, L{str}) -> L{list} of (L{str}, L{str})
    @ivar tag_implications: a dict of canon (tagtype, tagname) -> list of other (tagtype, tagnames) of same tag
    @type tag_implications: L{dict} of (L{str}, L{str}) -> L{list} of (L{str}, L{str})
    @ivar imply_all: if nonzero, each tag implies each variation
    @type imply_all: L{bool}
    """
    def __init__(self, path, imply_all=False):
        """
        The default constructor.

        @param path: path to the "tags" CSV file
        @type path: L{str}
        @ivar imply_all: if nonzero, each tag implies each variation
        @type imply_all: L{bool}
        """
        self.path = path
        self.imply_all = imply_all
        self._load_mergers()

    def _load_mergers(self):
        """
        Load the merger tags from the CSV.
        """
        # first, load the data from the CSV
        canonical2variations = {}  # canon tag id -> list of tag ids (incl. canon one)
        id2taginfo = {}  # tag id -> (ao3 tag type, tag name)
        with open(self.path, "r", encoding="utf-8") as fin:
            reader = csv.reader(fin)
            for row in reader:
                if row[0] == "id":
                    # first line contains column names
                    continue
                tag_id, tag_type, tag_name, is_canonical, cached_count, merger_id = row
                if not tag_name:
                    # we can ignore this line, as it does not contain any useful information
                    continue
                if is_canonical == "true":
                    merger_id = tag_id
                if not merger_id:
                    # no implications here
                    continue
                merger_id = int(merger_id)
                tag_id = int(tag_id)
                add_to_dict_list(canonical2variations, merger_id, tag_id)
                id2taginfo[tag_id] = (tag_type, tag_name)

        # now, resolve all tag implications by building dicts mapping
        # (tagtype, tagname) -> (canon tagtype, canon tagname)
        # and a dict mapping (canon tagtype, canon tagname) -> list of
        # (tagtype, tagname) for all merged tags
        # also do this with the categories, seperating them from the tags
        # additionally, translate AO3 tag types to zimfiction tag types
        # NOTE: the dict will not contain any key for a tag that has no
        # implications bar itself
        tag2canon = {}  # (tagname, taginfo) -> (canon tagname, canon taginfo)
        category2canon = {}  # same as above, but using categoryname
        tag_implications = {}
        category_implications = {}
        for canon_tag_id, tag_group in canonical2variations.items():
            # each taggroup contains all tag ids that imply each other
            if len(tag_group) <= 1:
                # group contains no implications
                # only the tag itself
                continue
            try:
                canon_tag_info = id2taginfo[canon_tag_id]
            except KeyError:
                # for some reason, canon tag ids are sometimes not listed
                # solution: add placeholder value
                # as the canon tag info is used only as a grouping key
                # and never actually implied, we can simply utilize it
                # as a placeholder
                canon_tag_info = ("Freeform", "special:canon_tag_" + str(canon_tag_id))
            canon_tag_type, canon_tag_name = canon_tag_info
            for tag_id in tag_group:
                tag_type, tag_name = id2taginfo[tag_id]
                is_category = (tag_type in AO3_CATEGORY_TAG_TYPES)
                if is_category:
                    category2canon[tag_name] = canon_tag_name
                    cur_tag_is_canon = (tag_name == canon_tag_name)
                    if cur_tag_is_canon or self.imply_all:
                        add_to_dict_list(category_implications, canon_tag_name, tag_name)
                else:
                    converted_canon_tag_type = AO3_TYPE_TO_ZIMFICTION_TYPE[canon_tag_type]
                    converted_tag_type = AO3_TYPE_TO_ZIMFICTION_TYPE[tag_type]
                    tag2canon[(converted_tag_type, tag_name)] = (converted_canon_tag_type, canon_tag_name)
                    cur_tag_is_canon = ((tag_type, tag_name) == canon_tag_info)
                    if cur_tag_is_canon or self.imply_all:
                        add_to_dict_list(tag_implications, (converted_canon_tag_type, canon_tag_name), (converted_tag_type, tag_name))
        # finalize
        self.tag2canon = tag2canon
        self.tag_implications = tag_implications
        self.category2canon = category2canon
        self.category_implications = category_implications

    def get_implied_tags(self, story, implied_tags):
        if story.publisher_name != AO3_PUBLISHER:
            # ignore non-ao3 stories
            return []
        new_tags = []
        # process explicit tags
        for tag in story.tags:
            tag_info = (tag.type, tag.name)
            try:
                canon_tag_info = self.tag2canon[tag_info]
            except KeyError:
                # no tag implications
                continue
            other_tags = self.tag_implications[canon_tag_info]
            for other_tag in other_tags:
                new_tags.append(other_tag)
        # process implicit tags
        for tag_info in implied_tags:
            try:
                canon_tag_info = self.tag2canon[tag_info]
            except KeyError:
                # no tag implications
                continue
            other_tags = self.tag_implications[canon_tag_info]
            for other_tag in other_tags:
                new_tags.append(other_tag)
        return new_tags

    def get_implied_categories(self, story, implied_categories):
        if story.publisher_name != AO3_PUBLISHER:
            # ignore non-ao3 stories
            return []
        new_categories = []
        # process explicit categories
        for category in story.categories:
            try:
                canon_category_name = self.category2canon[category.name]
            except KeyError:
                # no category implications
                continue
            other_categories = self.category_implications[canon_category_name]
            for other_category in other_categories:
                new_categories.append((AO3_PUBLISHER, other_category))
        # process implied categories
        for category_name in implied_categories:
            try:
                canon_category_name = self.category2canon[category_name]
            except KeyError:
                # no category implications
                continue
            for other_category in other_categories:
                new_categories.append((AO3_PUBLISHER, other_category))
        return new_categories
