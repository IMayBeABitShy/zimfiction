"""
This module contains functionality to create the search metadata.
"""
import math

from .buckets import BucketMaker


class SearchMetadataCreator(object):
    """
    This class is responsible for creating the search metadata.
    """

    _SEARCH_FIELDS = (
        "publisher",
        "language",
        "status",
        "categories", "implied_categories",
        "warnings", "implied_warnings",
        "tags", "implied_tags",
        "relationships", "implied_relationships",
        "characters", "implied_characters",
        "rating",
    )

    def __init__(self, max_page_size=50000):
        """
        The default constructor.

        @param max_page_size: max number of elements per metadata file
        @type max_page_size: L{int}
        """
        self._max_page_size = max_page_size
        self._num_stories = 0
        self._cur_tag_id = 0
        self._tag_ids = {f: {} for f in self._SEARCH_FIELDS if not f.startswith("implied_")}  # field -> {tag -> id}
        self._amounts = {}  # for RAM optimization purposes, only store amounts > 1
        self._search_items = []

    def feed(self, story):
        """
        Feed a story into the search metadata creator.

        @param story: story to process
        @type story: L{zimfiction.db.models.Story}
        """
        # the following code is the result of merging three other
        # methods. It is quite suboptimal, aesthetically speaking. I am sorry.
        self._num_stories += 1
        searchmeta = story.get_search_data()
        itemdata = {
            "publisher": searchmeta["publisher"],
            "id": searchmeta["id"],
            "updated": searchmeta["updated"],
            "words":  searchmeta["words"],
            "chapters": searchmeta["chapters"],
            "score": searchmeta["score"],
            "tags": [],
            "implied_tags": [],
            # "rating": searchmeta["rating"],
            "category_count": searchmeta["category_count"],
        }
        # find new tag ids
        for fieldname in self._SEARCH_FIELDS:
            outkey = fieldname.replace("implied_", "")
            tags = searchmeta[fieldname]
            if not isinstance(tags, (list, tuple)):
                # for ease of processing, convert single tags
                # into a list
                tags = [tags]
            for tag in tags:
                if tag not in self._tag_ids[outkey]:
                    tag_id = self._cur_tag_id
                    self._cur_tag_id += 1
                    self._tag_ids[outkey][tag] = tag_id
                    # do not yet register tag in amounts
                    # we try to save some RAM by assuming that every
                    # tag in self._tag_ids and not in self._amounts
                    # occurs exactly once
                else:
                    tag_id = self._tag_ids[outkey][tag]
                    if tag_id not in self._amounts:
                        self._amounts[tag_id] = 2
                    else:
                        self._amounts[tag_id] += 1
            # store search tags of story
            outkey = "tags"
            resolve_field = fieldname
            if fieldname.startswith("implied_"):
                outkey = "implied_tags"
                resolve_field = resolve_field.replace("implied_", "")
            if isinstance(searchmeta[fieldname], (list, tuple)):
                for tag in searchmeta[fieldname]:
                    resolved_tag = self._tag_ids[resolve_field][tag]
                    itemdata[outkey].append(resolved_tag)
            else:
                # non-list tag
                resolved_tag = self._tag_ids[resolve_field][searchmeta[fieldname]]
                itemdata[outkey].append(resolved_tag)
        itemdata["tags"].sort()
        itemdata["implied_tags"].sort()
        self._search_items.append(itemdata)

    def get_search_header(self):
        """
        Return the search header metadata.

        @return: the search header metadata
        @rtype: L{dict}
        """
        header = {}
        header["num_pages"] = math.ceil(self._num_stories / self._max_page_size)
        header["tag_ids"] = self._tag_ids
        header["amounts"] = {tag_id: self._amounts.get(tag_id, 1) for tag_id_group in self._tag_ids.values() for tag_name, tag_id in tag_id_group.items()}
        return header

    def iter_search_pages(self):
        """
        Iterate over the search pages.

        @yields: (pagenum, content)
        @ytype: L{tuple} of (L{int}, L{dict})
        """
        bucketmaker = BucketMaker(maxsize=self._max_page_size)
        cur_file_i = 0
        for item in self._search_items:
            bucket = bucketmaker.feed(item)
            if bucket is not None:
                yield (cur_file_i, bucket)
                cur_file_i += 1
        bucket = bucketmaker.finish()
        if bucket is not None:
            yield (cur_file_i, bucket)

