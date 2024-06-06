"""
This module contains the L{Implicator}, which manages the implication detection.
"""
from sqlalchemy import select, func
from sqlalchemy.orm import subqueryload

from ..db.models import Story, StoryCategoryAssociation, StoryTagAssociation, Tag, Publisher, Category
from ..reporter import BaseReporter, VoidReporter

from .finder import ImplicationFinder
from .relationships import RelationshipCharactersFinder


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

    def process(self, story):
        """
        Process a story, modifying the story.

        Don't forget to add and commit changes.

        @param story: story to process
        @type story: L{zimfiction.db.models.Story}
        """
        existing_tags = [(t.type, t.name) for t in story.tags]
        existing_categories = [(c.publisher_name, c.name) for c in story.categories]
        new_tags = []
        new_categories = []

        # find implied tags and categories
        for finder in self.finders:
            for tagdef in finder.get_implied_tags(story, new_tags):
                if (tagdef not in existing_tags) and (tagdef not in new_tags):
                    new_tags.append(tagdef)
            for catdef in finder.get_implied_categories(story, new_categories):
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


def get_default_implicator(session):
    """
    Return a L{Implicator} configured to use the default L{zimfiction.implication.finder.ImplicationFinder} implementations.

    @ivar session: session to add stories to
    @type session: L{sqlalchemy.orm.Session}
    @return: an implicator which uses a choosen set of implication finders
    @rtype: L{Implicator}
    """
    implicator = Implicator(
        session,
        finders=[
            RelationshipCharactersFinder(),
        ],
    )
    return implicator


def add_all_implications(session, implicator, reporter=None):
    """
    Find and add all implications for all stories in the database.

    @ivar session: session used to interact with the db
    @type session: L{sqlalchemy.orm.Session}
    @param implicator: implicator to use
    @type implicator: L{Implicator}
    @param reporter: reporter to use for progress report
    @type reporter: L{zimfiction.reporter.BaseReporter}
    """
    assert isinstance(implicator, Implicator)
    assert isinstance(reporter, BaseReporter)
    if reporter is None:
        reporter = VoidReporter()

    # find amount of stories
    n_stories = session.execute(
        select(func.count(Story.id))
    ).scalar_one()
    # find stories
    stories = session.scalars(
        select(Story)
        .options(
            # eager loading options
            # as it turns out, lazyloading is simply the fastest... This seems wrong...
            subqueryload(Story.category_associations),
            subqueryload(Story.category_associations, StoryCategoryAssociation.category),
        )
    ).all()
    # feed stories into implicator and commit them
    with reporter.with_progress("Finding implications... ", max=n_stories, unit="stories") as bar:
        for i, story in enumerate(stories):
            implicator.process(story)
            session.add(story)
            if i % 1000 == 0:
                session.commit()
            bar.advance(1)
        session.commit()
