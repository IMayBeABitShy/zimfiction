"""
This module contains the database models.
"""

# resource: https://stackoverflow.com/questions/7504753/relations-on-composite-keys-using-sqlalchemy

from sqlalchemy.orm import registry, relationship, deferred
from sqlalchemy import Column, ForeignKeyConstraint, Table, ForeignKey
from sqlalchemy import Integer, String, DateTime, Boolean, UnicodeText, Unicode
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.orderinglist import ordering_list

from ..util import format_date, format_number
from .unique import UniqueMixin


# setup ORM base
mapper_registry = registry()
Base = mapper_registry.generate_base()


# various constants
MAX_SITE_LENGTH = 32
MAX_AUTHOR_NAME_LENGTH = 128
MAX_CATEGORY_NAME_LENGTH = 256
MAX_STORY_TITLE_LENGTH = 256
MAX_STORY_TAG_LENGTH = 256
MAX_STORY_RATING_LENGTH = 16
MAX_STORY_SUMMARY_LENGTH = 2 * 1024
MAX_STORY_URL_LENGTH = 256
MAX_STORY_SERIES_LENGTH = 256
MAX_LANGUAGE_LENGTH = 16
MAX_CHAPTER_TITLE_LENGTH = 64
MAX_CHAPTER_TEXT_LENGTH = 16 * 1024 * 1024
MAX_AUTHOR_URL_LENGTH = 256
MAX_TAG_TYPE_LENGTH = 32


story_has_category_table = Table(
    "story_has_category",
    Base.metadata,
    Column("story_publisher", String(MAX_SITE_LENGTH), nullable=False),
    Column("story_id", Integer, nullable=False),
    Column("category_publisher", String(MAX_SITE_LENGTH) , nullable=False),
    Column("category_name", Unicode(MAX_CATEGORY_NAME_LENGTH)),
    ForeignKeyConstraint(
        ("story_publisher", "story_id"),
        ("story.publisher_name", "story.id"),
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ("category_publisher", "category_name"),
        ("category.publisher_name", "category.name"),
        ondelete="CASCADE",
    ),
)


class Publisher(UniqueMixin, Base):
    """
    This class represents a publisher in the database.
    """
    __tablename__ = "publisher"

    name = Column(String(MAX_SITE_LENGTH), primary_key=True)
    stories = relationship("Story", back_populates="publisher", overlaps="stories")
    authors = relationship("Author", back_populates="publisher")
    categories = relationship("Category", back_populates="publisher")
    series = relationship("Series", back_populates="publisher")
    chapters = relationship("Chapter", back_populates="publisher", overlaps="chapters")

    @classmethod
    def unique_hash(cls, name):
        return name

    @classmethod
    def unique_filter(cls, query, name):
        return query.filter(
            Publisher.name == name,
        )


class Author(UniqueMixin, Base):
    """
    This class represents an author in the database.
    """
    __tablename__ = "author"

    publisher_name = Column(String(MAX_SITE_LENGTH), ForeignKey("publisher.name"), primary_key=True)
    name = Column(Unicode(MAX_AUTHOR_NAME_LENGTH), primary_key=True)
    url = Column(String(MAX_AUTHOR_URL_LENGTH))
    publisher = relationship("Publisher", back_populates="authors")
    stories = relationship("Story", back_populates="author")

    @classmethod
    def unique_hash(cls, publisher, name, url):
        return (publisher.name, name)

    @classmethod
    def unique_filter(cls, query, publisher, name, url):
        return query.filter(
            Author.publisher_name == publisher.name,
            Author.name == name,
        )


class Category(UniqueMixin, Base):
    """
    This class represents a category in the database.
    """
    __tablename__ = "category"

    publisher_name = Column(String(MAX_SITE_LENGTH), ForeignKey("publisher.name"), primary_key=True)
    name = Column(Unicode(MAX_CATEGORY_NAME_LENGTH), primary_key=True)
    publisher = relationship("Publisher", back_populates="categories")
    stories = relationship("Story", secondary=story_has_category_table, back_populates="categories")

    @classmethod
    def unique_hash(cls, publisher, name):
        return (publisher.name, name)

    @classmethod
    def unique_filter(cls, query, publisher, name):
        return query.filter(
            Category.publisher_name == publisher.name,
            Category.name == name,
        )

    @property
    def num_stories(self):
        """
        The number of stories in this category.

        @return: number of stories in this category
        @rtype: L{int}
        """
        return len(self.stories)


class Tag(UniqueMixin, Base):
    """
    This class represents a tag in the database.

    It is also used for warnings and similiar information.
    """
    __tablename__ = "tag"

    type = Column(Unicode(MAX_TAG_TYPE_LENGTH), primary_key=True)
    name = Column(Unicode(MAX_STORY_TAG_LENGTH), primary_key=True)
    story_associations = relationship(
        "StoryTagAssociation",
        back_populates="tag",
        cascade="all, delete-orphan",
    )
    stories = association_proxy(
        "story_associations",
        "story",
    )

    @classmethod
    def unique_hash(cls, type, name):
        return (type, name)

    @classmethod
    def unique_filter(cls, query, type, name):
        return query.filter(
            Tag.type == type,
            Tag.name == name,
        )


class StoryTagAssociation(Base):
    """
    A model for the association of story->tag, providing the "index" attribute for order.
    """
    __tablename__ = "story_has_tag"

    story_publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    story_id = Column(Integer, autoincrement=False, primary_key=True)
    tag_type = Column(Unicode(MAX_TAG_TYPE_LENGTH), primary_key=True)
    tag_name = Column(Unicode(MAX_STORY_TAG_LENGTH), primary_key=True)
    index = Column(Integer, autoincrement=False)

    story = relationship(
        "Story",
        back_populates="tag_associations",
    )
    tag = relationship(
        "Tag",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            [story_publisher, story_id],
            ["story.publisher_name", "story.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [tag_type, tag_name],
            ["tag.type", "tag.name"],
            ondelete="CASCADE",
        ),
    )

    def __init__(self, tag, index=None):
        """
        The default constructor.

        @param tag: tag this association is for
        @type tag: L{Tag}
        @param index: index of this tag
        @type index: L{int} or L{None}
        """
        assert isinstance(tag, Tag)
        assert isinstance(index, int) or (index is None)
        self.tag = tag
        if index is None:
            self.index = 0
        else:
            self.index = index


class Series(UniqueMixin, Base):
    """
    This class represents a series of stories in the database.
    """
    __tablename__ = "series"

    publisher_name = Column(String(MAX_SITE_LENGTH), ForeignKey("publisher.name"), primary_key=True)
    name = Column(Unicode(MAX_STORY_SERIES_LENGTH), primary_key=True)
    publisher = relationship("Publisher", back_populates="series")
    story_associations = relationship(
        "StorySeriesAssociation",
        back_populates="series",
        cascade="all, delete-orphan",
        collection_class=ordering_list("index"),
        order_by="StorySeriesAssociation.index",
    )
    stories = association_proxy(
        "story_associations",
        "story",
    )

    @classmethod
    def unique_hash(cls, publisher, name):
        return (publisher.name, name)

    @classmethod
    def unique_filter(cls, query, publisher, name):
        return query.filter(
            Series.publisher_name == publisher.name,
            Series.name == name,
        )


class StorySeriesAssociation(Base):
    """
    A model for the association of story->series, providing the "index" attribute for order.
    """
    __tablename__ = "story_in_series"

    story_publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    story_id = Column(Integer, autoincrement=False, primary_key=True)
    series_publisher = Column(Unicode(MAX_SITE_LENGTH), primary_key=True)
    series_name = Column(Unicode(MAX_STORY_SERIES_LENGTH), primary_key=True)
    index = Column(Integer, autoincrement=False)

    story = relationship(
        "Story",
        back_populates="series_associations",
    )
    series = relationship(
        "Series",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            [story_publisher, story_id],
            ["story.publisher_name", "story.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [series_publisher, series_name],
            ["series.publisher_name", "series.name"],
            ondelete="CASCADE",
        ),
    )

    def __init__(self, series, index=None):
        """
        The default constructor.

        @param series: Series this association is for
        @type series: L{Series}
        @param index: index of the story in the series
        @type index: L{int} or L{None}
        """
        assert isinstance(series, Series)
        assert isinstance(index, int) or (index is None)
        self.series = series
        if index is None:
            self.index = 0
        else:
            self.index = index


class Story(Base):
    """
    This class represents a story in the database.
    """
    __tablename__ = "story"

    publisher_name = Column(String(MAX_SITE_LENGTH), ForeignKey("publisher.name"), primary_key=True)
    publisher = relationship("Publisher", back_populates="stories", overlaps="stories")
    id = Column(Integer, primary_key=True, autoincrement=False)
    title = Column(Unicode(MAX_STORY_TITLE_LENGTH), nullable=False)
    author_name = Column(String(MAX_AUTHOR_NAME_LENGTH), nullable=False)
    author = relationship(
        "Author",
        back_populates="stories",
        foreign_keys="Story.author_name",
    )
    chapters = relationship(
        "Chapter",
        back_populates="story",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    url = Column(String(MAX_STORY_URL_LENGTH), unique=True)
    language = Column(String(MAX_LANGUAGE_LENGTH), nullable=False)
    is_done = Column(Boolean, nullable=False)
    published = Column(DateTime, nullable=False)
    updated = Column(DateTime, nullable=False)
    packaged = Column(DateTime, nullable=False)
    rating = Column(String(MAX_STORY_RATING_LENGTH), nullable=True)
    summary = Column(UnicodeText(MAX_STORY_SUMMARY_LENGTH), nullable=False)
    categories = relationship("Category", secondary=story_has_category_table, back_populates="stories")
    tag_associations = relationship(
        "StoryTagAssociation",
        back_populates="story",
        cascade="all, delete-orphan",
        collection_class=ordering_list("index"),
        order_by="StoryTagAssociation.index"
    )
    tags = association_proxy(
        "tag_associations",
        "tag",
    )
    score = Column(Integer, autoincrement=False, default=0)
    num_comments = Column(Integer, autoincrement=False, default=0)
    series = relationship(
        "Series",
        back_populates="stories",
        cascade="all, delete-orphan",
        overlaps="stories",
    )
    series_associations = relationship(
        "StorySeriesAssociation",
        back_populates="story",
        cascade="all, delete-orphan",
    )
    series = association_proxy(
        "series_associations",
        "series",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            [publisher_name, author_name],
            ["author.publisher_name", "author.name"],
            ondelete="CASCADE",
        ),
    )

    def remove_from_related(self):
        """
        Remove this story from all related objects.
        """
        # self.publisher.stories.remove(self)
        # self.author.stories.remove(self)
        self.publisher = None
        self.author = None
        # for category in self.categories:
        #     category.stories.remove(self)
        self.categories = []
        self.tag_associations = []
        self.series_associations = []

    @property
    def warnings(self):
        """
        A list of all warning tags.

        @return: a list of all warning tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.tags if tag.type == "warning"]

    @property
    def genres(self):
        """
        A list of all genre tags.

        @return: a list of all genre tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.tags if tag.type == "genre"]

    @property
    def relationships(self):
        """
        A list of all relationship tags.

        @return: a list of all relationship tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.tags if tag.type == "relationship"]

    @property
    def characters(self):
        """
        A list of all character tags.

        @return: a list of all character tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.tags if tag.type == "character"]

    @property
    def ordered_tags(self):
        """
        Return a list of all tags, ordered by type to match ao3.

        @return: an ordered list of all tags
        @rtype: L{list} of L{Tag}
        """
        return self.warnings + self.relationships + self.characters + self.genres

    @property
    def total_words(self):
        """
        The total number of words in this story.

        @return: the number of words in this story
        @rtype: L{int}
        """
        return sum([chapter.num_words for chapter in self.chapters])

    @property
    def status(self):
        """
        A string describing the status of this story.

        @return: a string describing the status of this story
        @rtype: L{str}
        """
        return ("Complete" if self.is_done else "In-Progress")

    def get_preview_data(self):
        """
        Return a dict containing all the data needed to show a short preview of this story.

        @return: a dict containing said data
        @rtype: L{dict}
        """
        data = {
            "title": self.title,
            "publisher": self.publisher.name,
            "id": self.id,
            "author": self.author.name,
            "categories": [c.name for c in self.categories],
            "tags": [(t.type, t.name) for t in self.ordered_tags],
            "updated": format_date(self.updated),
            "summary": self.summary,
            "language": self.language,
            "status": self.status,
            "words": format_number(self.total_words),
            "chapters": len(self.chapters),
            "score": self.score,
            "series": [(sa.series.publisher.name, sa.index) for sa in self.series_associations],
            "rating": self.rating.title(),
        }
        return data

    def get_search_data(self):
        """
        Return a dict containing all the data needed to search this fic.

        @return: a dict containing said data
        @rtype: L{dict}
        """
        data = {
            "publisher": self.publisher.name,
            "id": self.id,
            "categories": [c.name for c in self.categories],
            "tags": [t.name for t in self.genres],
            "warnings": [t.name for t in self.warnings],
            "relationships": [t.name for t in self.relationships],
            "characters": [t.name for t in self.characters],
            "updated": format_date(self.updated),
            "language": self.language,
            "status": self.status,
            "words": self.total_words,
            "chapters": len(self.chapters),
            "score": self.score,
            "rating": self.rating.title(),
        }
        return data


class Chapter(Base):
    """
    This class represents a chapter in the database.
    """
    __tablename__ = "chapter"

    publisher_name = Column(String(MAX_SITE_LENGTH), ForeignKey("publisher.name"), primary_key=True)
    publisher = relationship("Publisher", back_populates="chapters", overlaps="chapters")
    story_id = Column(Integer, primary_key=True, autoincrement=False)
    story = relationship(
        "Story",
        back_populates="chapters",
        foreign_keys="Chapter.story_id",
        cascade="all",
    )
    index = Column(Integer, primary_key=True, nullable=False, autoincrement=False)
    title = Column(Unicode(MAX_CHAPTER_TITLE_LENGTH), nullable=False)
    text = deferred(Column(UnicodeText(MAX_CHAPTER_TEXT_LENGTH), nullable=False))
    num_words = Column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            [publisher_name, story_id],
            ["story.publisher_name", "story.id"],
            ondelete="CASCADE",
        ),
    )
