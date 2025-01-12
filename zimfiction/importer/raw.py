"""
This module contains classes for raw (non-db) stories.
"""
import datetime

from ..util import count_words, add_to_dict_list, remove_duplicates
from ..normalize import normalize_category, normalize_relationship
from ..db.models import Chapter, Story, Author, Category, Tag, Series, Publisher, Source
from ..db.models import StoryTagAssociation, StorySeriesAssociation, StoryCategoryAssociation
from ..implication.implicationlevel import ImplicationLevel
from ..exceptions import ParseError


def id_from_url(url):
    """
    Parse the URL of a story and return the story ID.

    @param url: url of the story
    @type url: L{str}
    @return: the story id
    @rtype: L{int}
    """
    if "fanfiction.net" in url:
        part = url[url.find("/s/") + 3:]
        if "/" in part:
            part = part[:part.find("/")]
        return int(part)
    elif "fictionpress.com" in url:
        part = url[url.find("/s/") + 3:]
        if "/" in part:
            part = part[:part.find("/")]
        return int(part)
    elif "archiveofourown.org" in url:
        part = url[url.find("/works/") + 7:]
        if "/" in part:
            part = part[:part.find("/")]
        return int(part)
    elif "adult-fanfiction.org" in url:
        start = url.find("?no=") + 4
        return int(url[start:])
    else:
        raise ParseError("Unknown story URL format: '{}'".format(url))


def split_categories(s):
    """
    Split all categories from a string.

    @param s: string of categories to split
    @type s: L{str}
    @return:: the list of categories
    @rtype: L{list} of L{str}
    """
    categories = []
    splitted = s.split(",")
    for e in splitted:
        e = e.strip()
        if e and (e not in categories):
            categories.append(e)
    return categories


def split_tags(s):
    """
    Split all tags from a string.

    @param s: comma separated list of tags to split
    @type s: L{str}
    @return:: the list of tags
    @rtype: L{list} of L{str}
    """
    tags = []
    splitted = s.split(",")
    for e in splitted:
        e = e.strip()
        if e and (e not in tags):
            tags.append(e)
    return tags


def is_done_from_status(status):
    """
    Check if a story is done depending on the status.

    @param status: status of the story
    @type status: l{str}
    @return: True if the story is finished, otherwise False
    @rtype: L{bool}
    """
    lstatus = status.lower().strip()
    if lstatus in (
        "in-progress",
    ):
        return False
    elif lstatus in (
        "complete",
        "completed",
    ):
        return True
    raise ParseError("Unknown story status: '{}'".format(status))


class RawChapter(object):
    """
    This class represents a raw, non-db chapter.

    This class is used to unify the import logic. Parsers should create
    instances of this class, which will then be converted to actual chapters
    later on.
    """
    def __init__(self, index, title, text, num_words=None):
        """
        The default constructor.

        @param index: index of this chapter
        @type index: L{int}
        @param title: title of this chapter
        @type title: L{str}
        @param text: text of this chapter
        @type text: L{str}
        @param num_words: number of words in this chapter. If not specified, calculate this.
        @type num_words: L{int} or L{None}
        """
        assert isinstance(index, int)
        assert isinstance(title, str)
        assert isinstance(text, str)
        assert isinstance(text, str) or (text is None)

        self.index = index
        self.title = title
        self.text = text
        if num_words is not None:
            self.num_words = num_words
        else:
            self.num_words = count_words(self.text)

    def to_dict(self):
        """
        Create a dictionary describing this chapter.

        @return: a dict containing all data of this chapter
        @rtype: L{dict}
        """
        data = {
            "index": self.index,
            "title": self.title,
            "num_words": self.num_words,
            "text": self.text,
        }
        return data

    @classmethod
    def from_dict(cls, d):
        """
        Instantiate a new chapter from the data contained in the provided dictionary.

        @param d: a dict describing this chapter, such as returned by L{RawChapter.to_dict}.
        @type d: L{dict}
        @return: an instance of a raw chapter
        @rtype: L{RawChapter}
        """
        chapter = cls(
            index=d["index"],
            title=d["title"],
            text=d["text"],
            num_words=d.get("num_words", None)
        )
        return chapter

    def to_chapter(self, publisher, story_id):
        """
        Create a database chapter from this raw chapter.

        @param publisher: publisher this chapter is from
        @type publisher: L{zimfiction.db.models.Publisher}
        @param story_id: id of the story this chapter is part of
        @type story_id: L{int}
        @return: a db instance of this chapter
        @rtype: L{zimfiction.db.models.Chapter}
        """
        chapter = Chapter(
            story_id=story_id,
            index=self.index,
            title=self.title,
            text=self.text,
            num_words=self.num_words,
        )
        return chapter

    @classmethod
    def from_chapter(cls, chapter):
        """
        Instantiate a raw chapter from a db chapter.

        @param chapter: chapter to instantiate from
        @type chapter: L{zimfiction.db.models.Chapter}
        @return: a raw chapter instantiated from the db chapter
        @rtype: L{RawChapter}
        """
        ins = cls(
            index=chapter.index,
            title=chapter.title,
            text=chapter.text,
            num_words=chapter.num_words,
        )
        return ins


class RawSeriesMembership(object):
    """
    This class represents membership of a story in a series.

    @ivar publisher: publisher of the series
    @type publisher: L{str}
    @ivar name: name of the series
    @type name: L{str}
    @ivar index: index of the story in the series
    @type index: L{int}
    """
    def __init__(self, publisher, name, index):
        """
        The default constructor.

        @param publisher: publisher of the series
        @type publisher: L{str}
        @ivar name: name of the series
        @type name: L{str}
        @param index: index of the story in the series
        @type index: L{int}
        """
        assert isinstance(publisher, str)
        assert isinstance(name, str)
        assert isinstance(index, int)
        self.publisher = publisher
        self.name = name
        self.index = index

    def to_dict(self):
        """
        Create a dictionary describing this series membership.

        @return: a dict containing information about this series membership
        @rtype: L{dict}
        """
        data = {
            "publisher": self.publisher,
            "name": self.name,
            "index": self.index,
        }
        return data

    @classmethod
    def from_dict(cls, d):
        """
        Instantiate a new series membership from a dict describing it.

        @param d: a dict containing info about the series membership such as returned by L{RawSeriesMembership.to_dict}
        @type d: L{dict}
        @return: a instance of the series membership, matching the supplied dict
        @rtype: L{RawSeriesMembership}
        """
        return cls(**d)


class RawStory(object):
    """
    This class represents a raw, non-db story.

    This class is used to unify the import logic. Parsers should create
    instances of this class, which will then be converted to actual stories
    later on.

    @ivar id: id of the story
    @type id: L{int}
    @ivar title: title of this story
    @type title: L{str}
    @ivar summary: summary of this story
    @type summary: L{str}
    @ivar author: name of the author of this story
    @type author: L{str}
    @ivar author_url: URL of the author of this story
    @type author_url: L{str} or L{None}
    @ivar series: series this story is part of
    @type series: L{list} of L{RawSeriesMembership}
    @ivar categories: categories this series is part of
    @type categories: L{list} of L{str}
    @ivar genres: genres (generic tags) of this story
    @type genres: L{list} of L{str}
    @ivar language: language of this story
    @type language: L{str}
    @ivar is_done: whether this story is finished or not
    @type is_done: L{bool}
    @ivar published: date this story was published
    @type published: L{datetime.datetime}
    @ivar updated: date this story was updated
    @type updated: L{datetime.datetime}
    @ivar packaged: date this story was downloaded
    @type packaged: L{datetime.datetime}
    @ivar rating: rating of this story or L{None}
    @type rating: L{str} or L{None}
    @ivar warnings: warning tags of this story
    @type warnings: L{list} of L{str}
    @ivar publisher: name of the publishing site
    @type publisher: L{str}
    @ivar url: url of the story
    @type url: L{str}
    @ivar characters: list of character tags of this story
    @type characters: L{list} of L{str}
    @ivar relationships: list of relationship tags of this story
    @type relationships: L{list} of L{str}
    @ivar score: score/kudos/... of this story
    @type score: L{int}
    @ivar num_comments: number of comments in this story
    @type num_comments: L{int}
    @ivar chapters: chapters of this story
    @type chapters: L{list} of L{RawChapters}
    @ivar source_group: name of the source group this story is from
    @type source_group: L{str}
    @ivar source_name: name of the source this story is from
    @type source_name: L{str}
    """
    def __init__(
        self,
        id,
        title,
        summary,
        chapters,

        author,
        author_url,
        series,
        categories,
        genres,
        language,
        is_done,
        published,
        updated,
        packaged,
        warnings,
        publisher,
        url,
        characters,
        relationships,
        rating=None,
        score=0,
        num_comments=0,
        source_group="unknown",
        source_name="unknown",
        ):
        """
        The default constructor.

        WARNING: this constructor does not automatically normalize
        tags, relationships, ...! Be sure to normalize them first
        or use L{RawStory.convert_metadata}.

        @param id: id of the story
        @type id: L{int}
        @param title: title of this story
        @type title: L{str}
        @param summary: summary of this story
        @type summary: L{str}
        @param author: name of the author of this story
        @type author: L{str}
        @param author_url: URL of the author of this story
        @type author_url: L{str} or L{None}
        @param series: series this story is part of
        @type series: L{list} of L{RawSeriesMembership}
        @param categories: categories this series is part of
        @type categories: L{list} of L{str}
        @param genres: genres (generic tags) of this story
        @type genres: L{list} of L{str}
        @param language: language of this story
        @type language: L{str}
        @param is_done: whether this story is finished or not
        @type is_done: L{bool}
        @param published: date this story was published
        @type published: L{datetime.datetime}
        @param updated: date this story was updated
        @type updated: L{datetime.datetime}
        @param packaged: date this story was downloaded
        @type packaged: L{datetime.datetime}
        @param rating: rating of this story
        @type rating: L{str} or L{None}
        @param warnings: warning tags of this story
        @type warnings: L{list} of L{str}
        @param publisher: name of the publishing site
        @type publisher: L{str}
        @param url: url of the story
        @type url: L{str}
        @param characters: list of character tags of this story
        @type characters: L{list} of L{str}
        @param relationships: list of relationship tags of this story
        @type relationships: L{list} of L{str}
        @param score: score/kudos/... of this story
        @type score: L{int}
        @param num_comments: number of comments in this story
        @type num_comments: L{int}
        @param chapters: chapters of this story
        @type chapters: L{list} of L{RawChapters}
        @param source_group: name of the source group this story is from
        @type source_group: L{str}
        @param source_name: name of the source this story is from
        @type source_name: L{str}
        """
        assert isinstance(id, int)
        assert isinstance(title, str)
        assert isinstance(summary, str)
        assert isinstance(author, str)
        assert isinstance(author_url, str)
        assert isinstance(series, list)
        assert isinstance(categories, list)
        assert isinstance(genres, list)
        assert isinstance(language, str)
        assert isinstance(is_done, bool)
        assert isinstance(published, datetime.datetime)
        assert isinstance(updated, datetime.datetime)
        assert isinstance(packaged, datetime.datetime)
        assert isinstance(rating, str) or rating is None
        assert isinstance(warnings, list)
        assert isinstance(publisher, str)
        assert isinstance(url, str)
        assert isinstance(characters, list)
        assert isinstance(relationships, list)
        assert isinstance(score, int)
        assert isinstance(num_comments, int)
        assert isinstance(chapters, list)
        assert isinstance(source_group, str)
        assert isinstance(source_name, str)

        self.id = id
        self.title = title
        self.summary = summary
        self.author = author
        self.author_url = author_url
        self.series = series
        self.categories = categories
        self.genres = genres
        self.language = language
        self.is_done = is_done
        self.published = published
        self.updated = updated
        self.packaged = packaged
        self.rating = rating
        self.warnings = warnings
        self.publisher = publisher
        self.url = url
        self.characters = characters
        self.relationships = relationships
        self.score = score
        self.num_comments = num_comments
        self.chapters = chapters
        self.source_group = source_group
        self.source_name = source_name

    def to_dict(self):
        """
        Create a dictionary describing this story.

        @return: a dict containing all data of this story
        @rtype: L{dict}
        """
        data = {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,

            "author": self.author,
            "author_url": self.author_url,
            "series": [s.to_dict() for s in self.series],
            "categories": self.categories,
            "genres": self.genres,
            "language": self.language,
            "is_done": self.is_done,
            "published": self.published.isoformat(),
            "updated": self.updated.isoformat(),
            "packaged": self.packaged.isoformat(),
            "rating": self.rating,
            "warnings": self.warnings,
            "publisher": self.publisher,
            "url": self.url,
            "characters": self.characters,
            "relationships": self.relationships,
            "score": self.score,
            "num_comments": self.num_comments,
            "chapters": [c.to_dict() for c in self.chapters],
            "source_group": self.source_group,
            "source_name": self.source_name,
        }
        return data

    @classmethod
    def from_dict(cls, d):
        """
        Instantiate a new story from the data contained in the provided dictionary.

        @param d: a dict describing this story, such as returned by L{RawStory.to_dict}.
        @type d: L{dict}
        @return: an instance of a raw Story
        @rtype: L{RawStory}
        """
        copied = d.copy()
        copied["chapters"] = [RawChapter.from_dict(cd) for cd in copied["chapters"]]
        copied["series"] = [RawSeriesMembership.from_dict(cd) for cd in copied["series"]]
        copied["published"] = datetime.datetime.fromisoformat(copied["published"])
        copied["updated"] = datetime.datetime.fromisoformat(copied["updated"])
        copied["packaged"] = datetime.datetime.fromisoformat(copied["packaged"])
        story = cls(
            **copied,
        )
        return story

    def to_story(self, session, force_publisher=None):
        """
        Create a database story from this raw story.

        @param session: sqlalchemy session to use
        @type session: L{sqlalchemy.orm.Session}
        @param force_publisher: if not None, force all stories imported to have this publisher
        @type force_publisher: L{str} or L{None}
        @return: a db instance of this story
        @rtype: L{zimfiction.db.models.Story}
        """
        publisher = Publisher.as_unique(
            session,
            name=(self.publisher if force_publisher is None else force_publisher),
        )
        chapters = [
            Chapter(
                index=c.index,
                title=c.title,
                text=c.text,
                num_words=c.num_words,
            )
            for c in self.chapters
        ]
        author = Author.as_unique(
            session,
            publisher=publisher,
            name=self.author,
            url=self.author_url
        )
        source = Source.as_unique(
            session,
            group=self.source_group,
            name=self.source_name,
        )
        kwargs = {
            "id": self.id,
            "title": self.title,
            "author": author,
            "publisher": publisher,
            "summary": self.summary,
            "language": self.language,
            "is_done": self.is_done,
            "rating": self.rating,
            "published": self.published,
            "updated": self.updated,
            "packaged": self.packaged,
            "url": self.url,
            "score": self.score,
            "num_comments": self.num_comments,
            "chapters": chapters,
            "source": source,
        }
        story = Story(**kwargs)
        # link categories
        for category_name in self.categories:
            story.category_associations.append(
                StoryCategoryAssociation(
                    Category.as_unique(session, publisher=publisher, name=category_name),
                    implication_level=ImplicationLevel.SOURCE,
                ),
            )
        # link tags
        tag_i = 0
        for tagtype, taglist in [
            ("warning", self.warnings),
            ("relationship", self.relationships),
            ("character", self.characters),
            ("genre", self.genres),
        ]:
            for tagname in taglist:
                story.tag_associations.append(
                    StoryTagAssociation(
                        Tag.as_unique(session, type=tagtype, name=tagname),
                        index=tag_i,
                        implication_level=ImplicationLevel.SOURCE,
                    ),
                )
                tag_i += 1
        # link series
        for sm in self.series:
            story.series_associations.append(
                StorySeriesAssociation(
                    Series.as_unique(session, publisher=publisher, name=sm.name),  # todo: use publisher of membership
                    index=sm.index,
                ),
            )
        return story

    @classmethod
    def from_story(cls, story):
        """
        Instantiate a raw story from a db story.

        @param story: story to instantiate from
        @type story: L{zimfiction.db.models.Story}
        @return: a raw story instantiated from the db story
        @rtype: L{RawStory}
        """
        ins = cls(
            id=story.id,
            title=story.title,
            summary=story.summary,
            author=story.author.name,
            author_url=story.author.url,
            series=[
                RawSeriesMembership(
                    publisher=sa.series_publisher,
                    name=sa.series_name,
                    index=sa.index,
                )
                for sa in story.series_associations
            ],
            categories=[c.name for c in story.explicit_categories],
            genres=[tag.name for tag in story.genres],
            language=story.language,
            is_done=story.is_done,
            published=story.published,
            updated=story.updated,
            packaged=story.packaged,
            rating=story.rating,
            warnings=[tag.name for tag in story.warnings],
            publisher=story.publisher.name,
            url=story.url,
            characters=[tag.name for tag in story.characters],
            relationships=[tag.name for tag in story.relationships],
            score=story.score,
            num_comments=story.num_comments,
            chapters=[
                RawChapter.from_chapter(c)
                for c in story.chapters
            ],
            source_group=story.source.group,
            source_name=story.source.name,
        )
        return ins

    @staticmethod
    def convert_metadata(metadata):
        """
        Convert dict containing metadata keys and values as written by
        fanficfare into a dict that could be passed to L{RawStory.__init__}.

        This method can not populate the returned dict with the following keys:

            - title
            - author
            - summary (unless metadata 'Summary' is correctly set)
            - chapters
            - source_group
            - source_name

        This method takes care of normalizing relationships, categories, and so on.
        This method may initialize some values with defaults. It is recommended
        to update the returned dict by the actual values.

        @param metadata: a dict mapping fanficfare keys to fanficfare values
        @type metadata: L{dict}
        @return: a dict that could be passed as **kwargs to __init__
        @rtype: L{dict}
        """
        ret = {
            "genres": [],
            "characters": [],
            "relationships": [],
            "warnings": [],
        }
        series = []
        if "Story URL" in metadata:
            ret["url"] = metadata["Story URL"]
            ret["id"] = id_from_url(metadata["Story URL"])
        if "Summary" in metadata:
            ret["summary"] = metadata["Summary"]
        if "Publisher" in metadata:
            publisher = metadata["Publisher"]
            ret["publisher"] = publisher.strip()
        if "Series" in metadata:
            value = metadata["Series"]
            series_index = int(value[value.rfind("[")+1: value.rfind("]")])
            series_name = value[:value.rfind("[") - 1]
            # ensure that we don't add a series twice - because apparently
            # some fics contain the data multiple times
            if not any([e.name == series_name for e in series]):
                series.append(RawSeriesMembership(publisher, series_name, series_index))
        ret["series"] = series
        if "Category" in metadata:
            splitted_categories = split_categories(metadata["Category"])
            ret["categories"] = [normalize_category(c) for c in splitted_categories]
        for key in ("Genre", "Genres", "Erotica Tags"):
            if key in metadata:
                for tag in split_tags(metadata[key]):
                    add_to_dict_list(ret, "genres", tag)
        if "Warnings" in metadata:
            for tag in split_tags(metadata["Warnings"]):
                add_to_dict_list(ret, "warnings", tag)
        if "Characters" in metadata:
            for tag in split_tags(metadata["Characters"]):
                add_to_dict_list(ret, "characters", tag)
        if "Relationships" in metadata:
            for tag in split_tags(metadata["Relationships"]):
                add_to_dict_list(ret, "relationships", normalize_relationship(tag))
        for key in ("Chars/Pairs", "Characters/Pairing"):
            if key in metadata:
                for tag in split_tags(metadata[key]):
                    if ("&" in tag) or ("/" in tag):
                        add_to_dict_list(ret, "relationships", tag)
                    else:
                        add_to_dict_list(ret, "characters", tag)
        if "Language" in metadata:
            ret["language"] = metadata["Language"].strip()
        if "Published" in metadata:
            ret["published"] = datetime.datetime.fromisoformat(metadata["Published"])
        if "Updated" in metadata:
            ret["updated"] = datetime.datetime.fromisoformat(metadata["Updated"])
        elif "published" in ret:
            # default to updated=published
            ret["updated"] = ret["published"]
        if "Packaged" in metadata:
            ret["packaged"] = datetime.datetime.fromisoformat(metadata["Packaged"])
        elif "updated" in ret:
            # default to packaged=updated
            ret["packaged"] = ret["updated"]
        if "Rating" in metadata:
            ret["rating"] = metadata["Rating"].strip()
        if "Comments" in metadata:
            ret["num_comments"] = int(metadata["Comments"].strip())
        for key in ("Kudos", "Favorites"):
            if key in metadata:
                ret["score"] = int(metadata[key].strip())
        if "Status" in metadata:
            ret["is_done"] = is_done_from_status(metadata["Status"])
        if "Author URL" in metadata:
            ret["author_url"] = metadata["Author URL"].strip()
        # remove duplicate tags/categories/relationships
        for key in ("genres", "warnings", "characters", "relationships", "categories"):
            if key in ret:
                ret[key] = remove_duplicates(ret[key])
        return ret
