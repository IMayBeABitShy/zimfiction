"""
This module contains classes for raw (non-db) stories.
"""
import datetime

from ..util import count_words
from ..db.models import Chapter, Story, Author, Category, Tag, Series, Publisher
from ..db.models import StoryTagAssociation, StorySeriesAssociation, StoryCategoryAssociation


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
        ):
        """
        The default constructor.

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
        }
        story = Story(**kwargs)
        # link categories
        for category_name in self.categories:
            story.category_associations.append(
                StoryCategoryAssociation(
                    Category.as_unique(session, publisher=publisher, name=category_name),
                    implied=False,
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
                        implied=False,
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
        )
        return ins
