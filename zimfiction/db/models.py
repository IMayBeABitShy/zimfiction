"""
This module contains the database models.

NOTE: there are two types of IDs used here:
- class.id may reference a site provided id that's not unique between sites
- class.uid references a unqiue id that's not stable between multiple imports
"""

# resource: https://stackoverflow.com/questions/7504753/relations-on-composite-keys-using-sqlalchemy

from sqlalchemy import Column, Index, ForeignKeyConstraint, ForeignKey, func, select
from sqlalchemy import Integer, String, DateTime, Boolean, UnicodeText, Unicode
from sqlalchemy.orm import registry, relationship, deferred
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.ext.hybrid import hybrid_property

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
MAX_STORY_RATING_LENGTH = 64
MAX_STORY_SUMMARY_LENGTH = 4 * 1024
MAX_STORY_URL_LENGTH = 512
MAX_STORY_SERIES_LENGTH = 512
MAX_LANGUAGE_LENGTH = 64
MAX_CHAPTER_TITLE_LENGTH = 512
MAX_CHAPTER_TEXT_LENGTH = 16 * 1024 * 1024
MAX_AUTHOR_URL_LENGTH = 2 * 1024
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

    uid = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(MAX_SITE_LENGTH), unique=True, index=True, nullable=False)
    stories = relationship("Story", back_populates="publisher", overlaps="stories")
    authors = relationship("Author", back_populates="publisher")
    categories = relationship("Category", back_populates="publisher")
    series = relationship("Series", back_populates="publisher")

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

    uid = Column(Integer, primary_key=True, autoincrement=True)
    publisher_uid = Column(Integer, ForeignKey("publisher.uid"), nullable=False)
    name = Column(Unicode(MAX_AUTHOR_NAME_LENGTH), nullable=False)
    url = Column(String(MAX_AUTHOR_URL_LENGTH))
    publisher = relationship("Publisher", back_populates="authors")
    stories = relationship("Story", back_populates="author")

    @classmethod
    def unique_hash(cls, publisher, name, url):
        return (publisher.name, name)

    @classmethod
    def unique_filter(cls, query, publisher, name, url):
        return query.filter(
            Author.publisher.has(name=publisher.name),
            Author.name == name,
        )

Index("author_name_index", Author.publisher_uid, Author.name, unique=True)


class Category(UniqueMixin, Base):
    """
    This class represents a category in the database.
    """
    __tablename__ = "category"

    uid = Column(Integer, primary_key=True, autoincrement=True)
    publisher_uid = Column(Integer, ForeignKey("publisher.uid"), nullable=False)
    name = Column(Unicode(MAX_CATEGORY_NAME_LENGTH), nullable=False)
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
            Category.publisher.has(name=publisher.name),
            Category.name == name,
        )

    @hybrid_property
    def num_stories(self):
        """
        The number of stories in this category.

        @return: number of stories in this category
        @rtype: L{int}
        """
        return len(self.stories)

    @num_stories.inplace.expression
    @classmethod
    def _num_stories_expression(cls):
        return (
            select(func.count(StoryCategoryAssociation))
            .where(
                StoryCategoryAssociation.category_uid == cls.uid,
            )
            .label("num_stories")
        )

Index("category_name_index", Category.publisher_uid, Category.name, unique=True)


class StoryCategoryAssociation(Base):
    """
    A model for the association story<->category providing the "implied" attribute.
    """
    __tablename__ = "story_has_category"

    story_uid = Column(Integer, primary_key=True)
    category_uid = Column(Integer, primary_key=True)
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
            [story_uid],
            ["story.uid"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [category_uid],
            ["category.uid"],
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

    uid = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(Unicode(MAX_TAG_TYPE_LENGTH), nullable=False)
    name = Column(Unicode(MAX_STORY_TAG_LENGTH), nullable=False)
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

Index("tag_name_index", Tag.type, Tag.name)


class StoryTagAssociation(Base):
    """
    A model for the association of story->tag, providing the "index"
    attribute for order and the "implied" attribute.
    """
    __tablename__ = "story_has_tag"

    story_uid = Column(Integer, autoincrement=False, primary_key=True)
    tag_uid = Column(Integer, primary_key=True)
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
            [story_uid],
            ["story.uid"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [tag_uid],
            ["tag.uid"],
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

    uid = Column(Integer, primary_key=True, autoincrement=True)
    publisher_uid = Column(Integer, ForeignKey("publisher.uid"), autoincrement=False, nullable=False)
    name = Column(Unicode(MAX_STORY_SERIES_LENGTH), nullable=False)
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
            Series.publisher.has(name=publisher.name),
            Series.name == name,
        )

Index("series_name_index", Series.publisher_uid, Series.name)


class StorySeriesAssociation(Base):
    """
    A model for the association of story->series, providing the "index" attribute for order.
    """
    __tablename__ = "story_in_series"

    story_uid = Column(Integer, autoincrement=False, primary_key=True)
    series_uid = Column(Integer, autoincrement=False, primary_key=True)
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
            [story_uid],
            ["story.uid"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [series_uid],
            ["series.uid"],
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

    uid = Column(Integer, autoincrement=True, primary_key=True)
    publisher_uid = Column(Integer, ForeignKey("publisher.uid"), nullable=False)
    publisher = relationship("Publisher", back_populates="stories", overlaps="stories")
    id = Column(Integer, primary_key=False, autoincrement=False, nullable=False)
    title = Column(Unicode(MAX_STORY_TITLE_LENGTH), nullable=False)
    author_uid = Column(Integer, ForeignKey("author.uid"), autoincrement=False, nullable=False)
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
    summary = deferred(Column(_get_longtext_type(MAX_STORY_SUMMARY_LENGTH), nullable=False))
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
        order_by="StoryTagAssociation.index",
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
            [author_uid],
            ["author.uid"],
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

    @hybrid_property
    def total_words(self):
        """
        The total number of words in this story.

        This is a sqlalchemy hybrid property. It's behavior differs
        between class and instance level.

        @return: the number of words in this story
        @rtype: L{int}
        """
        return sum([chapter.num_words for chapter in self.chapters])

    @total_words.inplace.expression
    @classmethod
    def _total_words_expression(cls):
        return (
            select(func.sum(Chapter.num_words))
            .where(
                Chapter.story_uid == cls.uid,
            )
            .label("total_words")
        )

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
            "series": [(sa.series.name, sa.index) for sa in self.series_associations],
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

Index("story_id_index", Story.publisher_uid, Story.id, unique=True)


class Chapter(Base):
    """
    This class represents a chapter in the database.
    """
    __tablename__ = "chapter"

    uid = Column(Integer, primary_key=True, autoincrement=True)
    story_uid = Column(Integer, autoincrement=False, nullable=False)
    story = relationship(
        "Story",
        back_populates="chapters",
        overlaps="chapters, publisher",
        cascade="all",
    )
    index = Column(Integer, nullable=False, autoincrement=False)
    title = Column(Unicode(MAX_CHAPTER_TITLE_LENGTH), nullable=False)
    text = deferred(Column(_get_longtext_type(MAX_CHAPTER_TEXT_LENGTH), nullable=False))
    num_words = Column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            [story_uid],
            ["story.uid"],
            ondelete="CASCADE",
        ),
    )

Index("chapter_id_index", Chapter.story_uid, Chapter.index, unique=True)
