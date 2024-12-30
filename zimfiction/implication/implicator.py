"""
This module contains the L{Implicator}, which manages the implication detection.
"""
from sqlalchemy import select, delete
from sqlalchemy.orm import undefer, selectinload, joinedload, raiseload

from ..db.models import Story, StoryCategoryAssociation, StoryTagAssociation, Tag, Publisher, Category
from ..db.models import  MAX_STORY_TAG_LENGTH, MAX_CATEGORY_NAME_LENGTH
from ..reporter import BaseReporter, VoidReporter
from ..zimbuild.buckets import BucketMaker
from ..util import normalize_category, normalize_relationship

from .finder import ImplicationFinder
from .relationships import RelationshipCharactersFinder
from .ao3dumpfinder import Ao3MergerFinder
from .exclamationtagfinder import ExclamationTagFinder


STORIES_PER_QUERY = 1000


class Implicator(object):
    """
    The Implicator manages the implication detection.

    @ivar finders: list of implication finders to use
    @type finders: L{list} of L{zimfiction.implication.finder.ImplicationFinder}
    @ivar session: session to add stories to
    @type session: L{sqlalchemy.orm.Session}

    @ivar n_tags_implied: number of tag implications found
    @type n_tags_implied: L{int}
    @ivar n_categories_implied: number of category implications found
    @type n_categories_implied: L{int}
    """
    def __init__(self, session, finders=None):
        """
        The default construcotr.

        @param session: session to add stories to
        @type session: L{sqlalchemy.orm.Session}
        @param finders: list of implication finders to use
        @type finders: L{None} or L{list} of L{zimfiction.implication.finder.ImplicationFinder}
        """
        self.session = session
        if finders is None:
            finders = []
        self.finders = finders

        self.n_tags_implied = 0
        self.n_categories_implied = 0

    def add_finder(self, finder):
        """
        Add an implication finder, so that it will be used from now on.

        @param finder: implication finder to use
        @type finder: L{zimfiction.implication.finder.ImplicationFinder}
        """
        assert isinstance(finder, ImplicationFinder)
        self.finders.append(finder)

    def delete_implications(self):
        """
        Delete existing implications.
        """
        # tags
        stmt = (
            delete(StoryTagAssociation)
            .where(StoryTagAssociation.implied == True)
        )
        self.session.execute(stmt)
        # categories
        stmt = (
            delete(StoryCategoryAssociation)
            .where(StoryCategoryAssociation.implied == True)
        )
        self.session.execute(stmt)

    def process(self, story):
        """
        Process a story, modifying the story.

        Don't forget to add and commit changes.

        @param story: story to process
        @type story: L{zimfiction.db.models.Story}
        """
        existing_tags = [(t.type, t.name) for t in story.tags]
        existing_categories = [(c.publisher.name, c.name) for c in story.categories]
        new_tags = []
        new_categories = []

        # find implied tags and categories
        for finder in self.finders:
            for tagdef in finder.get_implied_tags(story, new_tags):
                if len(tagdef[1]) > MAX_STORY_TAG_LENGTH:
                    # tag to long, probably a bug in the implication finder
                    # TODO: some warning
                    continue
                if tagdef[0] == "relationship":
                    tagdef = (taged[0], normalize_relationship(tagdef[1]))
                if (tagdef not in existing_tags) and (tagdef not in new_tags):
                    new_tags.append(tagdef)
            for catdef in finder.get_implied_categories(story, new_categories):
                if len(catdef[1]) > MAX_CATEGORY_NAME_LENGTH:
                    # category to long, probably a bug in the implication finder
                    # TODO: some warning
                    continue
                catdef = (catdef[0], normalize_category(catdef[1]))
                if (catdef not in existing_categories) and (catdef not in new_categories):
                    new_categories.append(catdef)

        # add implied tags
        tag_i = len(story.tag_associations)
        for tagtype, tagname in new_tags:
            story.tag_associations.append(
                StoryTagAssociation(
                    Tag.as_unique(self.session, type=tagtype, name=tagname),
                    index=tag_i,
                    implied=True,
                ),
            )
            self.n_tags_implied += 1
            tag_i += 1
        # add implied categories
        for (publisher_name, category_name) in new_categories:
            publisher = Publisher.as_unique(self.session, name=publisher_name.strip())
            story.category_associations.append(
                StoryCategoryAssociation(
                    Category.as_unique(self.session, publisher=publisher, name=category_name),
                    implied=True,
                ),
            )
            self.n_categories_implied += 1


def get_default_implicator(session, ao3_merger_path=None):
    """
    Return a L{Implicator} configured to use the default L{zimfiction.implication.finder.ImplicationFinder} implementations.

    @ivar session: session to add stories to
    @type session: L{sqlalchemy.orm.Session}
    @param ao3_merger_path: if specified, a path to a CSV dump of ao3 tag info
    @type ao3_merger_path: L{str} or L{None}
    @return: an implicator which uses a choosen set of implication finders
    @rtype: L{Implicator}
    """
    finders = []
    finders.append(ExclamationTagFinder())
    finders.append(RelationshipCharactersFinder())
    if ao3_merger_path is not None:
        finders.append(Ao3MergerFinder(ao3_merger_path))
    implicator = Implicator(
        session,
        finders=finders,
    )
    return implicator


def add_all_implications(session, implicator, eager=True, reporter=None):
    """
    Find and add all implications for all stories in the database.

    @param session: session used to interact with the db
    @type session: L{sqlalchemy.orm.Session}
    @param implicator: implicator to use
    @type implicator: L{Implicator}
    @param eager: eager load stories
    @type eager: L{bool}
    @param reporter: reporter to use for progress report
    @type reporter: L{zimfiction.reporter.BaseReporter}
    """
    assert isinstance(implicator, Implicator)
    assert isinstance(reporter, BaseReporter)
    if reporter is None:
        reporter = VoidReporter()

    # find story ids
    reporter.msg("Loading story ids... ", end="")
    uid_bucket_maker = BucketMaker(maxsize=STORIES_PER_QUERY)
    select_story_uids_stmt = select(Story.uid)
    result = session.execute(select_story_uids_stmt)
    n_stories = 0
    story_uid_groups = []
    for story in result:
        n_stories += 1
        bucket = uid_bucket_maker.feed(story.uid)
        if bucket is not None:
            story_uid_groups.append(bucket)
    bucket = uid_bucket_maker.finish()
    if bucket is not None:
        story_uid_groups.append(bucket)
    reporter.msg("Done.")

    # setup eager loading options
    if eager:
        options = (
            undefer(Story.summary),
            # selectinload(Story.chapters),
            # joinedload(Story.author),
            # selectinload(Story.series_associations),
            # joinedload(Story.series_associations, StorySeriesAssociation.series),
            selectinload(Story.tag_associations),
            joinedload(Story.tag_associations, StoryTagAssociation.tag),
            raiseload(Story.tag_associations, StoryTagAssociation.tag, Tag.story_associations),
            selectinload(Story.category_associations),
            joinedload(Story.category_associations, StoryCategoryAssociation.category),
            raiseload(Story.category_associations, StoryCategoryAssociation.category, Category.story_associations),
        )
    else:
        options = (
            undefer(Story.summary),
        )

    # process stories
    with reporter.with_progress("Finding implications... ", max=n_stories, unit="stories") as bar:
        for story_uid_group in story_uid_groups:
            # load stories group-wise
            stories = session.scalars(
                select(Story)
                .where(Story.uid.in_(story_uid_group))
                .options(
                    *options,
                )
            ).all()
            # feed stories to the implicator
            for story in stories:
                implicator.process(story)
                session.add(story)
                bar.advance(1)
            session.commit()
    reporter.msg("Done.")
