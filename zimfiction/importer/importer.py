"""
The actual import logic.
"""
import traceback

try:
    import multiprocessing
except:
    multiprocessing = None

from fs import open_fs
from fs.walk import Walker

from sqlalchemy import and_, exists

from .txtparser import parse_txt_story
from .epubparser import parse_epub_story
from .htmlparser import parse_html_story
from .jsonparser import parse_json_story
from ..exceptions import ParseError
from ..db.models import Story
from ..db.unique import clear_unique_cache
from ..util import chunked


def parse_story(fs, path, remove=False, ignore_errors=False, verbose=False):
    """
    Parse a story, returning the parsed raw story.

    @param fs: filesystem to import from
    @type fs: L{fs.base.Fs}
    @param path: path of story on fs to import
    @type path: L{str}
    @param remove: if nonzero, remove successfully imported fics
    @type remove: L{bool}
    @param ignore_errors: if nonzero, ignore errors
    @type ignore_errors: L{bool}
    @param verbose: if nonzero, be more verbose
    @type verbose: L{bool}
    @return: the parsed story or L{None} if the import failed
    @rtype: L{zimfiction.importer.raw.RawStory} or L{None}
    """
    use_encoding = path.split(".")[-1] in ("txt", "html", "json")
    open_kwargs = {}
    if use_encoding:
        open_kwargs["encoding"] = ("utf-8" if use_encoding else None)
        open_kwargs["errors"] = "replace"
    open_kwargs["mode"] = ("r" if use_encoding else "rb")
    with fs.open(path, **open_kwargs) as fin:
        try:
            if path.endswith(".txt"):
                raw = parse_txt_story(fin)
            elif path.endswith(".html"):
                raw = parse_html_story(fin)
            elif path.endswith(".epub"):
                raw = parse_epub_story(fin)
            elif path.endswith(".json"):
                raw = parse_json_story(fin)
            else:
                raise ValueError("Don't know how to parse '{}'!".format(path))
        except Exception as e:
            if verbose:
                print("\nException caught parsing {}:".format(path))
                traceback.print_exc()
            if not ignore_errors:
                raise ParseError("Error parsing: {}".format(path)) from e
            return None
        else:
            if remove:
                fs.remove(path)
        return raw


def _parse_map_helper(kwargs):
    """
    Wrapper around L{parse_story}, using a single dictionary providing the keyword arguments.

    This is a helper function to make it usable with map-like functions.
    Additionally, if "fs" is not set but "fs_url" is, the filesystem will
    be opened and the keyword arguments adjusted.

    @param kwargs: keyword-arguments to call L{parse_story} with
    @type kwargs: L{dict}
    @return: the result of L{parse_story}
    @rtype: L{zimfiction.importer.raw.RawStory}
    """
    new_kwargs = kwargs.copy()  # be nice and prevent modification of original dict
    if ("fs" not in new_kwargs) and ("fs_url" in new_kwargs):
        new_kwargs["fs"] = open_fs(new_kwargs["fs_url"])
        del new_kwargs["fs_url"]
    return parse_story(**new_kwargs)


def import_from_fs(fs_url, session, workers=0, ignore_errors=False, limit=None, force_publisher=None, remove=False, verbose=False):
    """
    Import all stories from a filesystem.

    @param fs_url: pyfilesystem2 URL of filesystem to import from
    @type fs_url: L{str}
    @param session: session to add stories to
    @type session: L{sqlalchemy.orm.Session}
    @param workers: if > 0, use this many workers to parallelize import
    @type workers: L{int}
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
    assert isinstance(workers, int) and (workers >= 0)
    fs = open_fs(fs_url)

    stories = []
    do_not_commit = []
    # as we are not directly flushing stories, we need to keep track of
    # all of the stories in the current batch to avoid duplicates.
    current_story_ids_to_stories = {}
    n_imported = 0

    if workers > 0:
        pool = multiprocessing.Pool()
        map_f = lambda f, l: pool.imap(f, l, chunksize=64)
    else:
        map_f = map

    walker = Walker(filter=["*.txt", "*.epub", "*.html", "*.json"])
    for pathgroup in chunked(walker.files(fs), n=2000):
        parse_args = [
            {
                "fs_url": fs_url,
                "path": path,
                "remove": remove,
                "ignore_errors": ignore_errors,
                "verbose": verbose,
            }
            for path in pathgroup
        ]
        raw_stories = map_f(_parse_map_helper, parse_args)
        raw_stories = filter(lambda x: x is not None, raw_stories)

        for raw in raw_stories:
            story = raw.to_story(session=session, force_publisher=force_publisher)
            full_story_id = (story.publisher.name, story.id)

            # check if session in story:
            with session.no_autoflush:
                # check if story already in database
                already_exists = (
                    session.query(
                        exists().
                        where(
                            and_(
                                Story.publisher.has(name=story.publisher.name),
                                Story.id == story.id,
                            )
                        )
                    ).scalar()
                )
                if already_exists:
                    # check if current story has more words than story in DB
                    n_new_words = sum([c.num_words for c in story.chapters])
                    n_old_words = session.query(
                        Story.total_words,
                    ).where(
                        and_(
                            Story.publisher.has(name=story.publisher.name),  # TODO: ensure this really works
                            Story.id == story.id,
                        )
                    ).scalar()
                    if n_new_words >= n_old_words:
                        if verbose:
                            print(
                                "Story {}-{} already exists in DB, replacing it...".format(
                                    story.publisher.name,
                                    story.id,
                                )
                            )
                        session.query(Story).filter(
                            and_(
                                Story.publisher.has(name=story.publisher.name),
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
                n_imported += 1
                current_story_ids_to_stories[full_story_id] = story
                if verbose:
                    print("Added story: ", story.title, end="   \r")
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
        if (limit is not None) and (n_imported >= limit):
            # imported stories up to max
            break

    if verbose:
        print("\nFinished importing from {}".format(fs))
