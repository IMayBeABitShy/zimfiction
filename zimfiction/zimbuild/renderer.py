"""
The renderer generates HTML pages.
"""
import urllib.parse
import json
import datetime
import math

import htmlmin
import mistune
from jinja2 import Environment, PackageLoader, select_autoescape

# optional optimization dependencies
try:
    import minify_html
except ImportError:
    minify_html = None

from ..util import format_size, format_number, normalize_tag, get_resource_file_path
from ..statistics import StoryListStatCreator
from .buckets import BucketMaker
from .search import SearchMetadataCreator


STORIES_PER_PAGE = 20
CATEGORIES_PER_PAGE = 200
CATEGORIES_ON_PUBLISHER_PAGE = 200
SEARCH_ITEMS_PER_FILE = 35000
MIN_STORIES_FOR_SEARCH = 5
MAX_STORIES_FOR_SEARCH = float("inf")
SEARCH_ONLY_ON_FIRST_PAGE = True
MAX_ITEMS_PER_RESULT = 200


class RenderedObject(object):
    """
    Base class for render results.
    """
    pass


class HtmlPage(RenderedObject):
    """
    This class holds the representation of a single rendered page.

    @ivar path: absolute path of the rendered page
    @type path: L{str}
    @ivar title: title of the page
    @type title: L{str}
    @ivar content: the HTML code of the page
    @type content: L{str}
    @ivar is_front: True if this is a front article
    @type is_front: L{bool}
    """
    def __init__(self, path, title, content, is_front=True):
        """
        The default constructor.

        @param path: absolute path of the rendered page
        @type path: L{str}
        @param title: title of the page
        @type title: L{str}
        @param content: the HTML code of the page
        @param content: L{str}
        @param is_front: True if this is a front article
        @type is_front: L{bool}
        """
        assert isinstance(path, str)
        assert isinstance(title, str)
        assert isinstance(content, str)
        assert isinstance(is_front, bool)
        self.path = path
        self.title = title
        self.content = content
        self.is_front = is_front


class JsonObject(RenderedObject):
    """
    This class holds a rendered json object.

    @ivar path: absolute path the object should be stored at
    @type path: L{str}
    @ivar title: title of the object
    @type title: L{str}
    @ivar content: the serialized json object to store
    @type content: L{str}
    """
    def __init__(self, path, title, content):
        """
        The default constructor.

        @ivar path: absolute path the object should be stored at
        @type path: L{str}
        @ivar title: title of the object
        @type title: L{str}
        @ivar content: the json object to store
        @type content: json-serializable
        """
        assert isinstance(path, str)
        assert isinstance(title, str)
        self.path = path
        self.title = title
        self.content = json.dumps(content, separators=(",", ":"))


class Script(RenderedObject):
    """
    This class holds a rendered js script.

    @ivar path: absolute path the script should be stored at
    @type path: L{str}
    @ivar title: title of the object
    @type title: L{str}
    @ivar content: the script itself
    @type content: L{str}
    """
    def __init__(self, path, title, content):
        """
        The default constructor.

        @ivar path: absolute path the object should be stored at
        @type path: L{str}
        @ivar title: title of the script
        @type title: L{str}
        @ivar content: the script to store
        @type content: L{str}
        """
        assert isinstance(path, str)
        assert isinstance(title, str)
        self.path = path
        self.title = title
        self.content = content


class Redirect(RenderedObject):
    """
    This class holds redirect information.

    @ivar source: source path
    @type source: L{str}
    @ivar target: target path to redirect to
    @type target: L{str}
    @ivar title: title of the redirect
    @type title: L{str}
    @ivar is_front: True if this is a front article
    @type is_front: L{bool}
    """
    def __init__(self, source, target, title, is_front=False):
        """
        The default constructor.

        @param source: source path
        @type source: L{str}
        @param target: target path to redirect to
        @type target: L{str}
        @param title: title of the redirect
        @type title: L{str}
        @param is_front: True if this is a front article
        @type is_front: L{bool}
        """
        self.source = source
        self.target = target
        self.title = title
        self.is_front = is_front


class RenderResult(object):
    """
    This class encapsulates a list of  multiple L{RenderedObject},
    which together make up a rendered result.

    @ivar _objects: list of the rendered objects
    @type _objects: L{list} of L{RenderedObject}
    """
    def __init__(self, objects=None):
        """
        The default constructor.

        @param objects: list of the rendered objects or a rendered object, if any
        @type objects: L{None} or L{RenderedObject} or L{list} of L{RenderedObject}
        """
        if objects is None:
            self._objects = []
        elif isinstance(objects, RenderedObject):
            self._objects = [objects]
        elif isinstance(objects, (tuple, list)):
            self._objects = list(objects)
        else:
            raise TypeError("Expected None, RenderedObject or list/tuple of RenderedObject, got {} instead!".format(repr(objects)))

    def add(self, obj):
        """
        Add an object to the result.

        @param object: object to add
        @type object: L{RenderedObject}
        """
        self._objects.append(obj)

    def iter_objects(self):
        """
        Iterate over the objects in this result.

        @yields: the objects in this result
        @ytype: L{RenderedObject}
        """
        for obj in self._objects:
            yield obj


class RenderOptions(object):
    """
    Options for the renderer.

    @ivar include_external_links: whether external links should be included
    @type include_external_links: L{bool}
    """
    def __init__(self, include_external_links=False):
        """
        The default constructor.

        @param include_external_links: whether external links should be included
        @type include_external_links: L{bool}
        """
        self.include_external_links = include_external_links


class HtmlRenderer(object):
    """
    The HTML renderer renders HTML pages for various objects.

    @ivar environment: the jinja2 environment used to render templates
    @type environment: L{jinja2.environment}
    @ivar options: render options
    @type options: L{RenderOptions}
    """
    def __init__(self, options):
        """
        The default constructor.

        @param options: render options
        @type options: L{RenderOptions}
        """
        assert isinstance(options, RenderOptions)
        self.options = options

        # setup jinja environment
        self.environment = Environment(
            loader=PackageLoader("zimfiction.zimbuild"),
            auto_reload=False,
            autoescape=select_autoescape(),
        )

        # configure environment globals
        self.environment.globals["options"] = self.options

        # configure filters
        self.environment.filters["render_storytext"] = self._render_storytext_filter
        self.environment.filters["format_number"] = format_number
        self.environment.filters["format_size"] = format_size
        self.environment.filters["normalize_tag"] = self._normalize_tag
        self.environment.filters["format_date"] = self._format_date
        self.environment.filters["first_elements"] = self._first_elements

        # configure tests
        self.environment.tests["date"] = self._is_date

    @staticmethod
    def minify_html(s):
        """
        Minify html code.

        @param s: html code to minify
        @type s: L{str}
        @return: the minified html
        @rtype: L{str}
        """
        if minify_html is None:
            # fall back to htmlmin
            return htmlmin.minify(
                s,
                remove_comments=True,
                remove_empty_space=True,
                reduce_boolean_attributes=True,
                remove_optional_attribute_quotes=True,
            )
        else:
            return minify_html.minify(
                s,
            )

    def render_story(self, story):
        """
        Render a story.

        @param story: story to render
        @type story: L{zimfiction.db.models.Story}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        # NOTE: not keeping track of items per result here
        # -> stories with 198+ chapters are relatively rare and shouldn't cause RAM problems
        result = RenderResult()
        chapter_template = self.environment.get_template("chapter.html.jinja")
        min_chapter_i = None
        is_first = True
        for chapter in story.chapters:
            chapter_page = chapter_template.render(
                chapter=chapter,
                is_first=is_first,
                to_root="../../..",
            )
            result.add(
                HtmlPage(
                    path="story/{}/{}/{}".format(story.publisher.name, story.id, chapter.index),
                    title="{} by {} - Chapter {} - {}".format(story.title, story.author.name, chapter.index, chapter.title),
                    content=self.minify_html(chapter_page),
                    is_front=False,  # redirect to first chapter will be front
                ),
            )
            # keep track of lowest chapter index so we can redirect to it
            if (min_chapter_i is None) or (chapter.index < min_chapter_i):
                min_chapter_i = chapter.index
            is_first = False
        # add redirect from story -> page 1
        result.add(
            Redirect(
                "story/{}/{}/".format(story.publisher.name, story.id),
                "story/{}/{}/{}".format(story.publisher.name, story.id, min_chapter_i),
                title="{} by {} on {}".format(story.title, story.author.name, story.publisher.name),
                is_front=True,
            ),
        )
        # add index
        chapter_index_template = self.environment.get_template("chapter_index.html.jinja")
        chapter_index_page = chapter_index_template.render(
            story=story,
            to_root="../../..",
        )
        result.add(
            HtmlPage(
                path="story/{}/{}/index".format(story.publisher.name, story.id),
                content=self.minify_html(chapter_index_page),
                title="{} by {} on {} - List of chapters".format(story.title, story.author.name, story.publisher.name),
                is_front=False,
            ),
        )
        # add preview json
        result.add(
            JsonObject(
                path="story/{}/{}/preview.json".format(story.publisher.name, story.id),
                content=story.get_preview_data(),
                title="",
            ),
        )
        return result

    def render_tag(self, tag, stories=None, num_stories=None, statistics=None):
        """
        Render a tag.

        If stories is specified, it should be an iterable yielding lists
        of stories sorted by (score, total_words) descending. If it is
        not specified, it will be generated from tag.stories

        @param tag: tag to render
        @type tag: L{zimfiction.db.models.Tag}
        @param stories: an iterable yielding the stories in the tag in a sorted order as described above
        @type stories: iterable yielding L{zimfiction.db.models.Story} or L{None}
        @param num_stories: number of stories in this tag
        @type num_stories: L{int} or L{None}
        @param statistics: if specified, use these statistics rather than collecting them
        @type statistics: L{zimfiction.statistics.StoryListStats}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        # general preparations
        if stories is None:
            num_stories = len(tag.stories)
            stories = sorted(tag.stories, key=lambda x: (x.score, x.total_words), reverse=True)
        else:
            assert num_stories is not None
        result = RenderResult()
        items_in_result = 0
        if num_stories == 0:
            # tag has no stories
            # this can happen if a tag is only implied
            # we do not return any page in this case
            return result
        # default redirect to page 1
        result.add(
            Redirect(
                "tag/{}/{}/".format(tag.type, normalize_tag(tag.name)),
                "tag/{}/{}/1".format(tag.type, normalize_tag(tag.name)),
                title="Stories tagged '{}' [{}]".format(tag.name, tag.type),
                is_front=True,
            ),
        )
        items_in_result += 1
        # prepare rendering the story list pages
        list_page_template = self.environment.get_template("storylistpage.html.jinja")
        include_search = (num_stories >= MIN_STORIES_FOR_SEARCH) and (num_stories <= MAX_STORIES_FOR_SEARCH)
        include_stats = True
        collect_stats = (statistics is None) and include_stats
        if collect_stats:
            stat_creator = StoryListStatCreator()
        num_pages = math.ceil(num_stories / STORIES_PER_PAGE)
        bucketmaker = BucketMaker(STORIES_PER_PAGE)
        if include_search:
            search_creator = SearchMetadataCreator(max_page_size=SEARCH_ITEMS_PER_FILE)
        # render the story list pages
        page_index = 1
        for story in stories:
            if collect_stats:
                stat_creator.feed(story)
            if include_search:
                search_creator.feed(story)
            bucket = bucketmaker.feed(story)
            if bucket is not None:
                items_in_result += self._render_tag_page(
                    tag=tag,
                    stories=bucket,
                    page_index=page_index,
                    num_pages=num_pages,
                    template=list_page_template,
                    result=result,
                    include_search=include_search,
                )
                if items_in_result >= MAX_ITEMS_PER_RESULT:
                    yield result
                    result = RenderResult()
                    items_in_result = 0
                page_index += 1
        bucket = bucketmaker.finish()
        if bucket is not None:
            items_in_result += self._render_tag_page(
                tag=tag,
                stories=bucket,
                page_index=page_index,
                num_pages=num_pages,
                template=list_page_template,
                result=result,
                include_search=include_search,
            )
            if items_in_result >= MAX_ITEMS_PER_RESULT:
                yield result
                result = RenderResult()
                items_in_result = 0
        # add statistics
        if collect_stats:
            statistics = stat_creator.get_stats()
        if include_stats:
            stats_page_template = self.environment.get_template("storyliststatspage.html.jinja")
            page = stats_page_template.render(
                to_root="../../..",
                title="Stories tagged '{}' [{}] - Statistics".format(tag.name, tag.type),
                stats=statistics,
                backref="1",
            )
            result.add(
                HtmlPage(
                    path="tag/{}/{}/stats".format(tag.type, normalize_tag(tag.name)),
                    content=self.minify_html(page),
                    title="Stories tagged '{}' [{}] - Statistics".format(tag.name, tag.type),
                    is_front=False
                )
            )
            result.add(
                JsonObject(
                    path="tag/{}/{}/storyupdates.json".format(tag.type, normalize_tag(tag.name)),
                    title="",
                    content=statistics.timeline,
                ),
            )
            items_in_result += 2
        # add search
        if include_search:
            search_header_data = search_creator.get_search_header()
            result.add(
                JsonObject(
                    path="tag/{}/{}/search_header.json".format(tag.type, normalize_tag(tag.name)),
                    title="",
                    content=search_header_data,
                ),
            )
            items_in_result += 1
            for i, search_data in search_creator.iter_search_pages():
                result.add(
                    JsonObject(
                        path="tag/{}/{}/search_content_{}.json".format(tag.type, normalize_tag(tag.name), i),
                        title="",
                        content=search_data,
                    ),
                )
                items_in_result += 1
                if items_in_result >= MAX_ITEMS_PER_RESULT:
                    yield result
                    result = RenderResult()
                    items_in_result = 0
        yield result

    def _render_tag_page(self, tag, stories, page_index, num_pages, template, result, include_search):
        """
        Helper function for rendering a tag page of stories.

        This function renders a page of stories in the tag and adds the
        rendered page to the result.

        @param tag: tag this page is for
        @type tag: L{zimfiction.db.models.Tag}
        @param stories: list of stories that should be listed on this page
        @type stories: L{list} of L{zimfiction.db.models.Story}
        @param page_index: index of current page (1-based)
        @type page_index: L{int}
        @param num_pages: total number of pages
        @type num_pages: L{int}
        @param template: template that should be rendered
        @type template: L{jinja2.Template}
        @param result: result the rendered page should be added to
        @type result: L{RenderResult}
        @param include_search: whether search should be included for this tag
        @type include_search: L{bool}
        @return: the number of items added to the render result
        @rtype: L{int}
        """
        page = template.render(
            to_root="../../..",
            title="Stories tagged '{}' [{}] - Page {}".format(tag.name, tag.type, page_index),
            stories=stories,
            include_search=(include_search and (page_index == 1 or not SEARCH_ONLY_ON_FIRST_PAGE)),
            num_pages=num_pages,
            cur_page=page_index,
        )
        result.add(
            HtmlPage(
                path="tag/{}/{}/{}".format(tag.type, normalize_tag(tag.name), page_index),
                content=self.minify_html(page),
                title="Stories tagged '{}' [{}] - Page {}".format(tag.name, tag.type, page_index),
                is_front=False,
            ),
        )
        return 1  # 1 item added

    def render_author(self, author):
        """
        Render an author.

        @param author: author to render
        @type author: L{zimfiction.db.models.Author}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        # NOTE: not keeping track of items per result here
        # -> authors with MAX_ITEMS_PER_RESULT*STORIES_PER_PAGE are rare
        #    and should not cause memory problems
        result = RenderResult()
        bucketmaker = BucketMaker(STORIES_PER_PAGE)
        result.add(
            Redirect(
                "author/{}/{}/".format(author.publisher.name, normalize_tag(author.name)),
                "author/{}/{}/1".format(author.publisher.name, normalize_tag(author.name)),
                title="Author {} on {}".format(author.name, author.publisher.name),
                is_front=True,
            ),
        )
        list_page_template = self.environment.get_template("author.html.jinja")
        pages = []
        stat_creator = StoryListStatCreator()
        for story in sorted(author.stories, key=lambda x: x.published, reverse=True):
            stat_creator.feed(story)
            bucket = bucketmaker.feed(story)
            if bucket is not None:
                pages.append(bucket)
        bucket = bucketmaker.finish()
        if bucket is not None:
            pages.append(bucket)
        if not pages:
            # for some reason, it can happen that an author does not
            # have any associated stories. This is most likely a bug
            # probably somewhere in the import
            # Until that one is fixed, we need to ensure that there's
            # always at least on (perhaps empty) page for each author
            # otherwise some redirects and links won't work correctly
            pages.append([])
        stats = stat_creator.get_stats()
        for i, stories in enumerate(pages, start=1):
            page = list_page_template.render(
                to_root="../../..",
                author=author,
                stories=stories,
                stats=stats,
                num_pages=len(pages),
                cur_page=i,
            )
            result.add(
                HtmlPage(
                    path="author/{}/{}/{}".format(author.publisher.name, normalize_tag(author.name), i),
                    content=self.minify_html(page),
                    title="Author {} on {} - Page {}".format(author.name, author.publisher.name, i),
                    is_front=False,
                ),
            )
        result.add(
            JsonObject(
                path="author/{}/{}/storyupdates.json".format(author.publisher.name, normalize_tag(author.name)),
                title="",
                content=stats.timeline,
            )
        )
        return result


    def render_category(self, category, stories=None, num_stories=None, statistics=None):
        """
        Render an category.

        If stories is specified, it should be an iterable yielding lists
        of stories sorted by (score, total_words) descending. If it is
        not specified, it will be generated from category.stories

        @param category: category to render
        @type category: L{zimfiction.db.models.Category}
        @param stories: an iterable yielding the stories in the category in a sorted order as described above
        @type stories: iterable yielding L{zimfiction.db.models.Story} or L{None}
        @param num_stories: number of stories in this category
        @type num_stories: L{int} or L{None}
        @param statistics: if specified, use these statistics rather than collecting them
        @type statistics: L{zimfiction.statistics.StoryListStats}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        # general preparations
        if stories is None:
            num_stories = len(category.stories)
            stories = sorted(category.stories, key=lambda x: (x.score, x.total_words), reverse=True)
        else:
            assert num_stories is not None
        result = RenderResult()
        items_in_result = 0
        if num_stories == 0:
            # tag has no stories
            # this can happen if a tag is only implied
            # we do not return any page in this case
            return result
        # default redirect to page 1
        result.add(
            Redirect(
                "category/{}/{}/".format(category.publisher.name, normalize_tag(category.name)),
                "category/{}/{}/1".format(category.publisher.name, normalize_tag(category.name)),
                title="Category: {} on {}".format(category.name, category.publisher.name),
                is_front=True,
            ),
        )
        items_in_result += 1
        # prepare rendering the story list pages
        list_page_template = self.environment.get_template("storylistpage.html.jinja")
        include_search = (num_stories >= MIN_STORIES_FOR_SEARCH) and (num_stories <= MAX_STORIES_FOR_SEARCH)
        include_stats = True
        collect_stats = (statistics is None) and include_stats
        if collect_stats:
            stat_creator = StoryListStatCreator()
        num_pages = math.ceil(num_stories / STORIES_PER_PAGE)
        bucketmaker = BucketMaker(STORIES_PER_PAGE)
        if include_search:
            search_creator = SearchMetadataCreator(max_page_size=SEARCH_ITEMS_PER_FILE)
        # render the story list pages
        page_index = 1
        for story in stories:
            if collect_stats:
                stat_creator.feed(story)
            if include_search:
                search_creator.feed(story)
            bucket = bucketmaker.feed(story)
            if bucket is not None:
                items_in_result += self._render_category_page(
                    category=category,
                    stories=bucket,
                    page_index=page_index,
                    num_pages=num_pages,
                    template=list_page_template,
                    result=result,
                    include_search=include_search,
                )
                if items_in_result >= MAX_ITEMS_PER_RESULT:
                    yield result
                    result = RenderResult()
                    items_in_result = 0
                page_index += 1
        bucket = bucketmaker.finish()
        if bucket is not None:
            items_in_result += self._render_category_page(
                category=category,
                stories=bucket,
                page_index=page_index,
                num_pages=num_pages,
                template=list_page_template,
                result=result,
                include_search=include_search,
            )
            if items_in_result >= MAX_ITEMS_PER_RESULT:
                yield result
                result = RenderResult()
                items_in_result = 0
        # add statistics
        if collect_stats:
            statistics = stat_creator.get_stats()
        if include_stats:
            stats_page_template = self.environment.get_template("storyliststatspage.html.jinja")
            page = stats_page_template.render(
                to_root="../../..",
                title="{} fanfiction on {} - Statistics".format(category.name, category.publisher.name),
                stats=statistics,
                backref="1",
            )
            result.add(
                HtmlPage(
                    path="category/{}/{}/stats".format(category.publisher.name, normalize_tag(category.name)),
                    content=self.minify_html(page),
                    title="{} fanfiction on {} - Statistics".format(category.name, category.publisher.name),
                    is_front=False
                )
            )
            result.add(
                JsonObject(
                    path="category/{}/{}/storyupdates.json".format(category.publisher.name, normalize_tag(category.name)),
                    title="",
                    content=statistics.timeline,
                )
            )
            items_in_result += 2
        # add search
        if include_search:
            search_header_data = search_creator.get_search_header()
            result.add(
                JsonObject(
                    path="category/{}/{}/search_header.json".format(category.publisher.name, normalize_tag(category.name)),
                    title="",
                    content=search_header_data,
                ),
            )
            for i, search_data in search_creator.iter_search_pages():
                result.add(
                    JsonObject(
                        path="category/{}/{}/search_content_{}.json".format(category.publisher.name, normalize_tag(category.name), i),
                        title="",
                        content=search_data,
                    ),
                )
                items_in_result += 1
                if items_in_result >= MAX_ITEMS_PER_RESULT:
                    yield result
                    result = RenderResult()
                    items_in_result = 0
        yield result

    def _render_category_page(self, category, stories, page_index, num_pages, template, result, include_search):
        """
        Helper function for rendering a category page of stories.

        This function renders a page of stories in the category and adds the
        rendered page to the result.

        @param category: category this page is for
        @type category: L{zimfiction.db.models.Category}
        @param stories: list of stories that should be listed on this page
        @type stories: L{list} of L{zimfiction.db.models.Story}
        @param page_index: index of current page (1-based)
        @type page_index: L{int}
        @param num_pages: total number of pages
        @type num_pages: L{int}
        @param template: template that should be rendered
        @type template: L{jinja2.Template}
        @param result: result the rendered page should be added to
        @type result: L{RenderResult}
        @param include_search: whether search should be included for this category
        @type include_search: L{bool}
        @return: the number of items added to the render result
        @rtype: L{int}
        """
        page = template.render(
            to_root="../../..",
            title="{} fanfiction on {} - Page {}".format(category.name, category.publisher.name, page_index),
            category=category,
            stories=stories,
            include_search=(include_search and (page_index == 1 or not SEARCH_ONLY_ON_FIRST_PAGE)),
            num_pages=num_pages,
            cur_page=page_index,
        )
        result.add(
            HtmlPage(
                path="category/{}/{}/{}".format(category.publisher.name, normalize_tag(category.name), page_index),
                content=self.minify_html(page),
                title="{} fanfiction on {} - Page {}".format(category.name, category.publisher.name, page_index),
                is_front=False,
            ),
        )
        return 1  # 1 item added


    def render_series(self, series):
        """
        Render an series.

        @param series: series to render
        @type series: L{zimfiction.db.models.Series}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        series_template = self.environment.get_template("series.html.jinja")
        stats = StoryListStatCreator.get_stats_from_iterable(series.stories)
        page = series_template.render(
            to_root="../../..",
            series=series,
            stats=stats,
        )
        result.add(
            HtmlPage(
                path="series/{}/{}/".format(series.publisher.name, normalize_tag(series.name)),
                content=self.minify_html(page),
                title="Series: '{}' on {}".format(series.name, series.publisher.name),
                is_front=True,
            ),
        )
        result.add(
            JsonObject(
                path="series/{}/{}/storyupdates.json".format(series.publisher.name, normalize_tag(series.name)),
                title="",
                content=stats.timeline,
            )
        )
        return result

    def render_publisher(self, publisher, stories=None, statistics=None):
        """
        Render a publisher.

        If stories is specified, it should be an iterable of stories
        in this publisher. It defaults to publisher.stories

        @param publisher: publisher to render
        @type publisher: L{zimfiction.db.models.Publisher}
        @param stories: stories in this publisher
        @type stories: iterable of L{zimfiction.db.models.Story}
        @param statistics: if specified, use these statistics rather than collecting them
        @type statistics: L{zimfiction.statistics.StoryListStats}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        if stories is None:
            stories = publisher.stories
        # NOTE: also not keeping track of items in result here
        # -> items in publisher depend on number of categories, which
        #    individually should not take enough RAM to cause memory
        #    problems in mass
        # TODO: currently, we avoid empty category pages by having the
        # worker only load  categories having at least one story for
        # which the category is not implied. This is quite ugly, we
        # should replace this behavior in the future
        result = RenderResult()
        publisher_template = self.environment.get_template("publisher.html.jinja")
        include_stats = True
        collect_stats = (statistics is None) and include_stats
        if collect_stats:
            statistics = StoryListStatCreator.get_stats_from_iterable(stories)
        page = publisher_template.render(
            to_root="../..",
            publisher=publisher,
            stats=statistics,
            n_categories=CATEGORIES_ON_PUBLISHER_PAGE,
        )
        result.add(
            HtmlPage(
                path="publisher/{}/".format(publisher.name),
                content=self.minify_html(page),
                title="Publisher: {}".format(publisher.name),
                is_front=True,
            ),
        )
        if include_stats:
            result.add(
                JsonObject(
                    path="publisher/{}/storyupdates.json".format(publisher.name),
                    title="",
                    content=statistics.timeline,
                )
            )
        # category pages
        bucketmaker = BucketMaker(CATEGORIES_PER_PAGE)
        categories = []
        for category in sorted(publisher.categories, key=lambda c: c.name):
            bucket = bucketmaker.feed(category)
            if bucket is not None:
                categories.append(bucket)
        bucket = bucketmaker.finish()
        if bucket is not None:
            categories.append(bucket)
        category_page_template = self.environment.get_template("category_long_list_page.html.jinja")
        for i, categorylist in enumerate(categories, start=1):
            page = category_page_template.render(
                to_root="../../..",
                categories=categorylist,
                title="Categories - Page {} of {}".format(i, len(categories)),
                cur_page=i,
                num_pages=len(categories),
            )
            result.add(
                HtmlPage(
                    path="publisher/{}/categories/{}".format(publisher.name, i),
                    content=self.minify_html(page),
                    title="Categories: {} - Page {}".format(publisher.name, i),
                    is_front=False,
                ),
            )
        return result

    def render_index(self, publishers):
        """
        Render the indexpage.

        @param publishers: list of publishers
        @type publishers: L{list}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        index_template = self.environment.get_template("index.html.jinja")
        page = index_template.render(
            to_root=".",
            publishers=publishers,
        )
        result.add(
            HtmlPage(
                path="index.html",
                content=self.minify_html(page),
                title="Welcome to ZimFiction!",
                is_front=True,
            ),
        )
        return result


    def render_global_stats(self, stats):
        """
        Render the global statistic page.

        @param stats: statistics to render
        @type stats: L{zimfiction.statistics.StoryListStats}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        stats_template = self.environment.get_template("storyliststatspage.html.jinja")
        page = stats_template.render(
            to_root=".",
            title="Global Statistics",
            stats=stats,
            backref=None,
        )
        result.add(
            HtmlPage(
                path="statistics.html",
                content=self.minify_html(page),
                title="Global Statistics",
                is_front=True,
            ),
        )
        result.add(
            JsonObject(
                path="storyupdates.json",
                title="",
                content=stats.timeline,
            )
        )
        return result

    def render_search_script(self):
        """
        Generate the search script.

        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        path = get_resource_file_path("search.js")
        with open(path, "r", encoding="utf-8") as fin:
            script = fin.read()
        result.add(
            Script(
                path="scripts/search.js",
                content=script,
                title="Search script",
            ),
        )
        return result

    def render_chart_scripts(self):
        """
        Generate the chart scripts.

        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        # chartjs
        path = get_resource_file_path("chartjs", "chart.js")
        with open(path, "r", encoding="utf-8") as fin:
            script = fin.read()
        result.add(
            Script(
                path="scripts/chart.js",
                content=script,
                title="Chart.js",
            ),
        )
        # storytimechart
        path = get_resource_file_path("storytimechart.js")
        with open(path, "r", encoding="utf-8") as fin:
            script = fin.read()
        result.add(
            Script(
                path="scripts/storytimechart.js",
                content=script,
                title="storytimechart.js",
            ),
        )
        return result

    def render_info_pages(self):
        """
        Render the info pages.

        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        # general info page
        info_template = self.environment.get_template("info.html.jinja")
        info_page = info_template.render(
            to_root="..",
        )
        result.add(
            HtmlPage(
                path="info/index.html",
                content=self.minify_html(info_page),
                title="Informations",
                is_front=True,
            ),
        )
        result.add(
            Redirect(
                "info/",
                "info/index.html",
                title="Informations",
                is_front=False,
            ),
        )
        # acknowledgements
        ack_template = self.environment.get_template("acknowledgements.html.jinja")
        licenses = {}
        with open(get_resource_file_path("chartjs", "LICENSE.md")) as fin:
            licenses["chart.js"] = fin.read()
        ack_page = ack_template.render(
            to_root="..",
            licenses=licenses,
        )
        result.add(
            HtmlPage(
                path="info/acknowledgements.html",
                content=self.minify_html(ack_page),
                title="Acknowledgements",
                is_front=True,
            ),
        )
        return result

    # =========== filters ===============

    def _render_storytext_filter(self, value):
        """
        Render a storytext, returning the rendered html.

        @param value: story text to render
        @type value: L{str}
        @return: the rendered HTML of the story text
        @rtype: L{str}
        """
        return mistune.html(value)

    def _normalize_tag(self, value):
        """
        Like L{zimfiction.util.normalize_tag}, but also quote the value

        @param value: tag name to normalize
        @type value: L{str}
        @return: the normalized, encoded tag
        @rtype: L{str}
        """
        return urllib.parse.quote_plus(normalize_tag(value))

    def _format_date(self, value):
        """
        Format a date.

        @param value: date to format
        @type value: L{datetime.datetime}
        @return: the formated date
        @rtype: L{str}
        """
        return value.strftime("%Y-%m-%d")

    def _first_elements(self, value, n):
        """
        Return the first n elements in a value

        @param value: list whose first elements should be returned
        @type value: L{list} or L{tuple}
        @param n: number of elements to return
        @type n: L{int}
        @return: the first n elements in value
        @rtype: L{list}
        """
        return list(value)[:n]

    # =========== tests ===============

    def _is_date(self, obj):
        """
        Return True if obj is a date or datetime.

        @param obj: object to check
        @type obj: any
        @return: True if obj is a date or datetime
        @rtype: L{bool}
        """
        return isinstance(obj, (datetime.date, datetime.datetime))

