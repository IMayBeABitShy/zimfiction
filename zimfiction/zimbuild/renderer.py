"""
The renderer generates HTML pages.
"""
import urllib.parse
import json

import htmlmin
import mistune
from jinja2 import Environment, PackageLoader, select_autoescape

from ..util import format_size, format_number, format_date, normalize_tag, get_resource_file_path
from ..statistics import StoryListStatCreator
from .buckets import BucketMaker
from .search import SearchMetadataCreator


STORIES_PER_PAGE = 20
CATEGORIES_PER_PAGE = 200
CATEGORIES_ON_PUBLISHER_PAGE = 200
SEARCH_ITEMS_PER_FILE = 50000
MIN_STORIES_FOR_SEARCH = 5
MAX_STORIES_FOR_SEARCH = float("inf")


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


class HtmlRenderer(object):
    """
    The HTML renderer renders HTML pages for various objects.

    @ivar environment: the jinja2 environment used to render templates
    @type environment: L{jinja2.environment}
    """
    def __init__(self):
        """
        The default constructor.
        """
        self.environment = Environment(
            loader=PackageLoader("zimfiction.zimbuild"),
            auto_reload=False,
            autoescape=select_autoescape(),
        )
        self.environment.filters["render_storytext"] = self._render_storytext_filter
        self.environment.filters["format_number"] = format_number
        self.environment.filters["format_size"] = format_size
        self.environment.filters["normalize_tag"] = self._normalize_tag
        self.environment.filters["format_date"] = self._format_date
        self.environment.filters["first_elements"] = self._first_elements

    @staticmethod
    def minify_html(s):
        """
        Minify html code.

        @param s: html code to minify
        @type s: L{str}
        @return: the minified html
        @rtype: L{str}
        """
        return htmlmin.minify(
            s,
            remove_comments=True,
            remove_empty_space=True,
            reduce_boolean_attributes=True,
            remove_optional_attribute_quotes=True,
        )

    def render_story(self, story):
        """
        Render a story.

        @param story: story to render
        @type story: L{zimfiction.db.models.Story}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        chapter_template = self.environment.get_template("chapter.html.jinja")
        min_chapter_i = None
        for chapter in story.chapters:
            chapter_page = chapter_template.render(
                chapter=chapter,
                to_root="../../..",
            )
            result.add(
                HtmlPage(
                    path="story/{}/{}/{}".format(story.publisher.name, story.id, chapter.index),
                    title="{} by {} - Chapter {} - {}".format(story.title, story.author_name, chapter.index, chapter.title),
                    content=self.minify_html(chapter_page),
                    is_front=True,
                ),
            )
            # keep track of lowest chapter index so we can redirect to it
            if (min_chapter_i is None) or (chapter.index < min_chapter_i):
                min_chapter_i = chapter.index
        # add redirect from story -> page 1
        result.add(
            Redirect(
                "story/{}/{}/".format(story.publisher.name, story.id),
                "story/{}/{}/{}".format(story.publisher.name, story.id, min_chapter_i),
                title="{} by {} on {}".format(story.title, story.author_name, story.publisher.name),
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
                title="{} by {} on {} - List of chapters".format(story.title, story.author_name, story.publisher.name),
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

    def render_tag(self, tag):
        """
        Render a tag.

        @param tag: tag to render
        @type tag: L{zimfiction.db.models.Tag}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        bucketmaker = BucketMaker(STORIES_PER_PAGE)
        result.add(
            Redirect(
                "tag/{}/{}/".format(tag.type, normalize_tag(tag.name)),
                "tag/{}/{}/1".format(tag.type, normalize_tag(tag.name)),
                title="Stories tagged '{}' [{}]".format(tag.name, tag.type),
                is_front=True,
            ),
        )
        list_page_template = self.environment.get_template("storylistpage.html.jinja")
        pages = []
        num_stories = 0
        stat_creator = StoryListStatCreator()
        search_creator = SearchMetadataCreator(max_page_size=SEARCH_ITEMS_PER_FILE)
        for story in sorted(tag.stories, key=lambda x: (x.score, x.total_words), reverse=True):
            num_stories += 1
            stat_creator.feed(story)
            search_creator.feed(story)
            bucket = bucketmaker.feed(story)
            if bucket is not None:
                pages.append(bucket)
        bucket = bucketmaker.finish()
        if bucket is not None:
            pages.append(bucket)
        include_search = (num_stories >= MIN_STORIES_FOR_SEARCH) and (num_stories <= MAX_STORIES_FOR_SEARCH);
        for i, stories in enumerate(pages, start=1):
            page = list_page_template.render(
                to_root="../../..",
                title="Stories tagged '{}' [{}]".format(tag.name, tag.type),
                stories=stories,
                include_search=include_search,
                num_pages=len(pages),
                cur_page=i,
            )
            result.add(
                HtmlPage(
                    path="tag/{}/{}/{}".format(tag.type, normalize_tag(tag.name), i),
                    content=self.minify_html(page),
                    title="Stories tagged '{}' [{}]".format(tag.name, tag.type),
                    is_front=False,
                ),
            )
        # add statistics
        stats = stat_creator.get_stats()
        stats_page_template = self.environment.get_template("storyliststatspage.html.jinja")
        page = stats_page_template.render(
            to_root="../../..",
            title="Stories tagged '{}' [{}] - Statistics".format(tag.name, tag.type),
            stats=stats,
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
            for i, search_data in search_creator.iter_search_pages():
                result.add(
                    JsonObject(
                        path="tag/{}/{}/search_content_{}.json".format(tag.type, normalize_tag(tag.name), i),
                        title="",
                        content=search_data,
                    ),
                )
        return result

    def render_author(self, author):
        """
        Render an author.

        @param author: author to render
        @type author: L{zimfiction.db.models.Author}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
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
        return result


    def render_category(self, category):
        """
        Render an category.

        @param category: category to render
        @type category: L{zimfiction.db.models.Category}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        bucketmaker = BucketMaker(STORIES_PER_PAGE)
        result.add(
            Redirect(
                "category/{}/{}/".format(category.publisher.name, normalize_tag(category.name)),
                "category/{}/{}/1".format(category.publisher.name, normalize_tag(category.name)),
                title="Category: {} on {}".format(category.name, category.publisher.name),
                is_front=True,
            ),
        )
        list_page_template = self.environment.get_template("category.html.jinja")
        pages = []
        num_stories = 0
        stat_creator = StoryListStatCreator()
        search_creator = SearchMetadataCreator(max_page_size=SEARCH_ITEMS_PER_FILE)
        for story in sorted(category.stories, key=lambda x: (x.score, x.total_words), reverse=True):
            num_stories += 1
            search_creator.feed(story)
            stat_creator.feed(story)
            bucket = bucketmaker.feed(story)
            if bucket is not None:
                pages.append(bucket)
        bucket = bucketmaker.finish()
        if bucket is not None:
            pages.append(bucket)
        include_search = (num_stories >= MIN_STORIES_FOR_SEARCH) and (num_stories <= MAX_STORIES_FOR_SEARCH)
        for i, stories in enumerate(pages, start=1):
            page = list_page_template.render(
                to_root="../../..",
                category=category,
                stories=stories,
                include_search=include_search,
                num_pages=len(pages),
                cur_page=i,
            )
            result.add(
                HtmlPage(
                    path="category/{}/{}/{}".format(category.publisher.name, normalize_tag(category.name), i),
                    content=self.minify_html(page),
                    title="{} fanfiction on {} - Page {}".format(category.name, category.publisher.name, i),
                    is_front=False,
                ),
            )
        # add statistics
        stats = stat_creator.get_stats()
        stats_page_template = self.environment.get_template("storyliststatspage.html.jinja")
        page = stats_page_template.render(
            to_root="../../..",
            title="{} fanfiction on {} - Statistics".format(category.name, category.publisher),
            stats=stats,
            backref="1",
        )
        result.add(
            HtmlPage(
                path="category/{}/{}/stats".format(category.publisher.name, normalize_tag(category.name)),
                content=self.minify_html(page),
                title="{} fanfiction on {} - Statistics".format(category.publisher.name, category.publisher),
                is_front=False
            )
        )
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
        return result


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
            to_root="../..",
            series=series,
            stats=stats,
        )
        result.add(
            HtmlPage(
                path="series/{}/{}".format(series.publisher.name, normalize_tag(series.name)),
                content=self.minify_html(page),
                title="Series: '{}' on {}".format(series.name, series.publisher.name),
                is_front=True,
            ),
        )
        return result

    def render_publisher(self, publisher):
        """
        Render a publisher.

        @param publisher_name: publisher to render
        @type publisher_name: L{zimfiction.db.models.Publisher}
        @return: the rendered pages and redirects
        @rtype: L{RenderResult}
        """
        result = RenderResult()
        publisher_template = self.environment.get_template("publisher.html.jinja")
        stats = StoryListStatCreator.get_stats_from_iterable(publisher.stories)
        page = publisher_template.render(
            to_root="../..",
            publisher=publisher,
            stats=stats,
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

