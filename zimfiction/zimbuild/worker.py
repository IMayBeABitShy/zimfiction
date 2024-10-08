"""
The worker logic for multi process rendering.

Workers receive their tasks from an inqueue fed from the builder. They
process the tasks by loading the required objects and feed them to a
renderer. The result is put into the outqueue, where the builder will
take the results and add them to the creator.

@var MARKER_WORKER_STOPPED: a symbolic constant put into the output queue when the worker is finished
@type MARKER_WORKER_STOPPED: L{str}
@var MARKER_TASK_COMPLETED: a symbolic constant put into the output queue when a task was completed
@type MARKER_TASK_COMPLETED: L{str}

@var MAX_STORY_EAGERLOAD: when loading tags and categories, do not eagerload if more than this number of stories are in said object
@type MAX_STORY_EAGERLOAD: L{int}
@var STORY_LIST_YIELD: number of story to fetch at once when rendering tags, categories, ...
@type STORY_LIST_YIELD: L{int}
"""
import contextlib
import os
import time

from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import Session, joinedload, subqueryload, selectinload, raiseload, undefer

try:
    import memray
except:
    memray = None

from .renderer import HtmlRenderer, RenderResult
from ..statistics import StoryListStatCreator
from ..util import ensure_iterable, normalize_tag
from ..db.models import Story, Chapter, Tag, Author, Category, Publisher
from ..db.models import StoryTagAssociation, StorySeriesAssociation, StoryCategoryAssociation, Series


MARKER_WORKER_STOPPED = "stopped"
MARKER_TASK_COMPLETED = "completed"

MAX_STORY_EAGERLOAD = 10000
STORY_LIST_YIELD = 2000


class Task(object):
    """
    Base class for all worker tasks.

    @cvar type: type of task
    @type type: L{str}
    """
    type = "<unset>"

    @property
    def name(self):
        """
        Return a non-unqiue id describing this task.

        @return: a name describing this task
        @rtype: L{str}
        """
        return "<unknown>"


class StopTask(Task):
    """
    Task indicating that the worker should shut down.
    """
    type = "stop"

    @property
    def name(self):
        return "stop"


class StoryRenderTask(Task):
    """
    A L{Task} for rendering stories.

    @ivar story_uids: ids of stories to render, as list of story uids
    @type story_uids: L{list} of L{int}
    """
    type = "story"

    def __init__(self, story_uids):
        """
        The default constructor.

        @param story_uids: ids of stories to render, as list of story uids
        @type story_uids: L{list} of L{int}
        """
        assert isinstance(story_uids, (list, tuple))
        assert isinstance(story_uids[0], int)
        self.story_uids = story_uids

    @property
    def name(self):
        if len(self.story_uids) == 0:
            return "stories_empty"
        return "stories_{}+{}".format(
            self.story_uids[0],
            len(self.story_uids) - 1,
        )


class TagRenderTask(Task):
    """
    A L{Task} for rendering tags.

    @ivar uid: uid of tag to render
    @type uid: L{int}
    """
    type = "tag"

    def __init__(self, uid):
        """
        The default constructor.

        @param uid: uid of tag to render
        @type uid: L{int}
        """
        assert isinstance(uid, int)
        self.uid = uid

    @property
    def name(self):
        return "tag_{}".format(self.uid)


class AuthorRenderTask(Task):
    """
    A L{Task} for rendering authors.

    @ivar uid: uid of author to render
    @type uid: L{int}
    """
    type = "author"

    def __init__(self, uid):
        """
        The default constructor.

        @param uid: uid of author to render
        @type uid: L{int}
        """
        assert isinstance(uid, int)
        self.uid = uid

    @property
    def name(self):
        return "author_{}".format(self.uid)


class CategoryRenderTask(Task):
    """
    A L{Task} for rendering categories.

    @ivar uid: uid of category to render
    @type uid: L{int}
    """
    type = "category"

    def __init__(self, uid):
        """
        The default constructor.

        @param uid: uid of category to render
        @type uid: L{int}
        """
        assert isinstance(uid, int)
        self.uid = uid

    @property
    def name(self):
        return "category_{}".format(self.uid)


class SeriesRenderTask(Task):
    """
    A L{Task} for rendering series.

    @ivar uid: uid of series to render
    @type uid: L{int}
    """
    type = "series"

    def __init__(self, uid):
        """
        The default constructor.

        @param uid: uid of series to render
        @type uid: L{int}
        """
        assert isinstance(uid, int)
        self.uid = uid

    @property
    def name(self):
        return "series_{}".format(self.uid)


class PublisherRenderTask(Task):
    """
    A L{Task} for rendering publishers.

    @ivar uid: uid of publisher to render
    @type uid: L{int}
    """
    type = "publisher"

    def __init__(self, uid):
        """
        The default constructor.

        @param uid: uid of publisher to render
        @type uid: L{int}
        """
        assert isinstance(uid, int)
        self.uid = uid

    @property
    def name(self):
        return "publisher_{}".format(self.uid)


class EtcRenderTask(Task):
    """
    A L{Task} for rendering specific, individual pages.

    @ivar subtask: the name of the subtask to perform (e.g. index)
    @type subtask: L{str}
    """
    type = "etc"

    def __init__(self, subtask):
        """
        The default constructor.

        @param subtask: name of the subtask to perform
        @type subtask: L{str}
        """
        assert isinstance(subtask, str)
        self.subtask = subtask

    @property
    def name(self):
        return "etc_{}".format(self.subtask)


class WorkerOptions(object):
    """
    Options for the worker.

    @ivar log_directory: if not None, enable logging and write log here
    @type log_directory: L{str} or L{None}
    @ivar memprofile_directory: if not None, profile memory usage and write files into this directory
    @type memprofile_directory: L{str} or L{None}
    """
    def __init__(self, log_directory=None, memprofile_directory=None):
        """
        The default constructor.

        @param log_directory: if specified, enable logging and write log here
        @type log_directory: L{str} or L{None}
        @param memprofile_directory: if specified, profile memory usage and write files into this directory
        @type memprofile_directory: L{str} or L{None}
        """
        assert isinstance(log_directory, str) or (log_directory is None)
        assert isinstance(memprofile_directory, str) or (memprofile_directory is None)
        self.log_directory = log_directory
        self.memprofile_directory = memprofile_directory


class Worker(object):
    """
    The worker should be instantiated in a new process, where it will
    continuously process tasks from the main process.

    @ivar id: id of this worker
    @type id: L{int}
    @ivar inqueue: the queue providing new tasks
    @type inqueue: L{multiprocessing.Queue}
    @ivar outqueue: the queue where results will be put
    @type outqueue: L{multiprocessing.Queue}
    @ivar renderer: the renderer used to render the content
    @type renderer: L{zimfiction.zimbuild.renderer.HtmlRenderer}
    @ivar engine: engine used for database connection
    @type engine: L{sqlalchemy.engine.Engine}
    @ivar session: database session
    @type session: L{sqlalchemy.orm.Session}
    @ivar options: options for this worker
    @type options: L{WorkerOptions}

    @ivar _log_file: file used for logging
    @type _log_file: file-like object
    @ivar _last_log_time: timestamp of last log entry
    @ivar _last_log_time: L{int}
    """
    def __init__(self, id, inqueue, outqueue, engine, options, render_options):
        """
        The default constructor.

        @param id: id of this worker
        @type id: L{int}
        @param inqueue: the queue providing new tasks
        @type inqueue: L{multiprocessing.Queue}
        @param outqueue: the queue where results will be put
        @type outqueue: L{multiprocessing.Queue}
        @param engine: engine used for database connection. Be sure to dispose the connection pool first!
        @type engine: L{sqlalchemy.engine.Engine}
        @param options: options for the worrker
        @type options: L{WorkerOptions}
        @param render_options: options for the renderer
        @type render_options: L{zimfiction.zimbuild.renderer.RenderOptions}
        """
        assert isinstance(id, int)
        self.id = id
        self.inqueue = inqueue
        self.outqueue = outqueue
        self.engine = engine

        self.session = Session(engine)
        self.options = options
        self.renderer = HtmlRenderer(options=render_options)

        self.setup_logging()

        self.log("Worker initialized.")

    def setup_logging(self):
        """
        Setup the logging system.
        """
        self._last_log_time = time.time()
        if self.options.log_directory is not None:
            fn = os.path.join(
                self.options.log_directory,
                "log_worker_{}.txt".format(self.id),
            )
            self._log_file = open(fn, mode="w", encoding="utf-8")
        else:
            self._log_file = None

    def log(self, msg):
        """
        Log a message.

        @param msg: message to log
        @type msg: L{str}
        """
        assert isinstance(msg, str)
        if self._log_file is not None:
            full_msg = "[{}][+{:8.3f}s] {}\n".format(
                time.ctime(),
                time.time() - self._last_log_time,
                msg,
            )
            self._log_file.write(full_msg)
            self._log_file.flush()
        self._last_log_time = time.time()

    def run(self):
        """
        Run the worker.

        This does not start a new process, the worker should already
        have been instantiated in a new process.

        This method will run in a loop, taking new tasks from the inqueue,
        processing them and putting the results in the outqueue until a
        L{StopTask} has been received. Upon completion,
        L{MARKER_WORKER_FINISHED} will be put on the outqueue once.
        Additionally, L{MARKER_TASK_COMPLETED} is put in the queue
        after each task.
        """
        self.log("Entering mainloop.")
        running = True
        while running:
            task = self.inqueue.get(block=True)
            self.log("Received task '{}'".format(task.name))
            with self.get_task_processing_context(task=task):
                if task.type == "stop":
                    # stop the worker
                    self.log("Stopping worker...")
                    running = False
                    self._cleanup()
                elif task.type == "story":
                    self.process_story_task(task)
                elif task.type == "tag":
                    self.process_tag_task(task)
                elif task.type == "author":
                    self.process_author_task(task)
                elif task.type == "category":
                    self.process_category_task(task)
                elif task.type == "series":
                    self.process_series_task(task)
                elif task.type == "publisher":
                    self.process_publisher_task(task)
                elif task.type == "etc":
                    self.process_etc_task(task)
                else:
                    raise ValueError("Task {} has an unknown task type '{}'!".format(repr(task), task.type))
                if task.type != "stop":
                    # notify builder that a task was completed
                    self.log("Marking task as completed.")
                    self.outqueue.put(MARKER_TASK_COMPLETED)
        # send a message indicated that this worker has finished
        self.outqueue.put(MARKER_WORKER_STOPPED)
        self.log("Worker finished.")

    def _cleanup(self):
        """
        Called before the worker finishes.

        All cleanup (e.g. closing sessions) should happen here.
        """
        self.session.close()
        self.engine.dispose()

    def handle_result(self, result):
        """
        Handle a renderer result, putting it in the outqueue.

        @param result: result to handle
        @type result: L{zimfiction.zimbuild.renderer.RenderResult} or iterable of it
        """
        it = ensure_iterable(result)
        for i, subresult in enumerate(it):
            self.log("Submitting result part {}...".format(i))
            self.outqueue.put(subresult)

    def get_task_processing_context(self, task):
        """
        Return A context manager that runs while a task is being processed.

        @param task: task the context is for
        @type task: Task
        @return: context manager to use
        @rtype: a context manager
        """
        if self.options.memprofile_directory is not None:
            if memray is None:
                raise ImportError("Could not import package 'memray' required for memory profiling!")
            file_name = os.path.join(
                self.options.memprofile_directory,
                "mp_{}_{}.bin".format(self.id, normalize_tag(task.name))
            )
            return memray.Tracker(
                destination=memray.FileDestination(
                    path=file_name,
                    overwrite=True,
                    compress_on_exit=False,
                ),
                native_traces=False,
                trace_python_allocators=False,
                follow_fork=False,  # already in fork
            )
        else:
            return contextlib.nullcontext()

    def process_story_task(self, task):
        """
        Process a received story task.

        @param task: task to process
        @type task: L{StoryRenderTask}
        """
        for story_uid in task.story_uids:
            # get the story
            self.log("Retrieving story...")
            story = self.session.scalars(
                select(Story)
                .where(Story.uid == story_uid)
                .options(
                    # eager loading options
                    # as it turns out, lazyloading is simply the fastest... This seems wrong...
                    joinedload(Story.chapters).undefer(Chapter.text),
                    # selectinload(Story.tags),
                    joinedload(Story.author),
                    joinedload(Story.series_associations),
                    joinedload(Story.series_associations, StorySeriesAssociation.series),
                    subqueryload(Story.category_associations),
                    subqueryload(Story.category_associations, StoryCategoryAssociation.category),
                )
            ).first()
            self.log("Retrieved story, rendering...")
            result = self.renderer.render_story(story)
            self.log("Rendered story, submitting result...")
            self.handle_result(result)
            self.log("Done.")

    def process_tag_task(self, task):
        """
        Process a received tag task.

        @param task: task to process
        @type task: L{TagRenderTask}
        """
        # count stories in tag
        self.log("Counting non-implied stories in tag...")
        count_stmt = (
            select(func.count(StoryTagAssociation.story_uid))
            .where(
                StoryTagAssociation.tag_uid == task.uid,
                StoryTagAssociation.implied == False,
            )
        )
        n_stories_in_tag = self.session.execute(count_stmt).scalar_one()
        self.log("Found {} stories.".format(n_stories_in_tag))
        # load tag
        self.log("Loading tag...")
        tag_stmt = (
            select(Tag)
            .where(
                Tag.uid == task.uid,
            )
            .options(
                raiseload(Tag.story_associations),
            )
        )
        tag = self.session.scalars(tag_stmt).first()
        self.log("Tag loaded.")
        if tag is None:
            self.log("-> Tag not found!")
            self.log("Submitting empty result...")
            result = RenderResult()
            self.handle_result(result)
            self.log("Done.")
            return

        # load non-implied stories
        self.log("Starting to load stories...")
        story_stmt = (
            select(Story)
            .join(
                StoryTagAssociation,
                and_(
                    StoryTagAssociation.story_uid == Story.uid,
                    StoryTagAssociation.tag_uid == task.uid,
                    StoryTagAssociation.implied == False,
                )
            )
            .order_by(desc(Story.score), desc(Story.total_words))
            .options(
                selectinload(Story.chapters),
                undefer(Story.summary),
            )
            .execution_options(
                yield_per=STORY_LIST_YIELD,
            )
        )
        stories = self.session.scalars(story_stmt)
        self.log("Rendering tag...")
        result = self.renderer.render_tag(
            tag=tag,
            stories=stories,
            num_stories=n_stories_in_tag,
        )
        self.log("Submitting result...")
        self.handle_result(result)
        self.log("Done.")

    def process_author_task(self, task):
        """
        Process a received author task.

        @param task: task to process
        @type task: L{AuthorRenderTask}
        """
        # get the author
        self.log("Retrieving author...")
        author = self.session.scalars(
            select(Author)
            .where(Author.uid == task.uid)
            .options(
                # eager loading options
                joinedload(Author.stories).undefer(Story.summary),
            )
        ).first()
        self.log("Rendering author...")
        result = self.renderer.render_author(author)
        self.log("Submitting result...")
        self.handle_result(result)
        self.log("Done.")

    def process_category_task(self, task):
        """
        Process a received category task.

        @param task: task to process
        @type task: L{CategoryRenderTask}
        """
        # count stories in category
        self.log("Counting non-implied stories in category...")
        count_stmt = (
            select(func.count(StoryCategoryAssociation.story_uid))
            .where(
                StoryCategoryAssociation.category_uid == task.uid,
                StoryCategoryAssociation.implied == False,
            )
        )
        n_stories_in_category = self.session.execute(count_stmt).scalar_one()
        self.log("Found {} stories.".format(n_stories_in_category))
        # load category
        self.log("Loading category...")
        category_stmt = (
            select(Category)
            .where(
                Category.uid == task.uid,
            )
            .options(
                raiseload(Category.story_associations),
            )
        )
        category = self.session.scalars(category_stmt).first()
        self.log("Category loaded.")
        if category is None:
            self.log("-> Category not found!")
            self.log("Submitting empty result...")
            result = RenderResult()
            self.handle_result(result)
            self.log("Done.")
            return

        # load non-implied stories
        self.log("Starting to load stories...")
        story_stmt = (
            select(Story)
            .join(
                StoryCategoryAssociation,
                and_(
                    StoryCategoryAssociation.story_uid == Story.uid,
                    StoryCategoryAssociation.category_uid == task.uid,
                    StoryCategoryAssociation.implied == False,
                )
            )
            .order_by(desc(Story.score), desc(Story.total_words))
            .options(
                selectinload(Story.chapters),
                undefer(Story.summary),
            )
            .execution_options(
                yield_per=STORY_LIST_YIELD,
            )
        )
        stories = self.session.scalars(story_stmt)
        self.log("Rendering category...")
        result = self.renderer.render_category(
            category=category,
            stories=stories,
            num_stories=n_stories_in_category,
        )
        self.log("Submitting result...")
        self.handle_result(result)
        self.log("Done.")

    def process_series_task(self, task):
        """
        Process a received series task.

        @param task: task to process
        @type task: L{SeriesRenderTask}
        """
        # get the series
        self.log("Retrieving series...")
        series = self.session.scalars(
            select(Series)
            .where(Series.uid == task.uid)
            .options(
                # eager loading options
                joinedload(Series.story_associations),
                joinedload(Series.story_associations, StorySeriesAssociation.story).undefer(Story.summary),
            )
        ).first()
        self.log("Rendering series...")
        result = self.renderer.render_series(series)
        self.log("Submitting result...")
        self.handle_result(result)
        self.log("Done.")

    def process_publisher_task(self, task):
        """
        Process a received publisher task.

        @param task: task to process
        @type task: L{PublisherRenderTask}
        """
        # get the categories in the series
        self.log("Retrieving publisher...")
        publisher = self.session.scalars(
            select(Publisher)
            .where(Publisher.uid == task.uid)
            .options(
                # eager loading options
                joinedload(Publisher.categories),
                joinedload(Publisher.categories, Category.story_associations),
                joinedload(Publisher.categories, Category.story_associations, StoryCategoryAssociation.story),
            )
        ).first()
        self.log("Rendering publisher...")
        result = self.renderer.render_publisher(
            publisher=publisher,
        )
        self.log("Submitting result...")
        self.handle_result(result)
        self.log("Done.")

    def process_etc_task(self, task):
        """
        Process a received etc task.

        @param task: task to process
        @type task: L{PublisherRenderTask}
        """
        if task.subtask == "index":
            # render the indexpage
            self.log("Retrieving publishers...")
            publishers = self.session.scalars(
                select(Publisher)
                .options(
                    # eager loading options
                    subqueryload(Publisher.categories),
                    # joinedload(Publisher.categories, Category.stories),
                    raiseload(Publisher.categories, Category.story_associations),
                )
            ).all()
            self.log("Rendering index page...")
            result = self.renderer.render_index(publishers=publishers)
        elif task.subtask == "stats":
            # render the global statistics
            self.log("Retrieving stories...")
            stories = self.session.scalars(
                select(Story)
                .options(
                    # eager loading options
                    # as it turns out, lazyloading is simply the fastest... This seems wrong...
                    selectinload(Story.chapters),
                    joinedload(Story.author),
                    selectinload(Story.series_associations),
                    joinedload(Story.series_associations, StorySeriesAssociation.series),
                    selectinload(Story.category_associations),
                    joinedload(Story.category_associations, StoryCategoryAssociation.category),
                    selectinload(Story.tag_associations),
                    joinedload(Story.tag_associations, StoryTagAssociation.tag),
                ).execution_options(
                    yield_per=STORY_LIST_YIELD,
                )
            ).all()
            self.log("Generating stats...")
            stats = StoryListStatCreator.get_stats_from_iterable(stories)
            self.log("Rendering statistics...")
            result = self.renderer.render_global_stats(stats)
        elif task.subtask == "search":
            # The search script
            self.log("Rendering search script...")
            result = self.renderer.render_search_script()
        elif task.subtask == "chartscripts":
            # the chart.js script
            self.log("Including chart.js script...")
            result = self.renderer.render_chart_scripts()
        elif task.subtask == "info":
            # the info pages
            self.log("Rendering info pages...")
            result = self.renderer.render_info_pages()
        else:
            raise ValueError("Unknown etc subtask: '{}'!".format(task.subtask))
        self.log("Submitting result...")
        self.handle_result(result)
        self.log("Done.")
