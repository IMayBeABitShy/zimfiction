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
"""
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session, joinedload, subqueryload, selectinload, raiseload, lazyload, contains_eager, undefer

from .renderer import HtmlRenderer, RenderResult
from ..statistics import StoryListStatCreator
from ..util import ensure_iterable
from ..db.models import Story, Chapter, Tag, Author, Category, Publisher
from ..db.models import StoryTagAssociation, StorySeriesAssociation, StoryCategoryAssociation, Series


MARKER_WORKER_STOPPED = "stopped"
MARKER_TASK_COMPLETED = "completed"

MAX_STORY_EAGERLOAD = 4000


class Task(object):
    """
    Base class for all worker tasks.

    @cvar type: type of task
    @type type: L{str}
    """
    type = "<unset>"


class StopTask(Task):
    """
    Task indicating that the worker should shut down.
    """
    type = "stop"


class StoryRenderTask(Task):
    """
    A L{Task} for rendering stories.

    @ivar story_ids: ids of stories to render, as list of tuples of (publisher, id)
    @type story_ids: L{list} of L{tuple} of (L{str}, L{int})
    """
    type = "story"

    def __init__(self, story_ids):
        """
        The default constructor.

        @param story_ids: ids of stories to render, as list of tuples of (publisher, id)
        @type story_ids: L{list} of L{tuple} of (L{str}, L{int})
        """
        assert isinstance(story_ids, (list, tuple))
        assert isinstance(story_ids[0], tuple)
        assert isinstance(story_ids[0][0], str)
        assert isinstance(story_ids[0][1], int)
        self.story_ids = story_ids


class TagRenderTask(Task):
    """
    A L{Task} for rendering tags.

    @ivar tag_type: type of tag to render
    @type tag_type: L{str}
    @ivar tag_name: name of tag to render
    @type tag_name: L{str}
    """
    type = "tag"

    def __init__(self, tag_type, tag_name):
        """
        The default constructor.

        @param tag_type: type of tag to render
        @type tag_type: L{str}
        @param tag_name: name of tag to render
        @type tag_name: L{str}
        """
        assert isinstance(tag_type, str)
        assert isinstance(tag_name, str)
        self.tag_type = tag_type
        self.tag_name = tag_name


class AuthorRenderTask(Task):
    """
    A L{Task} for rendering authors.

    @ivar publisher: publisher this author is from
    @type publisher: L{str}
    @ivar name: name of the author to render
    @type name: L{str}
    """
    type = "author"

    def __init__(self, publisher, name):
        """
        The default constructor.

        @param publisher: publisher this author is from
        @type publisher: L{str}
        @param name: name of the author to render
        @type name: L{str}
        """
        assert isinstance(publisher, str)
        assert isinstance(name, str)
        self.publisher = publisher
        self.name = name


class CategoryRenderTask(Task):
    """
    A L{Task} for rendering categories.

    @ivar publisher: publisher this category is from
    @type publisher: L{str}
    @ivar name: name of the category to render
    @type name: L{str}
    """
    type = "category"

    def __init__(self, publisher, name):
        """
        The default constructor.

        @param publisher: publisher this category is from
        @type publisher: L{str}
        @param name: name of the category to render
        @type name: L{str}
        """
        assert isinstance(publisher, str)
        assert isinstance(name, str)
        self.publisher = publisher
        self.name = name


class SeriesRenderTask(Task):
    """
    A L{Task} for rendering series.

    @ivar publisher: publisher this series is from
    @type publisher: L{str}
    @ivar name: name of the series to render
    @type name: L{str}
    """
    type = "series"

    def __init__(self, publisher, name):
        """
        The default constructor.

        @param publisher: publisher this series is from
        @type publisher: L{str}
        @param name: name of the series to render
        @type name: L{str}
        """
        assert isinstance(publisher, str)
        assert isinstance(name, str)
        self.publisher = publisher
        self.name = name


class PublisherRenderTask(Task):
    """
    A L{Task} for rendering publishers.

    @ivar publisher: publisher to render
    @type publisher: L{str}
    """
    type = "publisher"

    def __init__(self, publisher):
        """
        The default constructor.

        @param publisher: name of publisher to render
        @type publisher: L{str}
        """
        assert isinstance(publisher, str)
        self.publisher = publisher


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


class Worker(object):
    """
    The worker should be instantiated in a new process, where it will
    continuously process tasks from the main process.

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
    """
    def __init__(self, inqueue, outqueue, engine, options):
        """
        The default constructor.

        @param inqueue: the queue providing new tasks
        @type inqueue: L{multiprocessing.Queue}
        @param outqueue: the queue where results will be put
        @type outqueue: L{multiprocessing.Queue}
        @param engine: engine used for database connection. Be sure to dispose the connection pool first!
        @type engine: L{sqlalchemy.engine.Engine}
        @param options: options for the renderer
        @type options: L{zimfiction.zimbuild.renderer.RenderOptions}
        """
        self.inqueue = inqueue
        self.outqueue = outqueue
        self.engine = engine

        self.session = Session(engine)
        self.renderer = HtmlRenderer(options=options)

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
        running = True
        while running:
            task = self.inqueue.get(block=True)

            if task.type == "stop":
                # stop the worker
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
                self.outqueue.put(MARKER_TASK_COMPLETED)
        # send a message indicated that this worker has finished
        self.outqueue.put(MARKER_WORKER_STOPPED)

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
        for subresult in it:
            self.outqueue.put(subresult)

    def process_story_task(self, task):
        """
        Process a received story task.

        @param task: task to process
        @type task: L{StoryRenderTask}
        """
        for publisher, story_id in task.story_ids:
            # get the story

            story = self.session.scalars(
                select(Story)
                .where(Story.publisher_name == publisher, Story.id == story_id)
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
            result = self.renderer.render_story(story)
            self.handle_result(result)

    def process_tag_task(self, task):
        """
        Process a received tag task.

        @param task: task to process
        @type task: L{TagRenderTask}
        """
        # count stories in tag
        count_stmt = (
            select(func.count(StoryTagAssociation.story_id))
            .where(
                StoryTagAssociation.tag_type == task.tag_type,
                StoryTagAssociation.tag_name == task.tag_name,
                StoryTagAssociation.implied == False,
            )
        )
        n_stories_in_tag = self.session.execute(count_stmt).scalar_one()
        # get the tag
        should_eagerload = (n_stories_in_tag <= MAX_STORY_EAGERLOAD)
        # setup options
        if should_eagerload:
            options = (
                contains_eager(Tag.story_associations),
                contains_eager(Tag.story_associations, StoryTagAssociation.story),
                selectinload(Tag.story_associations, StoryTagAssociation.story, Story.chapters),
                undefer(Tag.story_associations, StoryTagAssociation.story, Story.summary),
            )
        else:
            # like above, but don't undefer summary nor eager load chapters
            options = (
                contains_eager(Tag.story_associations),
                contains_eager(Tag.story_associations, StoryTagAssociation.story),
                lazyload(Tag.story_associations, StoryTagAssociation.story, Story.chapters),
            )
        # only load non-implied tag associations
        stmt = (
            select(Tag)
            .where(
                Tag.type == task.tag_type,
                Tag.name == task.tag_name,
            ).join(
                StoryTagAssociation,
                and_(
                    StoryTagAssociation.tag_type == Tag.type,
                    StoryTagAssociation.tag_name == Tag.name,
                    StoryTagAssociation.implied == False,
                ),
            ).join(
                Story,
                and_(
                    StoryTagAssociation.story_publisher == Story.publisher_name,
                    StoryTagAssociation.story_id == Story.id,
                    StoryTagAssociation.implied == False,
                ),
            ).options(
                *options,
            )
        )
        tag = self.session.scalars(stmt).first()
        if tag is None:
            result = RenderResult()
        else:
            result = self.renderer.render_tag(tag)
        self.handle_result(result)

    def process_author_task(self, task):
        """
        Process a received author task.

        @param task: task to process
        @type task: L{AuthorRenderTask}
        """
        # get the author
        author = self.session.scalars(
            select(Author)
            .where(Author.publisher_name == task.publisher, Author.name == task.name)
            .options(
                # eager loading options
                joinedload(Author.stories).undefer(Story.summary),
            )
        ).first()
        result = self.renderer.render_author(author)
        self.handle_result(result)

    def process_category_task(self, task):
        """
        Process a received category task.

        @param task: task to process
        @type task: L{CategoryRenderTask}
        """
        # count stories in category
        count_stmt = (
            select(func.count(StoryCategoryAssociation.story_id))
            .where(
                StoryCategoryAssociation.category_publisher == Category.publisher_name,
                StoryCategoryAssociation.category_name == Category.name,
                StoryCategoryAssociation.implied == False,
            )
        )
        n_stories_in_category = self.session.execute(count_stmt).scalar_one()
        # get the tag
        should_eagerload = (n_stories_in_category <= MAX_STORY_EAGERLOAD)
        # setup options
        if should_eagerload:
            options = (
                contains_eager(Category.story_associations),
                contains_eager(Category.story_associations, StoryCategoryAssociation.story),
                selectinload(Category.story_associations, StoryCategoryAssociation.story, Story.chapters),
                undefer(Category.story_associations, StoryCategoryAssociation.story, Story.summary),
            )
        else:
            # same as above, but don't undefer story summaries not eager load chapters
            options = (
                contains_eager(Category.story_associations),
                contains_eager(Category.story_associations, StoryCategoryAssociation.story),
                lazyload(Category.story_associations, StoryCategoryAssociation.story, Story.chapters),
            )
        # get the category
        stmt = (
            select(Category)
            .where(
                Category.publisher_name == task.publisher,
                Category.name == task.name,
            ).join(
                StoryCategoryAssociation,
                and_(
                    StoryCategoryAssociation.category_publisher == Category.publisher_name,
                    StoryCategoryAssociation.category_name == Category.name,
                    StoryCategoryAssociation.implied == False,
                ),
            ).join(
                Story,
                and_(
                    StoryCategoryAssociation.story_publisher == Story.publisher_name,
                    StoryCategoryAssociation.story_id == Story.id,
                    StoryCategoryAssociation.implied == False,
                ),
            ).options(
                *options,
            )
        )
        category = self.session.scalars(stmt).first()
        if category is None:
            result = RenderResult()
        else:
            result = self.renderer.render_category(category)
        self.handle_result(result)

    def process_series_task(self, task):
        """
        Process a received series task.

        @param task: task to process
        @type task: L{SeriesRenderTask}
        """
        # get the series
        series = self.session.scalars(
            select(Series)
            .where(Series.publisher_name == task.publisher, Series.name == task.name)
            .options(
                # eager loading options
                joinedload(Series.story_associations),
                joinedload(Series.story_associations, StorySeriesAssociation.story).undefer(Story.summary),
            )
        ).first()
        result = self.renderer.render_series(series)
        self.handle_result(result)

    def process_publisher_task(self, task):
        """
        Process a received publisher task.

        @param task: task to process
        @type task: L{PublisherRenderTask}
        """
        # get the categories in the series
        publisher = self.session.scalars(
            select(Publisher)
            .where(Publisher.name == task.publisher)
            .options(
                # eager loading options
                joinedload(Publisher.categories),
                joinedload(Publisher.categories, Category.story_associations),
                joinedload(Publisher.categories, Category.story_associations, StoryCategoryAssociation.story),
            )
        ).first()
        result = self.renderer.render_publisher(
            publisher=publisher,
        )
        self.handle_result(result)

    def process_etc_task(self, task):
        """
        Process a received etc task.

        @param task: task to process
        @type task: L{PublisherRenderTask}
        """
        if task.subtask == "index":
            # render the indexpage
            publishers = self.session.scalars(
                select(Publisher)
                .options(
                    # eager loading options
                    subqueryload(Publisher.categories),
                    # joinedload(Publisher.categories, Category.stories),
                    raiseload(Publisher.categories, Category.story_associations),
                )
            ).all()
            result = self.renderer.render_index(publishers=publishers)
        elif task.subtask == "stats":
            # render the global statistics
            stories = self.session.scalars(
                select(Story)
                .options(
                    # eager loading options
                    # as it turns out, lazyloading is simply the fastest... This seems wrong...
                    # joinedload(Story.chapters),
                    # selectinload(Story.tags),
                    # joinedload(Story.author),
                    # joinedload(Story.series_associations),
                    # joinedload(Story.series_associations, StorySeriesAssociation.series),
                    subqueryload(Story.category_associations),
                    subqueryload(Story.category_associations, StoryCategoryAssociation.category),
                )
            ).all()
            stats = StoryListStatCreator.get_stats_from_iterable(stories)
            result = self.renderer.render_global_stats(stats)
        elif task.subtask == "search":
            # The search script
            result = self.renderer.render_search_script()
        else:
            raise ValueError("Unknown etc subtask: '{}'!".format(task.subtask))
        self.handle_result(result)
