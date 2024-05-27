"""
Module for evaluating statistics.
"""


def zerodiv(a, b):
    """
    Calculate a/b if b != 0 else return 0.

    @param a: number to divide
    @type a: L{int} or L{float}
    @param b: number to divide by
    @type b: L{int} or L{float}
    @return: a/b or 0
    @rtype: L{int} or L{float}
    """
    if b == 0:
        return 0
    return a/b


class Counter(object):
    """
    A simple class for incrementally counting the number of objects seen.

    @ivar count: number of objects seen
    @type count: L{int}
    """
    def __init__(self):
        """
        The default constructor.
        """
        self.count = 0

    def feed(self, element):
        """
        Process an element.

        @param element: element to process
        @type element: L{any}
        """
        self.count += 1


class IntCounter(Counter):
    """
    An extension of L{Counter} for counting integers while collecting
    further statistics like min, max and sum.

    @ivar min: minimum value encountered
    @type min: L{int}
    @ivar max: maximum value encountered
    @type max: L{int}
    @ivar sum: sum of values encountered
    @type sum: L{int}
    """
    def __init__(self):
        Counter.__init__(self)
        self.min = None
        self.max = None
        self.sum = 0

    def feed(self, element):
        """
        Process an element.

        @param element: element to process
        @type element: L{int}
        """
        assert isinstance(element, int)
        Counter.feed(self, element)
        self.min = (element if self.min is None else min(self.min, element))
        self.max = (element if self.max is None else max(self.max, element))
        self.sum += element

    @property
    def average(self):
        """
        The average value of the elements.

        @return: the average value of the elements (sum/count)
        @rtype: L{float}
        """
        return zerodiv(self.sum, self.count)


class UniqueCounter(Counter):
    """
    An extension of L{Counter} for also counting the numbers of unique hashable elements.
    """
    def __init__(self):
        Counter.__init__(self)
        self._encountered = set()

    def feed(self, element):
        """
        Process an element.

        @param element: element to process
        @type element: hashable
        """
        Counter.feed(self, element)
        self._encountered.add(element)

    @property
    def unique_count(self):
        """
        The number of unique elements encountered.

        @return: the number of unique elements encountered
        @rtype: L{int}
        """
        return len(self._encountered)


class _StatCreator(object):
    """
    A base class for generating statistics incrementally.
    """
    def feed(self, element):
        """
        Process an element.

        @param element: element to process
        @type element: any
        """
        pass

    @classmethod
    def from_iterable(cls, iterable):
        """
        Return a new instance fed with all elements in the iterable.

        @param iterable: iterable of elements to feed into the stat creator
        @type iterable: see the 'feed' method of the same class
        @return: a new instance of this class, fed with all the elements in the iterabke
        @rtype: instance of cls
        """
        creator = cls()
        for element in iterable:
            creator.feed(element)
        return creator

    @classmethod
    def get_stats_from_iterable(cls, iterable):
        """
        A shorthand for calling L{_StatCreator.from_iterable} and then calling L{_StatCreator.get_stats}.

        @param iterable: iterable of elements to feed into the stat creator
        @type iterable: see the 'feed' method of the same class
        @return: the collected statistics
        @rtype: see the 'get_stats' method of the same class
        """
        return cls.from_iterable(iterable).get_stats()

    def get_stats(self):
        """
        Return the collected statistics.

        @return: the collected statistics
        @rtype: L{_Stats}
        """
        raise NotImplementedError("Must be implemented by subclasses!")


class _Stats(object):
    """
    Base class for statistic results.
    """
    pass


class StoryListStats(_Stats):
    """
    The collected statistics of a list of stories.

    @ivar story_count: number of stories
    @type story_count: L{int}

    @ivar total_words: total words of stories
    @type total_words: L{int}
    @ivar min_story_words: number of words in the shortest story
    @type min_story_words: L{int}
    @ivar max_story_words: number of words in the longest story
    @type max_story_words: L{int}
    @ivar average_story_words: average number of words in a story
    @type average_story_words: L{int}

    @ivar chapter_count: number of chapters
    @type chapter_count: L{int}
    @ivar min_chapter_count: min number of chapters in a story
    @type min_chapter_count: L{float}
    @ivar max_chapter_count: max number of chapters in a story
    @type max_chapter_count: L{float}
    @ivar average_chapter_count: average number of chapters in a story
    @type average_chapter_count: L{float}

    @ivar min_chapter_words: number of words in the shortest chapter
    @type min_chapter_words: L{int}
    @ivar max_chapter_words: number of words in the longest chapter
    @type max_chapter_words: L{int}
    @ivar average_chapter_words: average number of words in a chapter
    @type average_chapter_words: L{int}

    @ivar category_count: number of unique categories encountered
    @type category_count: L{int}
    @ivar total_category_count: total (non-unqiue) number of categories encountered
    @type total_category_count: L{int}
    @ivar average_category_count: average number of categories per story
    @type average_category_count: L{float}

    @ivar tag_count: number of unique tags encountered
    @type tag_count: L{int}
    @ivar total_tag_count: total (non-unqiue) number of tags encountered
    @type total_tag_count: L{int}
    @ivar average_tag_count: average number of tags per story
    @type average_tag_count: L{float}

    @ivar author_count: number of unique authors encountered
    @type author_count: L{int}
    @ivar total_author_count: total (non-unqiue) number of authors encountered
    @type total_author_count: L{int}
    @ivar average_author_count: average number of categories per story
    @type average_author_count: L{float}
    @ivar average_stories_per_author: average number of stories per author
    @type average_stories_per_author: L{float}

    @ivar series_count: number of unique series encountered
    @type series_count: L{int}
    @ivar total_series_count: total (non-unique) number of series encountered
    @type total_series_count: L{int}
    """
    def __init__(
        self,
        story_count,
        total_words,
        min_story_words,
        max_story_words,

        chapter_count,
        min_chapter_count,
        max_chapter_count,

        min_chapter_words,
        max_chapter_words,

        category_count,
        total_category_count,

        tag_count,
        total_tag_count,

        author_count,
        total_author_count,

        series_count,
        total_series_count,
    ):
        """
        The default constructor.

        @param story_count: number of stories
        @type story_count: L{int}

        @param total_words: total words of stories
        @type total_words: L{int}
        @param min_story_words: number of words in the shortest story
        @type min_story_words: L{int}
        @param max_story_words: number of words in the longest story
        @type max_story_words: L{int}

        @param chapter_count: number of chapters
        @type chapter_count: L{int}
        @param min_chapter_count: min number of chapters in a story
        @type min_chapter_count: L{float}
        @param max_chapter_count: max number of chapters in a story
        @type max_chapter_count: L{float}

        @param min_chapter_words: number of words in the shortest chapter
        @type min_chapter_words: L{int}
        @param max_chapter_words: number of words in the longest chapter
        @type max_chapter_words: L{int}

        @param category_count: number of unique categories encountered
        @type category_count: L{int}
        @param total_category_count: total (non-unqiue) number of categories encountered
        @type total_category_count: L{int}

        @param tag_count: number of unique tags encountered
        @type tag_count: L{int}
        @param total_tag_count: total (non-unqiue) number of tags encountered
        @type total_tag_count: L{int}

        @param author_count: number of unique authors encountered
        @type author_count: L{int}
        @param total_author_count: total (non-unqiue) number of authors encountered
        @type total_author_count: L{int}

        @param series_count: number of unique series encountered
        @type series_count: L{int}
        @param total_series_count: total (non-unique) number of series encountered
        @type total_series_count: L{int}
        """
        self.story_count = story_count
        self.total_words = total_words
        self.min_story_words = min_story_words
        self.max_story_words = max_story_words
        self.average_story_words = zerodiv(self.total_words, self.story_count)

        self.chapter_count = chapter_count
        self.min_chapter_count = min_chapter_count
        self.max_chapter_count = max_chapter_count
        self.average_chapter_count = zerodiv(self.chapter_count, self.story_count)

        self.min_chapter_words = min_chapter_words
        self.max_chapter_words = max_chapter_words
        self.average_chapter_words = zerodiv(self.total_words, self.chapter_count)

        self.category_count = category_count
        self.total_category_count = total_category_count
        self.average_category_count = zerodiv(self.total_category_count, self.story_count)

        self.tag_count = tag_count
        self.total_tag_count = total_tag_count
        self.average_tag_count = zerodiv(self.total_tag_count, self.story_count)

        self.author_count = author_count
        self.total_author_count = total_author_count
        self.average_author_count = zerodiv(self.total_author_count, self.story_count)
        self.average_stories_per_author = zerodiv(self.story_count, self.author_count)

        self.series_count = series_count
        self.total_series_count = total_series_count



class StoryListStatCreator(_StatCreator):
    """
    A class for incrementally generating statistics for a list of stories.
    """
    def __init__(self):
        self._story_word_counter = IntCounter()
        self._chapter_num_counter = IntCounter()
        self._chapter_word_counter = IntCounter()
        self._category_counter = UniqueCounter()
        self._tag_counter = UniqueCounter()
        self._author_counter = UniqueCounter()
        self._series_counter = UniqueCounter()

    def feed(self, element):
        """
        Process a story.

        @param element: story to process
        @type element: L{zimfiction.db.models.Story}
        """
        # make story an alias of element for readability
        story = element
        # feed the counters
        self._story_word_counter.feed(story.total_words)
        self._chapter_num_counter.feed(len(story.chapters))
        for chapter in story.chapters:
            self._chapter_word_counter.feed(chapter.num_words)
        for category in story.categories:
            self._category_counter.feed((category.publisher.name, category.name))
        for tag in story.tags:
            self._tag_counter.feed((tag.type, tag.name))
        self._author_counter.feed((story.author.publisher.name, story.author.name))
        for series in story.series:
            self._series_counter.feed((story.publisher.name, series.name))

    def get_stats(self):
        """
        Return the statistics collected from the story list.

        @return: the collected statistics
        @rtype: L{StoryListStats}
        """
        stats = StoryListStats(
            story_count=self._story_word_counter.count,
            total_words=self._story_word_counter.sum,
            min_story_words=self._story_word_counter.min,
            max_story_words=self._story_word_counter.max,

            chapter_count=self._chapter_num_counter.sum,
            min_chapter_count=self._chapter_num_counter.min,
            max_chapter_count=self._chapter_num_counter.max,

            min_chapter_words=self._chapter_word_counter.min,
            max_chapter_words=self._chapter_word_counter.max,

            category_count=self._category_counter.unique_count,
            total_category_count=self._category_counter.count,

            tag_count=self._tag_counter.unique_count,
            total_tag_count=self._tag_counter.count,

            author_count=self._author_counter.unique_count,
            total_author_count=self._author_counter.count,

            series_count=self._series_counter.unique_count,
            total_series_count=self._series_counter.count,
        )
        return stats
