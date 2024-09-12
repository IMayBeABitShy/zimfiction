"""
This module contains the epub story parse logic.

@var EPUB_ENCODING: encoding to use to decode epub pages
@type EPUB_ENCODING: L{str}
"""
import re
import tempfile
import os

from html import unescape as html_unescape

import html2text
import ebooklib
from ebooklib import epub

from .raw import RawStory, RawChapter
from ..exceptions import ParseError


EPUB_ENCODING = "utf-8"
TITLE_START_REGEX = re.compile(r"<[aA] href=\".+?\">")
AUTHOR_START_REGEX =  re.compile(r"by <[aA] (class=\".+?\")? href=\".+?\">")
CHAPTER_INDEX_REGEX = re.compile(r"[0-9]+")
CHAPTER_TITLE_REGEX = re.compile(r"class=\"fff_chapter_title\">(.+?)</")


def convert_epub(path):
    """
    Convert an epub story into a raw story.

    @param path: path of epub to read
    @type path: L{str}
    @return: the converted story
    @rtype: L{zimfiction.importer.raw.RawStory}
    """
    book = epub.read_epub(path)
    chapters = []
    metadata = {}
    for document in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        document_name = document.file_name[:document.file_name.rfind(".")]
        document_name = document_name[document_name.rfind("/")+1:]

        if document_name == "title_page":
            # it's the title page, which contains the metadata
            html = document.get_body_content().decode(EPUB_ENCODING)
            header = []
            got_ffftitle = False
            got_title = False
            in_summary = False
            summary = ""
            all_lines = html.splitlines()
            for line_i, rawline in enumerate(all_lines):
                # clean line by removing some html
                if not rawline.endswith("\n"):
                    # always have a trailing newline
                    # will be removed from "line" later on
                    rawline += "\n"
                line = html_unescape(rawline)
                line = line.replace("<b>", "").replace("<B>", "")
                line = line.replace("</b>", "").replace("</B>", "")
                line = line.replace("<div>", "").replace("<DIV>", "")  # note: do not replace <DIV class="...">
                line = line.replace("</div>", "").replace("</DIV>", "")
                line = line.replace("<br/>", "").replace("<BR/>", "").strip()

                next_nonempty_rawline = ""
                for next_rawline in all_lines[line_i + 1:]:
                    if next_rawline.strip():
                        next_nonempty_rawline = next_rawline
                        break

                if (not line) and (not in_summary):
                    continue

                # assert that this epub uses the format the parser was written for
                if line.startswith("<body"):
                    if "fff_titlepage" not in line:
                        raise ParseError("Body line of title page does not contain 'fff_titlepage', this does not seem to be a supported epub format!")
                    got_ffftitle = True
                    continue
                if not got_ffftitle:
                    raise ParseError("Could not find a body line of title that contains 'fff_titlepage', this does not seem to be a supported epub format!")

                if not got_title:
                    # this is likely the title line
                    title_start_i = TITLE_START_REGEX.search(line).end()
                    title = line[title_start_i:]
                    metadata["title"] = title[:title.find("</")]
                    author_start_i = AUTHOR_START_REGEX.search(line).end()
                    author = line[author_start_i:]
                    metadata["author"] = author[:author.find("</")]
                    got_title = True
                elif not in_summary:
                    # metadata
                    if line.lower() == "</body>":
                        # handle special case: no summary
                        if not summary:
                            summary = "[No Summary]"
                        continue
                    if line.lower().startswith("summary"):
                        in_summary = True
                        summary += rawline[rawline.lower().find("</b>")+4:]
                    else:
                        header.append(line)
                else:
                    # summary - ends with </body> or <br />
                    line_contains_br_end = (("<br/ >" in rawline.lower()[-10:]) or ("<br/>" in rawline.lower()[-10:]))
                    if (line.lower() == "</body>") or (line_contains_br_end and "<b>" in next_nonempty_rawline.lower()):
                        in_summary = False
                        if line_contains_br_end:
                            summary += rawline
                        continue
                    else:
                        summary += rawline
            # add extra metadata headers
            if not any([h.startswith("Story URL: ") for h in header]):
                source_url = book.get_metadata("http://purl.org/dc/elements/1.1/", "source")[0][0]
                header.append("Story URL: {}".format(source_url))
            if not any([h.startswith("Publisher: ") for h in header]):
                publisher = book.get_metadata("http://purl.org/dc/elements/1.1/", "publisher")[0][0]
                header.append("Publisher: {}".format(publisher))
            if not any([h.startswith("Packaged: ") for h in header]):
                dates = book.get_metadata("http://purl.org/dc/elements/1.1/", "date")
                for date, datemeta in dates:
                    if "creation" in list(datemeta.values()):
                        header.append("Packaged: {}".format(date))

            # fill in other required values that we can't extract
            if not any([h.startswith("Author URL: ") for h in header]):
                header.append("Author URL: .")
        else:
            # chapter page
            chapter_index_match = CHAPTER_INDEX_REGEX.search(document_name)
            chapter_index = int(chapter_index_match.group())
            html = document.get_body_content().decode(EPUB_ENCODING)
            chapter_text = html2text.html2text(html)
            if 'class="fff_chapter_title"/>' in html:
                # chapter without title (title is self-closing)
                chapter_title = "Chapter {}".format(chapter_index)
            else:
                chapter_title_match = CHAPTER_TITLE_REGEX.search(html)
                chapter_title = html_unescape(chapter_title_match.group(1))
            chapters.append(
                RawChapter(
                    index=chapter_index,
                    title=chapter_title,
                    text=chapter_text,
                )
            )

    metadata.update(
        RawStory.convert_metadata(
            {
                h[:h.find(":")]: h[h.find(":") + 1:].strip()
                for h in header
            }
        )
    )
    metadata["summary"] = summary
    metadata["chapters"] = chapters
    story = RawStory(
        **metadata,
    )
    return story


def parse_epub_story(session, fin):
    """
    Parse a story in epub format.

    @param session: sqlalchemy session to use
    @type session: L{sqlalchemy.orm.Session}
    @param fin: file-like object to read
    @type fin: file-like
    @return: the raw story
    @rtype: L{zimfiction.importer.raw.RawStory}
    """
    # copy file content to tempfile - ebooklib needs a path
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        data = True
        while data:
            data = fin.read(8192)
            tf.write(data)
        tf.close()
        path = tf.name
        # convert to txt
        story = convert_epub(path)
        # clean up temp file
        os.remove(path)
        return story

