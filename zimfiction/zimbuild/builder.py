"""
This module manages the build of the ZIM files.

It handles the ZIM creator, add basic content, instantiates the workers,
issues them their tasks and adds the result to the creator.

@var MAX_OUTSTANDING_TASKS: max size of the task queue
@type MAX_OUTSTANDING_TASKS: L{int}
@var MAX_RESULT_BACKLOG: max size of the task result queue
@type MAX_RESULT_BACKLOG: L{int}
@var STORIES_PER_TASK: number of storiy IDs to send per worker tasks
@type STORIES_PER_TASK: L{int}
"""
import multiprocessing
import threading
import queue
import datetime
import time
import os
import contextlib
import math
import pdb
import signal
import pathlib

from scss.compiler import Compiler as ScssCompiler
from scss.namespace import Namespace as ScssNamespace
from scss.types import String as ScssString
from sqlalchemy import select, func, distinct
from sqlalchemy.orm import Session
from libzim.writer import Creator, Item, StringProvider, FileProvider, Hint

try:
    import psutil
except ImportError:
    psutil = None
try:
    import setproctitle
except ImportError:
    setproctitle = None

from ..util import get_package_dir, get_resource_file_path, set_or_increment
from ..util import format_timedelta, format_size, format_number
from ..db.models import Story, Author, Series, Publisher, StoryTagAssociation, StoryCategoryAssociation
from ..db.unique import set_unique_enabled
from ..implication.implicationlevel import ImplicationLevel
from ..reporter import StdoutReporter
from .renderer import HtmlPage, Redirect, JsonObject, Script, RenderOptions
from .worker import Worker, WorkerOptions, StopTask, StoryRenderTask
from .worker import TagRenderTask, AuthorRenderTask, CategoryRenderTask
from .worker import SeriesRenderTask, PublisherRenderTask, EtcRenderTask
from .worker import MARKER_TASK_COMPLETED, MARKER_WORKER_STOPPED
from .buckets import BucketMaker


MAX_OUTSTANDING_TASKS = 1024 * 4
MAX_RESULT_BACKLOG = 512
STORIES_PER_TASK = 64


# =============== HELPER FUNCTIONS ================


def get_n_cores():
    """
    Return the number of cores to use.
    If multiprocessing is available, this is the number of cores available.
    Otherwise, this will be 1.

    @return: the number of cores to use.
    @rtype: L{int}
    """
    if multiprocessing is not None:
        return multiprocessing.cpu_count()
    else:
        return 1


def config_process(name, nice=0, ionice=0):
    """
    Configure the current OS process.

    This function expects the linux values and will try to guess the
    approximate windows values.

    @param name: name for the current process
    @type name: L{str}
    @param nice: new nice value for current process (-21->19 (lowest))
    @type nice: L{int}
    @param ionice: new io nice value for the process (0->17 (lowest))
    @type ionice: L{int}
    """
    # name
    if setproctitle is not None:
        setproctitle.setproctitle(name)
    # nice and ionice
    if psutil is not None:
        p = psutil.Process()
        if psutil.LINUX:
            p.nice(nice)
            p.ionice(psutil.IOPRIO_CLASS_BE, ionice)
        else:
            if nice > 0:
                nv = psutil.ABOVE_NORMAL_PRIORITY_CLASS
            elif nice < 0:
                nv = psutil.BELOW_NORMAL_PRIORITY_CLASS
            else:
                nv = psutil.NORMAL_PRIORITY_CLASS
            p.nice(nv)
            if ionice < 4:
                iv = psutil.IOPRIO_HIGH
            elif ionice > 4:
                iv = psutil.IOPRIO_LOW
            else:
                iv = psutil.IOPRIO_NORMAL
            p.ionice(iv)


def config_thread(name):
    """
    Configure the current OS thread.

    @param name: new name of the thread
    @type name: L{str}
    """
    if setproctitle is not None:
        setproctitle.setthreadtitle(name)


# ================ DEBUG HELPER ============


def on_pdb_interrupt(sig, frame):
    """
    Called on an SIGUSR1 interrupt to start pdb debugging.
    """
    pdb.Pdb().set_trace(frame)


try:
    signal.signal(signal.SIGUSR1, on_pdb_interrupt)
except Exception:
    pass


# =============== ITEM DEFINITIONS ================


class HtmlPageItem(Item):
    """
    A L{libzim.writer.Item} for HTML pages.
    """
    def __init__(self, path, title, content, is_front=True):
        """
        The default constructor.

        @param path: path of the page in the ZIM file
        @type path: L{str}
        @param title: title of the page
        @type title: L{str}
        @param content: the content of the page
        @type content: L{str}
        @param is_front: if this is nonzero, set this as a front article
        @type is_front: L{bool}
        """
        super().__init__()
        self._path = path
        self._title = title
        self._content = content
        self._is_front = is_front

    def get_path(self):
        return self._path

    def get_title(self):
        return self._title

    def get_mimetype(self):
        return "text/html"

    def get_contentprovider(self):
        return StringProvider(self._content)

    def get_hints(self):
        return {
            Hint.FRONT_ARTICLE: self._is_front,
            Hint.COMPRESS: True,
        }


class JsonItem(Item):
    """
    A L{libzim.writer.Item} for json.
    """
    def __init__(self, path, title, content):
        """
        The default constructor.

        @param path: path of to store item in ZIM file
        @type path: L{str}
        @param title: title of the json file
        @type title: L{str}
        @param content: the content of the json file
        @type content: L{str}
        """
        super().__init__()
        self._path = path
        self._title = title
        self._content = content

    def get_path(self):
        return self._path

    def get_title(self):
        return self._title

    def get_mimetype(self):
        return "application/json"

    def get_contentprovider(self):
        return StringProvider(self._content)

    def get_hints(self):
        return {
            Hint.FRONT_ARTICLE: False,
            Hint.COMPRESS: True,
        }


class ScriptItem(Item):
    """
    A L{libzim.writer.Item} for a js script.
    """
    def __init__(self, path, title, content):
        """
        The default constructor.

        @param path: path of to store item in ZIM file
        @type path: L{str}
        @param title: title of the js file
        @type title: L{str}
        @param content: the content of the js file
        @type content: L{str}
        """
        super().__init__()
        self._path = path
        self._title = title
        self._content = content

    def get_path(self):
        return self._path

    def get_title(self):
        return self._title

    def get_mimetype(self):
        return "text/javascript"

    def get_contentprovider(self):
        return StringProvider(self._content)

    def get_hints(self):
        return {
            Hint.FRONT_ARTICLE: False,
            Hint.COMPRESS: True,
        }


class StylesheetItem(Item):
    """
    A L{libzim.writer.Item} for the CSS stylesheet.
    """
    def __init__(self, theme="light"):
        """
        The default constructor.

        @param theme: theme to render
        @type theme: L{str}
        """
        super().__init__()
        self._theme = theme

    def get_path(self):
        return "style_{}.css".format(self._theme)

    def get_title(self):
        return "CSS Stylesheet"

    def get_mimetype(self):
        return "text/css"

    def get_contentprovider(self):
        path = get_resource_file_path("style.scss")
        with open(path, "r") as fin:
            scss = fin.read()
        namespace = ScssNamespace()
        namespace.set_variable("$theme", ScssString(self._theme))
        compiler = ScssCompiler(
            root=pathlib.Path(get_package_dir()),
            search_path=["resources"],
            live_errors=False,  # raise exception when compilation fails
            namespace=namespace,
        )
        css = compiler.compile_string(scss)
        return StringProvider(css)

    def get_hints(self):
        return {
            Hint.FRONT_ARTICLE: False,
            Hint.COMPRESS: True,
        }


class FaviconItem(Item):
    """
    A L{libzim.writer.Item} for the favicon.
    """
    def __init__(self):
        """
        The default constructor.
        """
        super().__init__()

    def get_path(self):
        return "favicon.png"

    def get_title(self):
        return "Favicon (PNG)"

    def get_mimetype(self):
        return "image/png"

    def get_contentprovider(self):
        return FileProvider(get_resource_file_path("icon_highres.png"))

    def get_hints(self):
        return {
            Hint.FRONT_ARTICLE: False,
            Hint.COMPRESS: True,
        }


# =============== BUILD LOGIC =================


class BuildOptions(object):
    """
    A class containing the build options for the ZIM.

    @ivar name: human-readable identifier of the resource
    @type name: L{str}
    @ivar title: title of ZIM file
    @type title: L{str}
    @ivar creator: creator of the ZIM file content
    @type creator: L{str}
    @ivar publisher: publisher of the ZIM file
    @type publisher: L{str}
    @ivar description: description of the ZIM file
    @type description: L{str}
    @ivar language: language to use (e.g. "eng")
    @type language: L{str}
    @ivar indexing: whether indexing should be enabled or not
    @type indexing: L{bool}

    @ivar use_threads: if nonzero, use threads instead of processes
    @type use_threads: L{bool}
    @ivar num_workers: number of (non-zim) workers to use
    @type num_workers: L{int}
    @ivar log_directory: if not None, enable logging and write logs into this directory
    @type log_directory: L{str} or L{None}

    @ivar eager: if nonzero, eager load objects from database
    @type eager: L{bool}
    @ivar memprofile_directory: if not None, enable memory profiling and write files into this directory
    @type memprpofile_directory: L{str} or L{None}

    @ivar include_external_links: whether the ZIM should contain external links or not
    @type include_external_links: L{bool}

    @ivar skip_stories: debug option to not render stories
    @type skip_stories: L{bool}
    """
    def __init__(
        self,

        # ZIM options
        name="zimfiction_eng",
        title="ZimFiction",
        creator="Various fanfiction communities",
        publisher="ZimFiction",
        description="ZIM file containing dumps of various fanfiction sites",
        language="eng",
        indexing=True,

        # genral build_options
        log_directory=None,

        # worker management options
        use_threads=False,
        num_workers=None,

        # worker options
        eager=True,
        memprofile_directory=None,

        # render options
        include_external_links=False,

        # debug options
        skip_stories=False,
        ):
        """
        The default constructor.

        @param name: human-readable identifier of the resource
        @type name: L{str}
        @param title: title of ZIM file
        @type title: L{str}
        @param creator: creator of the ZIM file content
        @type creator: L{str}
        @param publisher: publisher of the ZIM file
        @type publisher: L{str}
        @param description: description of the ZIM file
        @type description: L{str}
        @param language: language to use (e.g. "eng")
        @type language: L{str}
        @param indexing: whether indexing should be enabled or not
        @type indexing: L{bool}

        @param use_threads: if nonzero, use threads instead of processes
        @type use_threads: L{bool}
        @param num_workers: number of (non-zim) workers to use (None -> auto)
        @type num_workers: L{int} or L{None}

        @param log_directory: if specified, enable logging and write logs into this directory
        @type log_directory: L{str} or L{None}

        @param eager: if nonzero, eager load objects from database
        @type eager: L{bool}
        @param memprofile_directory: if specified, enable memory profiling and write files into this directory
        @type memprpofile_directory: L{str} or L{None}

        @param include_external_links: whether the ZIM should contain external links or not
        @type include_external_links: L{bool}

        @param skip_stories: debug option to not render stories
        @type skip_stories: L{bool}
        """
        self.name = name
        self.title = title
        self.creator = creator
        self.publisher = publisher
        self.description = description
        self.language = language
        self.indexing = indexing

        self.use_threads = bool(use_threads)
        if num_workers is None:
            self.num_workers = get_n_cores()
        else:
            self.num_workers = int(num_workers)

        self.log_directory = log_directory

        self.eager = eager
        self.memprofile_directory = memprofile_directory

        self.include_external_links = include_external_links

        self.skip_stories = skip_stories

    def get_metadata_dict(self):
        """
        Return a dictionary encoding the ZIM metadata described by this file.

        Additional metadata will likely be added.

        @return: a dictionary containing the metadata of this ZIM file.
        @rtype: L{bool}
        """
        tags = [
            "_sw:no",
            "_ftindex:" + ("yes" if self.indexing else "no"),
            "_pictures:no",  # may change in the future
            "_videos:no",  # unlikely to change
            "_category:fanfiction",
        ]
        metadata = {
            "Name": self.name,
            "Title": self.title,
            "Creator": self.creator,
            "Date": datetime.date.today().isoformat(),
            "Publisher": self.publisher,
            "Description": self.description,
            "Language": self.language,
            "Tags": ";".join(tags),
            "Scraper": "zimfiction",
        }
        return metadata

    def get_worker_options(self):
        """
        Return the worker options the worker should use.

        @return: options for the worker.
        @rtype: L{zimfiction.zimbuild.worker.WorkerOptions}
        """
        options = WorkerOptions(
            eager=self.eager,
            memprofile_directory=self.memprofile_directory,
            log_directory=self.log_directory,
        )
        return options

    def get_render_options(self):
        """
        Return the render options the renderer should use.

        @return: options for the renderer
        @rtype: L{zimfiction.zimbuild.renderer.RenderOptions}
        """
        options = RenderOptions(
            include_external_links=self.include_external_links,
        )
        return options


class ZimBuilder(object):
    """
    The ZimBuilder manages the ZIM build process.

    @ivar inqueue: the queue where tasks will be put
    @type inqueue: L{multiprocessing.Queue} or L{queue.Queue}
    @ivar outqueue: the queue containing the task results
    @type outqueue: L{multiprocessing.Queue} or L{queue.Queue}
    @ivar connection_config: configuration for database connection
    @type connection_config: L{zimfiction.db.connection.ConnectionConfig}
    @ivar reporter: reporter used for status reports
    @type reporter: L{zimfiction.reporter.BaseReporter}
    @ivar num_files_added: a dict mapping a filetype to the number of files of that type
    @type num_files_added: L{dict} of L{str} -> L{int}
    @ivar next_worker_id: ID to give next worker
    @type next_worker_id: L{int}
    """
    def __init__(self, connection_config):
        """
        The default constructor.

        @param connection_config: configuration for database connection
        @type connection_config: L{zimfiction.db.connection.ConnectionConfig}
        """
        self.connection_config = connection_config

        self.inqueue = None
        self.outqueue = None
        self.num_files_added = {}
        self.next_worker_id = 0

        self.reporter = StdoutReporter();

    def _init_queues(self, options):
        """
        Initialize the queues.

        @param options: build options
        @type options: L{BuildOptions}
        """
        if options.use_threads:
            self.inqueue = queue.Queue(maxsize=MAX_OUTSTANDING_TASKS)
            self.outqueue = queue.Queue(maxsize=MAX_RESULT_BACKLOG)
        else:
            self.inqueue = multiprocessing.Queue(maxsize=MAX_OUTSTANDING_TASKS)
            self.outqueue = multiprocessing.Queue(maxsize=MAX_RESULT_BACKLOG)

    def cleanup(self):
        """
        Perform clean up tasks.
        """
        pass
        # self.session.close()
        # self.engine.dispose()

    def build(self, outpath, options):
        """
        Build a ZIM.

        @param outpath: path to write ZIM to
        @type outpath: L{str}
        @param options: build options for the ZIM
        @type options: L{BuildOptions}
        """
        # prepare build
        self.reporter.msg("Preparing build...")

        start = time.time()
        set_unique_enabled(False)  # disable unique caches to save RAM

        # find and report options for the build
        self.reporter.msg(" -> Generating ZIM creation config...")
        compression = "zstd"
        # clustersize = 8 * 1024 * 1024  # 8 MiB
        clustersize = 2 * 1024 * 1024  # 2 MiB
        verbose = True
        n_creator_workers = get_n_cores()
        n_render_workers = options.num_workers
        use_threads = options.use_threads
        self.reporter.msg("        -> Path:             {}".format(outpath))
        self.reporter.msg("        -> Verbose:          {}".format(verbose))
        self.reporter.msg("        -> Compression:      {}".format(compression))
        self.reporter.msg("        -> Cluster size:     {}".format(format_size(clustersize)))
        self.reporter.msg("        -> Creator Workers:  {}".format(n_creator_workers))
        self.reporter.msg("        -> Render Workers:   {}".format(n_render_workers))
        self.reporter.msg("            -> using: {}".format("threads" if use_threads else "processes"))
        if not use_threads:
            self.reporter.msg("            -> started using: {}".format(multiprocessing.get_start_method()))
        self.reporter.msg("            -> eagerloading: {}".format("enabled" if options.eager else "disabled"))
        self.reporter.msg("        -> Done.")

        # connect to database
        # initially, we did this in __init__ and set the engine+session
        # as attributes, but as the engine is not pickable, this prevents
        # the use of "forkserver" for multiprocessing
        self.reporter.msg(" -> Establishing database connection... ", end="")
        engine = self.connection_config.connect()
        session = Session(engine)
        self.reporter.msg("Done.")

        # initailize queues
        self.reporter.msg(" -> Initiating queues...", end="")
        self._init_queues(options)
        self.reporter.msg("Done.")

        # open the ZIM creator
        self.reporter.msg("Opening ZIM creator, writing to path '{}'... ".format(outpath), end="")
        with Creator(outpath) \
            .config_indexing(options.indexing, options.language) \
            .config_clustersize(clustersize) \
            .config_verbose(verbose) \
            .config_nbworkers(n_creator_workers) as creator:
            self.reporter.msg("Done.")

            # configurations
            self.reporter.msg("Configuring ZIM... ", end="")
            creator.set_mainpath("index.html")
            self.reporter.msg("Done.")

            # add illustration
            self.reporter.msg("Adding illustration... ", end="")
            imagepath = get_resource_file_path("icon.png")
            with open(imagepath, "rb") as fin:
                creator.add_illustration(48, fin.read())
            set_or_increment(self.num_files_added, "image")
            self.reporter.msg("Done.")

            # add metadata
            self.reporter.msg("Adding metadata... ", end="")
            metadata = options.get_metadata_dict()
            for key, value in metadata.items():
                creator.add_metadata(key, value)
                set_or_increment(self.num_files_added, "metadata")
            self.reporter.msg("Done.")

            # add general items
            self.reporter.msg("Adding stylesheet... ", end="")
            creator.add_item(StylesheetItem(theme="light"))
            set_or_increment(self.num_files_added, "css")
            creator.add_item(StylesheetItem(theme="dark"))
            set_or_increment(self.num_files_added, "css")
            self.reporter.msg("Done.")
            self.reporter.msg("Adding favicon... ", end="")
            creator.add_item(FaviconItem())
            set_or_increment(self.num_files_added, "image")
            self.reporter.msg("Done.")

            # add content
            self._add_content(creator, session, options=options)

            # finish up
            self.reporter.msg("Finalizing ZIM...")
        self.reporter.msg("Done.")
        self.reporter.msg("Cleaning up... ", end="")
        self.cleanup()
        self.reporter.msg("Done.")

        # We're done, find and report some stats about the build
        final_size = os.stat(outpath).st_size
        end = time.time()
        time_elapsed = end - start
        self.reporter.msg("Finished ZIM creation in {}.".format(format_timedelta(time_elapsed)))
        self.reporter.msg("Final size: {}".format(format_size(final_size)))
        self.reporter.msg("Added files: ")
        for filetype, amount in self.num_files_added.items():
            if filetype != "total":
                # print total later
                self.reporter.msg("    {}: {} ({})".format(filetype, amount, format_number(amount)))
        total_amount = self.num_files_added["total"]
        self.reporter.msg("    total: {} ({})".format(total_amount, format_number(total_amount)))


    def _add_content(self, creator, session, options):
        """
        Add the content of the ZIM file.

        @param creator: the ZIM creator
        @type creator: L{zimfiction.writer.Creator}
        @param session: sqlalchemy session for data querying
        @type session: L{sqlalchemy.orm.Session}
        @param options: build options for the ZIM
        @type options: L{BuildOptions}
        """
        # the order in which we add the content may look a bit strange,
        # but it is actually optimized for RAM usage. Basically, some
        # tasks require significantly more RAM to complete and adding
        # items to the ZIM create causes a permament RAM usage increase.
        # For example, rendering stories requires nearly no RAM, but the
        # high amount of items added will reduce available RAM for the
        # rest of the build, thus it is advisable to add the stories
        # late, whereas tags require quite a bit of RAM while also adding
        # quite a few items, thus it is better to render tags somewhere
        # in the middle
        self.reporter.msg("Adding content...")
        # --- miscelaneous pages ---
        self.reporter.msg(" -> Adding miscelaneous pages...")
        n_misc_pages = 5
        with self._run_stage(
            creator=creator,
            options=options,
            task_name="Adding miscelaneous pages...",
            n_tasks=n_misc_pages,
            task_unit="pages",
        ):
            self._send_etc_tasks(session)
        # --- publisher ---
        self.reporter.msg(" -> Adding Publishers...")
        self.reporter.msg("     -> Finding publishers... ", end="")
        n_publishers = session.execute(
            select(func.count(Publisher.uid))
        ).scalar_one()
        self.reporter.msg("found {} publishers.".format(n_publishers))
        with self._run_stage(
            creator=creator,
            options=options,
            task_name="Adding publishers...",
            n_tasks=n_publishers,
            task_unit="publishers",
        ):
            self._send_publisher_tasks(session)
        # --- tags ---
        self.reporter.msg(" -> Adding tags...")
        self.reporter.msg("     -> Finding tags... ", end="")
        n_tags = session.execute(
            select(
                func.count(
                    distinct(StoryTagAssociation.tag_uid)
                )
            ).where(
                StoryTagAssociation.implication_level < ImplicationLevel.MIN_IMPLIED,
            )
        ).scalar_one()
        self.reporter.msg("found {} non-implied tags.".format(n_tags))
        with self._run_stage(
            creator=creator,
            options=options,
            task_name="Adding Tags...",
            n_tasks=n_tags,
            task_unit="tags",
        ):
            self._send_tag_tasks(session)
        # --- categories ---
        self.reporter.msg(" -> Adding Categories...")
        self.reporter.msg("     -> Finding categories... ", end="")
        n_categories = session.execute(
            select(
                func.count(distinct(StoryCategoryAssociation.category_uid))
            ).where(
                StoryCategoryAssociation.implication_level < ImplicationLevel.MIN_IMPLIED,
            )
        ).scalar_one()
        self.reporter.msg("found {} non-implied categories.".format(n_categories))
        with self._run_stage(
            creator=creator,
            options=options,
            task_name="Adding categories...",
            n_tasks=n_categories,
            task_unit="categories",
        ):
            self._send_category_tasks(session)
        # --- series ---
        self.reporter.msg(" -> Adding Series...")
        self.reporter.msg("     -> Finding series... ", end="")
        n_series = session.execute(
            select(func.count(Series.uid))
        ).scalar_one()
        self.reporter.msg("found {} series.".format(n_series))
        with self._run_stage(
            creator=creator,
            options=options,
            task_name="Adding series...",
            n_tasks=n_series,
            task_unit="series",
        ):
            self._send_series_tasks(session)
        # --- authors ---
        self.reporter.msg(" -> Adding Authors...")
        self.reporter.msg("     -> Finding authors... ", end="")
        n_authors = session.execute(
            select(func.count(Author.uid))
        ).scalar_one()
        self.reporter.msg("found {} authors.".format(n_authors))
        with self._run_stage(
            creator=creator,
            options=options,
            task_name="Adding Authors...",
            n_tasks=n_authors,
            task_unit="authors",
        ):
            self._send_author_tasks(session)
        # --- stories ---
        if not options.skip_stories:
            self.reporter.msg(" -> Adding stories...")
            self.reporter.msg("     -> Finding stories... ", end="")
            n_stories = session.execute(
                select(func.count(Story.uid))
            ).scalar_one()
            self.reporter.msg("found {} stories.".format(n_stories))
            n_story_tasks = math.ceil(n_stories / STORIES_PER_TASK)
            with self._run_stage(
                creator=creator,
                options=options,
                task_name="Adding stories...",
                n_tasks=n_story_tasks,
                task_unit="stories",
                task_multiplier=STORIES_PER_TASK,
            ):
                self._send_story_tasks(session)
        else:
            self.reporter.msg(" -> Skipping stories!")

    @contextlib.contextmanager
    def _run_stage(self, options, **kwargs):
        """
        Add the content of the ZIM file.

        @param options: zim build options
        @type options: L{BuildOptions}
        @param kwargs: keyword arguments passed to L{ZmBuilder._creator_thread}
        @type kwargs: L{dict}
        """

        if "options" not in kwargs:
            kwargs["options"] = options
        n_workers = options.num_workers

        worker_class = (threading.Thread if options.use_threads else multiprocessing.Process)
        worker_options = options.get_worker_options()
        render_options = options.get_render_options()

        # start workers
        self.reporter.msg("     -> Starting workers... ", end="")
        workers = []
        for i in range(n_workers):
            worker_id = self.next_worker_id
            self.next_worker_id += 1
            worker = worker_class(
                name="Content worker {}".format(worker_id),
                target=self._worker_process,
                kwargs={
                    "id": worker_id,
                    "connection_config": self.connection_config,
                    "worker_options": worker_options,
                    "render_options": render_options,
                },
            )
            worker.daemon = True
            worker.start()
            workers.append(worker)
        self.reporter.msg("Done.")

        # start the background creator thread
        # for the duration of this method, only the thread is allowed
        # to work with the creator directly
        self.reporter.msg("     -> Starting creator thread... ", end="")
        creator_thread = threading.Thread(  # <-- always use threads here
            name="Creator content adder thread",
            target=self._creator_thread,
            kwargs=kwargs,
        )
        creator_thread.daemon = True
        creator_thread.start()
        self.reporter.msg("Done.")

        # now it's finally time to add the tasks
        yield

        # finish up
        self.reporter.msg("     -> Waiting for workers... ", end="")
        # put stop tasks on queue
        for i in range(n_workers):
            self.inqueue.put(StopTask())
        # join with all workers
        for worker in workers:
            worker.join()
            if hasattr(worker, "close"):
                worker.close()
        self.reporter.msg("Done.")

        self.reporter.msg("     -> Joining with creator thread... ", end="")
        creator_thread.join()
        self.reporter.msg("Done.")
        self.reporter.msg("     -> Done.")

    def _creator_thread(
        self,
        creator,
        options,
        task_name,
        n_tasks,
        task_unit,
        task_multiplier=1,
        ):
        """
        This method will be executed as the creator thread.

        This function is responsible to get results from the outqueue
        and adding them to the ZIM file.

        @param creator: creator for the ZIM file
        @type creator: L{libzim.creator.Creator}
        @param options: zim build options
        @type options: L{BuildOptions}
        @param taskname
        @param task_name: name of the task that is currently being processed
        @type task_name: L{str}
        @param n_tasks: number of tasks issued
        @type n_tasks: L{int}
        @param task_unit: string describing the unit of the task (e.g. stories)
        @type task_unit: L{str}
        @param task_multiplier: multiply bar advancement per task by this factor
        @type task_multiplier: L{int}
        """
        if not options.use_threads:
            # setup priority first
            config_process(name="ZF creator", nice=2, ionice=7)
        config_thread(name="Creator thread")
        # main loop - get results from queue and add them to ZIM
        running = True
        n_finished = 0
        with self.reporter.with_progress(description=task_name, max=n_tasks*task_multiplier, unit=task_unit, secondary_unit="items") as bar:
            while running:
                render_result = self.outqueue.get(block=True)
                bar.advance(0)  # redraw
                if render_result == MARKER_WORKER_STOPPED:
                    # worker finished
                    n_finished += 1
                    if n_finished == options.num_workers:
                        # all workers shut down
                        running = False
                elif render_result == MARKER_TASK_COMPLETED:
                    # task was completed
                    bar.advance(task_multiplier)
                else:
                    # add the rendered objects to the ZIM
                    for rendered_object in render_result.iter_objects():
                        if isinstance(rendered_object, HtmlPage):
                            # add a HTML page
                            item = HtmlPageItem(
                                path=rendered_object.path,
                                title=rendered_object.title,
                                content=rendered_object.content,
                                is_front=rendered_object.is_front,
                            )
                            creator.add_item(item)
                            set_or_increment(self.num_files_added, "html")
                        elif isinstance(rendered_object, JsonObject):
                            # add a json object
                            item = JsonItem(
                                path=rendered_object.path,
                                title=rendered_object.title,
                                content=rendered_object.content,
                            )
                            creator.add_item(item)
                            set_or_increment(self.num_files_added, "json")
                        elif isinstance(rendered_object, Redirect):
                            # create a redirect
                            creator.add_redirection(
                                rendered_object.source,
                                rendered_object.title,
                                rendered_object.target,
                                hints = {
                                    Hint.FRONT_ARTICLE: rendered_object.is_front,
                                }
                            )
                            set_or_increment(self.num_files_added, "redirect")
                        elif isinstance(rendered_object, Script):
                            # add a script
                            item = ScriptItem(
                                path=rendered_object.path,
                                title=rendered_object.title,
                                content=rendered_object.content,
                            )
                            creator.add_item(item)
                            set_or_increment(self.num_files_added, "js")
                        else:
                            # unknown result object
                            raise RuntimeError("Unknown render result: {}".format(type(rendered_object)))
                        set_or_increment(self.num_files_added, "total")
                        bar.advance(0, secondary=1)

    def _worker_process(self, id, connection_config, worker_options, render_options):
        """
        This method will be executed as a worker process.

        The workers take tasks from the inqueue, process them and add
        the result to the outqueue.

        @param id: id of the worker
        @type id: L{int}
        @param connection_config: database connection configuration
        @type connection_config: L{zimfiction.db.connection.ConnectionConfig}
        @param worker_options: options for the worker
        @type worker_options: L{zimfiction.zimbuild.worker.WorkerOptions}
        @param render_options: options for the renderer
        @type render_options: L{zimfiction.zimbuild.renderer.RenderOptions}
        """
        # prepare the process priority
        config_process(name="ZF worker {}".format(id), nice=10, ionice=5)
        # start the worker
        worker = Worker(
            id=id,
            inqueue=self.inqueue,
            outqueue=self.outqueue,
            engine=connection_config.connect(),
            options=worker_options,
            render_options=render_options,
        )
        worker.run()

    def _send_story_tasks(self, session):
        """
        Create and send the tasks for the stories to the worker inqueue.

        @param session: sqlalchemy session for data querying
        @type session: L{sqlalchemy.orm.Session}
        """
        story_bucket_maker = BucketMaker(maxsize=STORIES_PER_TASK)
        select_story_ids_stmt = select(Story.uid)
        result = session.execute(select_story_ids_stmt)
        # create buckets and turn them into tasks
        for story in result:
            bucket = story_bucket_maker.feed(story.uid)
            if bucket is not None:
                # send out a task
                task = StoryRenderTask(story_uids=bucket)
                self.inqueue.put(task)
        # send out all remaining tasks
        bucket = story_bucket_maker.finish()
        if bucket is not None:
            task = StoryRenderTask(bucket)
            self.inqueue.put(task)

    def _send_tag_tasks(self, session):
        """
        Create and send the tasks for the tags to the worker inqueue.

        @param session: sqlalchemy session for data querying
        @type session: L{sqlalchemy.orm.Session}
        """
        # select from tag association such that we only add non-implied tags
        select_tags_stmt = (
            select(
                distinct(StoryTagAssociation.tag_uid)
            ).where(
                StoryTagAssociation.implication_level < ImplicationLevel.MIN_IMPLIED
            )
        )
        result = session.scalars(select_tags_stmt)
        for tag_uid in result:
            task = TagRenderTask(uid=tag_uid)
            self.inqueue.put(task)

    def _send_author_tasks(self, session):
        """
        Create and send the tasks for the authors to the worker inqueue.

        @param session: sqlalchemy session for data querying
        @type session: L{sqlalchemy.orm.Session}
        """
        select_authors_stmt = select(Author.uid)
        result = session.execute(select_authors_stmt)
        for author in result:
            task = AuthorRenderTask(uid = author.uid)
            self.inqueue.put(task)

    def _send_category_tasks(self, session):
        """
        Create and send the tasks for the categories to the worker inqueue.

        @param session: sqlalchemy session for data querying
        @type session: L{sqlalchemy.orm.Session}
        """
        select_categories_stmt = (
            select(
                distinct(StoryCategoryAssociation.category_uid)
            ).where(
                StoryCategoryAssociation.implication_level < ImplicationLevel.MIN_IMPLIED
            )
        )
        result = session.scalars(select_categories_stmt)
        for category_uid in result:
            task = CategoryRenderTask(uid=category_uid)
            self.inqueue.put(task)

    def _send_series_tasks(self, session):
        """
        Create and send the tasks for the series to the worker inqueue.

        @param session: sqlalchemy session for data querying
        @type session: L{sqlalchemy.orm.Session}
        """
        select_series_stmt = select(Series.uid)
        result = session.execute(select_series_stmt)
        for series in result:
            task = SeriesRenderTask(uid=series.uid)
            self.inqueue.put(task)

    def _send_publisher_tasks(self, session):
        """
        Create and send the tasks for the publishers to the worker inqueue.

        @param session: sqlalchemy session for data querying
        @type session: L{sqlalchemy.orm.Session}
        """
        select_publishers_stmt = select(Publisher.uid)
        result = session.execute(select_publishers_stmt)
        for publisher in result:
            task = PublisherRenderTask(uid=publisher.uid)
            self.inqueue.put(task)

    def _send_etc_tasks(self, session):
        """
        Create and send the tasks for the miscelaneous pages to the worker inqueue.

        @param session: sqlalchemy session for data querying
        @type session: L{sqlalchemy.orm.Session}
        """
        indextask = EtcRenderTask("index")
        self.inqueue.put(indextask)
        statstask = EtcRenderTask("stats")
        self.inqueue.put(statstask)
        searchtask = EtcRenderTask("search")
        self.inqueue.put(searchtask)
        chartjstask = EtcRenderTask("chartscripts")
        self.inqueue.put(chartjstask)
        infotask = EtcRenderTask("info")
        self.inqueue.put(infotask)
