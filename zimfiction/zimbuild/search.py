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
        self._raw_search_metadata = []
        self._tag_ids = None

    def feed(self, story):
        """
        Feed a story into the search metadata creator.

        @param story: story to process
        @type story: L{zimfiction.db.models.Story}
        """
        searchmeta = story.get_search_data()
        self._raw_search_metadata.append(searchmeta)
        self._tag_ids = None

    def _resolve(self):
        """
        Resolve the search metadata.

        This is the process of mapping the tags to ids.
        """
        cur_i = 0
        tag_ids = {f: {} for f in self._SEARCH_FIELDS if not f.startswith("implied_")}  # field -> {tag -> id}
        for item in self._raw_search_metadata:
            for fieldname in self._SEARCH_FIELDS:
                outkey = fieldname.replace("implied_", "")
                tags = item[fieldname]
                if not isinstance(tags, (list, tuple)):
                    # for ease of processing, convert single tags
                    # into a list
                    tags = [tags]
                for tag in tags:
                    if tag not in tag_ids[outkey]:
                        tag_ids[outkey][tag] = cur_i
                        cur_i += 1
        self._tag_ids = tag_ids

    def get_search_header(self):
        """
        Return the search header metadata.

        @return: the search header metadata
        @rtype: L{dict}
        """
        if self._tag_ids is None:
            # need to resolve tag ids first
            self._resolve()
        header = {}
        header["num_pages"] = math.ceil(len(self._raw_search_metadata) / self._max_page_size)
        header["tag_ids"] = self._tag_ids
        return header

    def iter_search_pages(self):
        """
        Iterate over the search pages.

        @yields: (pagenum, content)
        @ytype: L{tuple} of (L{int}, L{dict})
        """
        if self._tag_ids is None:
            # need to resolve tag ids first
            self._resolve()
        bucketmaker = BucketMaker(maxsize=self._max_page_size)
        cur_file_i = 0
        for item in self._raw_search_metadata:
            itemdata = {
                "publisher": item["publisher"],
                "id": item["id"],
                "updated": item["updated"],
                "words":  item["words"],
                "chapters": item["chapters"],
                "score": item["score"],
                "tags": [],
                "implied_tags": [],
                # "rating": item["rating"],
                "category_count": item["category_count"],
            }
            for field in self._SEARCH_FIELDS:
                outkey = "tags"
                resolve_field = field
                if field.startswith("implied_"):
                    outkey = "implied_tags"
                    resolve_field = resolve_field.replace("implied_", "")
                if isinstance(item[field], (list, tuple)):
                    for tag in item[field]:
                        resolved_tag = self._tag_ids[resolve_field][tag]
                        itemdata[outkey].append(resolved_tag)
                else:
                    # non-list tag
                    resolved_tag = self._tag_ids[resolve_field][item[field]]
                    itemdata[outkey].append(resolved_tag)
            itemdata["tags"].sort()
            itemdata["implied_tags"].sort()
            bucket = bucketmaker.feed(itemdata)
            if bucket is not None:
                yield (cur_file_i, bucket)
                cur_file_i += 1
        bucket = bucketmaker.finish()
        if bucket is not None:
            yield (cur_file_i, bucket)

