"""
An L{zimfiction.implication.finder.ImplicationFinder} for finding
exclamation mark based tags.

Exclamation mark based tags are found in summaries and have the form
mod1!mod2...!base. For example, a summary containing "a!b!c" implies
the tags:

    - a!b!c
    - a!c
    - b!c

"""
import itertools

from .finder import ImplicationFinder


class ExclamationTagFinder(ImplicationFinder):
    """
    An ImplicationFinder extracting exclamation based tags from the story summary.
    """
    def get_implied_tags(self, story, implied_tags):
        tags = []
        words = self._split_words(story.summary)
        for word in words:
            # remove starting and end exclamation marks
            # this should already be done by _split_words(), but it can't
            # hurt to be sure
            while word.startswith("!"):
                word = word[1:]
            while word.endswith("!"):
                word = word[:-1]
            # if word does not still contain at least one exclamation mark, skip it
            if word.count("!") == 0:
                continue
            tags.append(word)
            splitted = word.split("!")
            modifiers, base = splitted[:-1], splitted[-1]
            for c in self._all_combinations(modifiers):
                tag = "!".join(sorted(c)) + "!" + base
                tags.append(tag)

        implied_tags = [("genre", t) for t in tags]
        return implied_tags

    @staticmethod
    def _all_combinations(iterable):
        """
        Return all combinations of subsequences, excluding the empty one.

        Based on the itertools powerset recipe.

        Example:
            _all_combinations((1, 2, 3)) -> (1), (2), (3), (1, 2), (1, 3),
                (2, 3), (1, 2, 3)

        @param iterable: iterable to get combinations for
        @type iterable: an iterable, duh
        @return: an iterable of all combinations except the empty one.
        @rtype: an iterable
        """
        s = list(iterable)
        return itertools.chain.from_iterable(itertools.combinations(s, r) for r in range(1, len(s)+1))

    @staticmethod
    def _split_words(s):
        """
        Split "s" into words, removing punctuation.

        Also removes html tags from the words as some summaries contain html.

        @param s: string to split
        @type s: L{str}
        @return: the words
        @rtype: L{str}
        """
        words = []
        splitted = s.split(" ")
        for word in splitted:
            # remove punctuation
            for c in (".", ",", "?", "!", "'", '"', ":", ";", "*", "(", ")", "[", "]", "<", ">"):
                while word.endswith(c):
                    word = word[:-1]
                while word.startswith(c):
                    word = word[1:]
            # remove extra html tags
            # remember: leading and trailing <> have already been removed
            if "<" in word:
                word = word[:word.find("<")]
            if ">" in word:
                word = word[word.find(">")+1:]
            # clean up the word
            word = word.strip()
            if word:
                words.append(word)
        return words
