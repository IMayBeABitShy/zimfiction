"""
This module contains functionality to export a story as a txt file.
"""
from .dumper import Dumper


class TxtDumper(Dumper):
    """
    A dumper for .txt files.

    The output should be similiar to the ones produced by fanficfare.
    """

    def get_encoding(self, story):
        return "utf-8"

    def get_filename(self, story):
        return "story-{}-{}.txt".format(story.publisher.name, story.id)

    def dump(self, story):
        text = self._render_header(story) + "\n\n\n"
        for chapter in story.chapters:
            text += self._render_chapter(chapter)
        text += "End file.\n"
        return text

    def _render_header(self, story):
        """
        Generate the story header, which contains all non-chapter informations.

        @param story: story to get header for
        @type story: l{zimfiction.db.models.Story}
        @return: the header text (be sure to add 3 newlines to it!)
        @rtype: L{str}
        """
        title = "\n\n\n{}\n\nby {}\n\n\n".format(story.title, story.author.name)
        metadata = {
            "Series": ", ".join(["{} of {}".format(sa.index, sa.series.name) for sa in story.series_associations]),
            "Category": ", ".join([category.name for category in story.explicit_categories]),
            "Genre": ", ".join([tag.name for tag in story.genres]),
            "Language": story.language,
            "Status": ("Completed" if story.is_done else "In-Progress"),
            "Published": story.published.isoformat(),
            "Updated": story.updated.isoformat(),
            "Packaged": story.packaged.isoformat(),
            "Rating": story.rating,
            "Warnings": ", ".join([tag.name for tag in story.warnings]),
            "Chapters": str(len(story.chapters)),
            "Words": str(story.total_words),  # slightly different from the original
            "Publisher": story.publisher.name,
            "Story URL":  story.url,
            "Author URL": story.author.url,
            "Author": story.author.name,
            "Characters": ", ".join([tag.name for tag in story.characters]),
            "Relationships": ", ".join([tag.name for tag in story.relationships]),
            "Kudos": str(story.score),
            "Comments": str(story.num_comments),
        }
        header = title + "\n"
        for key, value in metadata.items():
            if (value is None) or (value == ""):
                # value empty, do not add it to output
                continue
            assert isinstance(key, str)
            assert isinstance(value, str)
            header += "{}: {}\n".format(key, value)
        # add summary last
        header += "Summary: {}\n".format(story.summary)
        return header

    def _render_chapter(self, chapter):
        """
        Render a chapter.

        @param chapter: chapter to render
        @type chapter: L{zimfiction.db.models.Chapter}
        @return: the rendered chapter
        @rtype: L{str}
        """
        text = "\t{}. {}\n\n{}".format(chapter.index, chapter.title, chapter.text)
        # end with exactly 3 newlines
        if not text.endswith("\n"):
            text += "\n"
        text += "\n\n"
        return text
