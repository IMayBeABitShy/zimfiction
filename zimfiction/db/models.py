"""
This module contains the database models.
"""

# resource: https://stackoverflow.com/questions/7504753/relations-on-composite-keys-using-sqlalchemy

from sqlalchemy.orm import registry, relationship, deferred
from sqlalchemy import Column, ForeignKeyConstraint, ForeignKey
from sqlalchemy import Integer, String, DateTime, Boolean, UnicodeText, Unicode
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.orderinglist import ordering_list

from ..util import format_date, format_number, normalize_relationship
from .unique import UniqueMixin


# setup ORM base
mapper_registry = registry()
Base = mapper_registry.generate_base()


# various constants
MAX_SITE_LENGTH = 64
MAX_AUTHOR_NAME_LENGTH = 256
MAX_CATEGORY_NAME_LENGTH = 1024
MAX_STORY_TITLE_LENGTH = 1024
MAX_STORY_TAG_LENGTH = 512
MAX_STORY_RATING_LENGTH = 32
MAX_STORY_SUMMARY_LENGTH = 4 * 1024
MAX_STORY_URL_LENGTH = 512
MAX_STORY_SERIES_LENGTH = 512
MAX_LANGUAGE_LENGTH = 32
MAX_CHAPTER_TITLE_LENGTH = 512
MAX_CHAPTER_TEXT_LENGTH = 16 * 1024 * 1024
MAX_AUTHOR_URL_LENGTH = 1024
MAX_TAG_TYPE_LENGTH = 32


def _get_longtext_type(max_length=None):
    """
    A helper function returning the type definition for a long, variable
    size text.

    This method is used so that we can quickly change the code to use
    or ignore the "max_length" type.

    @param max_length: max length for the text
    @type max_length: L{int} or L{None}
    @return: a type that can be used as argument for L{sqlalchemy.Column}
    @rtype:
    """
    return UnicodeText


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

    @property
    def num_stories(self):
        """
        Return the number of stories by this publisher.

        @return: the number of stories by this publisher
        @rtype: L{int}
        """
        return len(self.stories)


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
    story_associations = relationship(
        "StoryCategoryAssociation",
        back_populates="category",
        cascade="all, delete-orphan",
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


class StoryCategoryAssociation(Base):
    """
    A model for the association story<->category providing the "implied" attribute.
    """
    __tablename__ = "story_has_category"

    story_publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    story_id = Column(Integer, primary_key=True)
    category_publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    category_name = Column(Unicode(MAX_CATEGORY_NAME_LENGTH), primary_key=True)
    implied = Column(Boolean, default=False, nullable=False)

    story = relationship(
        "Story",
        back_populates="category_associations",
    )
    category = relationship(
        "Category",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            [story_publisher, story_id],
            ["story.publisher_name", "story.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [category_publisher, category_name],
            ["category.publisher_name", "category.name"],
            ondelete="CASCADE",
        ),
    )

    def __init__(self, category, implied=False):
        """
        The default constructor.

        @param category: category this association is for
        @type category: L{Category}
        @param implied: whether this category is implied or not
        @type implied: L{bool}
        """
        assert isinstance(category, Category)
        assert isinstance(implied, bool)
        self.category = category
        self.implied = implied


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
    A model for the association of story->tag, providing the "index"
    attribute for order and the "implied" attribute.
    """
    __tablename__ = "story_has_tag"

    story_publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    story_id = Column(Integer, autoincrement=False, primary_key=True)
    tag_type = Column(Unicode(MAX_TAG_TYPE_LENGTH), primary_key=True)
    tag_name = Column(Unicode(MAX_STORY_TAG_LENGTH), primary_key=True)
    index = Column(Integer, autoincrement=False)
    implied = Column(Boolean, default=False, nullable=False)

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

    def __init__(self, tag, index=None, implied=False):
        """
        The default constructor.

        @param tag: tag this association is for
        @type tag: L{Tag}
        @param index: index of this tag
        @type index: L{int} or L{None}
        @param implied: wheteher this tag is implied or not
        @type implied: L{bool}
        """
        assert isinstance(tag, Tag)
        assert isinstance(index, int) or (index is None)
        assert isinstance(implied, bool)
        self.tag = tag
        if index is None:
            self.index = 0
        else:
            self.index = index
        self.implied = implied


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
        overlaps="publisher, stories",
    )
    chapters = relationship(
        "Chapter",
        back_populates="story",
        order_by="Chapter.index",
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
    summary = Column(_get_longtext_type(MAX_STORY_SUMMARY_LENGTH), nullable=False)
    category_associations = relationship(
        "StoryCategoryAssociation",
        back_populates="story",
        cascade="all, delete-orphan",
    )
    categories = association_proxy(
        "category_associations",
        "category",
    )
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
    def implied_categories(self):
        """
        A list of all implied categories.

        @return: a list of all implied categories
        @rtype: L{list} of L{Category}
        """
        return [c_a.category for c_a in self.category_associations if c_a.implied]

    @property
    def explicit_categories(self):
        """
        A list of all explicit (non-implied) categories.

        @return: a list of all non-implied categories
        @rtype: L{list} of L{Category}
        """
        return [c_a.category for c_a in self.category_associations if not c_a.implied]

    @property
    def implied_tags(self):
        """
        A list of all implied tags.

        @return: a list of all implied tags, regardless of type
        @rtype: L{list} of L{Tag}
        """
        return [t_a.tag for t_a in self.tag_associations if t_a.implied]

    @property
    def explicit_tags(self):
        """
        A list of all explicit (non-implied) tags.

        @return: a list of all non-implied tags, regardless of type
        @rtype: L{list} of L{Tag}
        """
        return [t_a.tag for t_a in self.tag_associations if not t_a.implied]

    @property
    def warnings(self):
        """
        A list of all explicit warning tags.

        @return: a list of all warning tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.explicit_tags if tag.type == "warning"]

    @property
    def implied_warnings(self):
        """
        A list of all implied warning tags.

        @return: a list of all implied warning tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.implied_tags if tag.type == "warning"]

    @property
    def genres(self):
        """
        A list of all genre tags.

        @return: a list of all genre tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.explicit_tags if tag.type == "genre"]

    @property
    def implied_genres(self):
        """
        A list of all implied genre tags.

        @return: a list of all implied genre tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.implied_tags if tag.type == "genre"]

    @property
    def relationships(self):
        """
        A list of all relationship tags.

        @return: a list of all relationship tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.explicit_tags if tag.type == "relationship"]

    @property
    def implied_relationships(self):
        """
        A list of all relationship tags.

        @return: a list of all implied relationship tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.implied_tags if tag.type == "relationship"]

    @property
    def characters(self):
        """
        A list of all character tags.

        @return: a list of all character tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.explicit_tags if tag.type == "character"]

    @property
    def implied_characters(self):
        """
        A list of all implied character tags.

        @return: a list of all implied character tags
        @rtype: L{list} of L{Tag}
        """
        return [tag for tag in self.implied_tags if tag.type == "character"]

    @property
    def ordered_tags(self):
        """
        Return a list of all explicit tags, ordered by type to match ao3.

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
            "rating": (self.rating.title() if self.rating is not None else "Unknown"),
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
            "categories": [c.name for c in self.explicit_categories],
            "implied_categories": [c.name for c in self.implied_categories],
            "tags": [t.name.lower() for t in self.genres],
            "implied_tags": [t.name.lower() for t in self.implied_genres],
            "warnings": [t.name for t in self.warnings],
            "implied_warnings": [t.name for t in self.implied_warnings],
            "relationships": [normalize_relationship(t.name) for t in self.relationships],
            "implied_relationships": [normalize_relationship(t.name) for t in self.implied_relationships],
            "characters": [t.name for t in self.characters],
            "implied_characters": [t.name for t in self.implied_characters],
            "updated": format_date(self.updated),
            "language": self.language,
            "status": self.status,
            "words": self.total_words,
            "chapters": len(self.chapters),
            "score": self.score,
            "rating": (self.rating.title() if self.rating is not None else "Unknown"),
            "category_count": len(self.categories),
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
        overlaps="chapters, publisher",
        cascade="all",
    )
    index = Column(Integer, primary_key=True, nullable=False, autoincrement=False)
    title = Column(Unicode(MAX_CHAPTER_TITLE_LENGTH), nullable=False)
    text = deferred(Column(_get_longtext_type(MAX_CHAPTER_TEXT_LENGTH), nullable=False))
    num_words = Column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            [publisher_name, story_id],
            ["story.publisher_name", "story.id"],
            ondelete="CASCADE",
        ),
    )
