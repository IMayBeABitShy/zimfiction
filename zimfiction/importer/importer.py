"""
The actual import logic.
"""
import traceback

from fs.walk import Walker

from sqlalchemy import and_, exists
from sqlalchemy.sql import func

from .txtparser import parse_txt_story
from .epubparser import parse_epub_story
from .htmlparser import parse_html_story
from .jsonparser import parse_json_story
from ..exceptions import ParseError
from ..db.models import Story, Chapter
from ..db.unique import clear_unique_cache


def import_from_fs(fs, session, ignore_errors=False, limit=None, force_publisher=None, remove=False, verbose=False):
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
    @param force_publisher: if not None, force all stories imported to have this publisher
    @type force_publisher: L{str} or L{None}
    @param remove: if nonzero, remove imported fics
    @type remove: L{bool}
    @param verbose: if nonzero, be more verbose
    @type verbose: L{bool}
    """
    assert (limit is None) or (isinstance(limit, int) and limit >= 1)
    stories = []
    do_not_commit = []
    # as we are not directly flushing stories, we need to keep track of
    # all of the stories in the current batch to avoid duplicates.
    current_story_ids_to_stories = {}

    walker = Walker(filter=["*.txt", "*.epub", "*.html", "*.json"])
    for i, path in enumerate(walker.files(fs)):
        use_encoding = path.split(".")[-1] in ("txt", "html", "json")
        open_kwargs = {}
        if use_encoding:
            open_kwargs["encoding"] = ("utf-8" if use_encoding else None)
            open_kwargs["errors"] = "replace"
        open_kwargs["mode"] = ("r" if use_encoding else "rb")
        with fs.open(path, **open_kwargs) as fin:
            try:
                if path.endswith(".txt"):
                    story = parse_txt_story(session, fin, force_publisher=force_publisher)
                elif path.endswith(".html"):
                    story = parse_html_story(session, fin, force_publisher=force_publisher)
                elif path.endswith(".epub"):
                    story = parse_epub_story(session, fin, force_publisher=force_publisher)
                elif path.endswith(".json"):
                    story = parse_json_story(session, fin, force_publisher=force_publisher)
                else:
                    raise ValueError("Don't know how to parse '{}'!".format(path))
            except Exception as e:
                if verbose:
                    print("\nException caught parsing {}:".format(path))
                    traceback.print_exc()
                if ignore_errors:
                    continue
                raise ParseError("Error parsing: {}".format(path)) from e
        if remove:
            fs.remove(path)

        full_story_id = (story.publisher.name, story.id)

        # check if session in story:
        with session.no_autoflush:
            # check if story already in database
            already_exists = (
                session.query(
                    exists().
                    where(
                        and_(
                            Story.publisher_name == story.publisher.name,
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
                        Chapter.publisher_name == story.publisher.name,
                        Chapter.story_id == story.id,
                    )
                ).scalar()
                if n_new_words > n_old_words:
                    if verbose:
                        print(
                            "Story {}-{} already exists in DB, replacing it...".format(
                                story.publisher.name,
                                story.id,
                            )
                        )
                    session.query(Story).filter(
                        and_(
                            Story.publisher_name == story.publisher.name,
                            Story.id == story.id,
                        )
                    ).delete()
                else:
                    if verbose:
                        print(
                            "Story {}-{} already exists in DB and has more words, not replacing it...".format(
                                story.publisher.name,
                                story.id,
                            )
                        )
                    do_not_commit.append(story)
                    continue
            elif full_story_id in current_story_ids_to_stories:
                n_new_words = sum([c.num_words for c in story.chapters])
                old_story = current_story_ids_to_stories[full_story_id]
                n_old_words = sum([c.num_words for c in old_story.chapters])
                if n_new_words < n_old_words:
                    # do not replace old story
                    print(
                        "Story {}-{} already staged for commit and has more words, not replacing it...".format(
                            story.publisher.name,
                            story.id,
                        )
                    )
                    do_not_commit.append(story)
                    continue
                else:
                    stories.remove(old_story)
                    do_not_commit.append(old_story)
            stories.append(story)
            current_story_ids_to_stories[full_story_id] = story
            if verbose:
                print("Added story: ", story.title, end="   \r")
            if i % 1000 == 0 and i > 0:
            # if i % 5 == 1 and i > 0 and stories:
            #  if i % 1 == 0 and i > 0 and stories:
                if verbose:
                    print("Committing {} stories...".format(len(stories)), end="   \r")
                session.expunge_all()
                session.add_all(stories)
                for story in do_not_commit:
                    story.remove_from_related()
                    try:
                        session.expunge(story)
                    except Exception:
                        pass
                do_not_commit = []
                session.commit()
                stories = []
                current_story_ids_to_stories = {}
                clear_unique_cache(session)
            if (limit is not None) and (i >= limit):
                # imported stories up to max
                break

    session.expunge_all()
    session.add_all(stories)
    for story in do_not_commit:
        story.remove_from_related()
        try:
            session.expunge(story)
        except Exception:
            pass
    do_not_commit = []
    session.commit()
    stories = []
    clear_unique_cache(session)
    if verbose:
        print("\nFinished importing from {}".format(fs))
