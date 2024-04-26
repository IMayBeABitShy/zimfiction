"""
This module contains the database models.
"""

# resource: https://stackoverflow.com/questions/7504753/relations-on-composite-keys-using-sqlalchemy

from sqlalchemy.orm import registry, relationship
from sqlalchemy import Column, ForeignKeyConstraint, Table
from sqlalchemy import Integer, String, DateTime, Boolean, UnicodeText, Unicode
from sqlalchemy.ext.orderinglist import ordering_list

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


story_has_tag_table = Table(
    "story_has_tag",
    Base.metadata,
    Column("story_publisher", String(MAX_SITE_LENGTH), nullable=False),
    Column("story_id", Integer, nullable=False),
    Column("tag_type", Unicode(MAX_STORY_TAG_LENGTH)),
    Column("tag", Unicode(MAX_STORY_TAG_LENGTH)),
    ForeignKeyConstraint(
        ("story_publisher", "story_id"),
        ("story.publisher", "story.id"),
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ("tag_type", "tag"),
        ("tag.type", "tag.name"),
        ondelete="CASCADE",
    ),
)

story_has_category_table = Table(
    "story_has_category",
    Base.metadata,
    Column("story_publisher", String(MAX_SITE_LENGTH), nullable=False),
    Column("story_id", Integer, nullable=False),
    Column("category_publisher", String(MAX_SITE_LENGTH) , nullable=False),
    Column("category_name", Unicode(MAX_CATEGORY_NAME_LENGTH)),
    ForeignKeyConstraint(
        ("story_publisher", "story_id"),
        ("story.publisher", "story.id"),
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ("category_publisher", "category_name"),
        ("category.publisher", "category.name"),
        ondelete="CASCADE",
    ),
)


class Author(UniqueMixin, Base):
    """
    This class represents an author in the database.
    """
    __tablename__ = "author"

    publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    name = Column(Unicode(MAX_AUTHOR_NAME_LENGTH), primary_key=True)
    url = Column(String(MAX_AUTHOR_URL_LENGTH))
    stories = relationship("Story", back_populates="author")

    @classmethod
    def unique_hash(cls, publisher, name, url):
        return (publisher, name)

    @classmethod
    def unique_filter(cls, query, publisher, name, url):
        return query.filter(
            Author.publisher == publisher,
            Author.name == name,
        )


class Category(UniqueMixin, Base):
    """
    This class represents a category in the database.
    """
    __tablename__ = "category"

    publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    name = Column(Unicode(MAX_CATEGORY_NAME_LENGTH), primary_key=True)
    stories = relationship("Story", secondary=story_has_category_table, back_populates="categories")

    @classmethod
    def unique_hash(cls, publisher, name):
        return (publisher, name)

    @classmethod
    def unique_filter(cls, query, publisher, name):
        return query.filter(
            Category.publisher == publisher,
            Category.name == name,
        )


class Tag(UniqueMixin, Base):
    """
    This class represents a tag in the database.

    It is also used for warnings and similiar information.
    """
    __tablename__ = "tag"

    type = Column(Unicode(MAX_TAG_TYPE_LENGTH), primary_key=True)
    name = Column(Unicode(MAX_STORY_TAG_LENGTH), primary_key=True)
    stories = relationship("Story", secondary=story_has_tag_table, back_populates="tags")

    @classmethod
    def unique_hash(cls, type, name):
        return (type, name)

    @classmethod
    def unique_filter(cls, query, type, name):
        return query.filter(
            Tag.type == type,
            Tag.name == name,
        )


class Series(UniqueMixin, Base):
    """
    This class represents a series of stories in the database.
    """
    __tablename__ = "series"

    publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    name = Column(Unicode(MAX_STORY_SERIES_LENGTH), primary_key=True)
    stories = relationship(
        "Story",
        back_populates="series",
        overlaps="stories",
    )

    @classmethod
    def unique_hash(cls, publisher, name):
        return (publisher, name)

    @classmethod
    def unique_filter(cls, query, publisher, name):
        return query.filter(
            Series.publisher == publisher,
            Series.name == name,
        )


class Story(Base):
    """
    This class represents a story in the database.
    """
    __tablename__ = "story"

    publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
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
    tags = relationship(
        "Tag",
        secondary=story_has_tag_table,
        back_populates="stories",
    )
    score = Column(Integer, autoincrement=False, default=0)
    num_comments = Column(Integer, autoincrement=False, default=0)
    series = relationship(
        "Series",
        back_populates="stories",
        cascade="all, delete",
        overlaps="stories",
    )
    series_name = Column(String(MAX_STORY_SERIES_LENGTH), nullable=True)
    series_index = Column(Integer, autoincrement=False, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            [publisher, author_name],
            [Author.publisher, Author.name],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [publisher, series_name],
            [Series.publisher, Series.name],
            ondelete="CASCADE",
        ),
    )

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
    def ordered_tags(self):
        """
        Return a list of all tags, ordered by type to match ao3.

        @return: an ordered list of all tags
        @rtype: L{list} of L{Tag}
        """
        return self.warnings + self.relationships + self.genres

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


class Chapter(Base):
    """
    This class represents a chapter in the database.
    """
    __tablename__ = "chapter"

    publisher = Column(String(MAX_SITE_LENGTH), primary_key=True)
    story_id = Column(Integer, primary_key=True, autoincrement=False)
    story = relationship(
        "Story",
        back_populates="chapters",
        foreign_keys="Chapter.story_id",
        cascade="all",
    )
    index = Column(Integer, primary_key=True, nullable=False, autoincrement=False)
    title = Column(Unicode(MAX_CHAPTER_TITLE_LENGTH), nullable=False)
    text = Column(UnicodeText(MAX_CHAPTER_TEXT_LENGTH), nullable=False)
    num_words = Column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            [publisher, story_id],
            [Story.publisher, Story.id],
            ondelete="CASCADE",
        ),
    )
