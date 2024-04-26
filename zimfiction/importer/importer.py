"""
The actual import logic.
"""
import traceback

from fs.walk import Walker

from sqlalchemy import and_, exists
from sqlalchemy.sql import func

from .parser import parse_story
from ..exceptions import ParseError
from ..db.models import Story, Chapter
from ..db.unique import clear_unique_cache


def import_from_fs(fs, session, ignore_errors=False, limit=None, verbose=False):
    """
    Import all stories from a filesystem.

    @param fs: filesystem to import from
    @type fs: L{fs.base.Fs}
    @param session: session to add stories to
    @type session: L{sqlalchemy.orm.Session}
    @param ignore_errors: if nonzero, ignore errors
    @type ignore_errors: L{bool}
    @param limit: if specified, import at most this many stories
    @type limit: L{int} or L{None}
    @param verbose: if nonzero, be more verbose
    @type verbose: L{bool}
    """
    assert (limit is None) or (isinstance(limit, int) and limit >= 1)
    stories = []
    # as we are not directly flushing stories, we need to keep track of
    # all of the stories in the current batch to avoid duplicates.
    current_story_ids_to_stories = {}

    walker = Walker(filter=["*.txt"])
    for i, path in enumerate(walker.files(fs)):
        with fs.open(path, "r", encoding="utf-8", errors="replace") as fin:
            try:
                story = parse_story(session, fin)
            except Exception as e:
                if verbose:
                    print("\nException caught parsing {}:".format(path))
                    traceback.print_exc()
                if ignore_errors:
                    continue
                raise ParseError("Error parsing: {}".format(path)) from e

            full_story_id = (story.publisher, story.id)

            # check if session in story:
            with session.no_autoflush:
                # check if story already in database
                already_exists = (
                    session.query(
                        exists().
                        where(
                            and_(
                                Story.publisher == story.publisher,
                                Story.id == story.id,
                            )
                        )
                    ).scalar()
                )
                if already_exists:
                    # check if current story has more words than story in DB
                    n_new_words = sum([c.num_words for c in story.chapters])
                    n_old_words = session.query(
                        func.sum(Chapter.num_words),
                    ).where(
                        and_(
                            Chapter.publisher == story.publisher,
                            Chapter.story_id == story.id,
                        )
                    ).scalar()
                    if n_new_words > n_old_words:
                        if verbose:
                            print(
                                "Story {}-{} already exists in DB, replacing it...".format(
                                    story.publisher,
                                    story.id,
                                )
                            )
                        session.query(Story).filter(
                            and_(
                                Story.publisher == story.publisher,
                                Story.id == story.id,
                            )
                        ).delete()
                    else:
                        if verbose:
                            print(
                                "Story {}-{} already exists in DB and has more words, not replacing it...".format(
                                    story.publisher,
                                    story.id,
                                )
                            )
                        continue
                elif full_story_id in current_story_ids_to_stories:
                    n_new_words = sum([c.num_words for c in story.chapters])
                    old_story = current_story_ids_to_stories[full_story_id]
                    n_old_words = sum([c.num_words for c in old_story.chapters])
                    if n_new_words < n_old_words:
                        # do not replace old story
                        print(
                            "Story {}-{} already staged for commit and has more words, not replacing it...".format(
                                story.publisher,
                                story.id,
                            )
                        )
                        continue
                    else:
                        stories.remove(old_story)
            stories.append(story)
            current_story_ids_to_stories[full_story_id] = story
            if verbose:
                print("Added story: ", story.title, end="   \r")
            #  if i % 10000 == 0 and i > 0 and stories:
            if i % 20 == 1 and i > 0 and stories:
                if verbose:
                    print("Committing {} stories...".format(len(stories)), end="   \r")
                session.expunge_all()
                session.add_all(stories)
                session.commit()
                stories = []
                current_story_ids_to_stories = {}
                clear_unique_cache(session)
            if (limit is not None) and (i >= limit):
                # imported stories up to max
                break

    session.expunge_all()
    session.add_all(stories)
    session.commit()
    stories = []
    clear_unique_cache(session)
    if verbose:
        print("\nFinished importing from {}".format(fs))
