"""
This module contains the txt/markdown story parse logic.
"""
import datetime
import re

from .raw import RawStory, RawChapter, RawSeriesMembership
from .raw import id_from_url, split_categories, split_tags, is_done_from_status
from ..util import add_to_dict_list
from ..exceptions import ParseError


CHAPTER_TITLE_REGEX = re.compile(r"\t[0-9]+\. .+")


def parse_txt_story(session, fin):
    """
    Parse a story in txt/markdown format.

    @param session: sqlalchemy session to use
    @type session: L{sqlalchemy.orm.Session}
    @param fin: file-like object to read or text to parse
    @type fin: file-like or L{str}
    @return: the raw story
    @rtype: L{zimfiction.importer.raw.RawStory}
    """
    in_body = False
    in_summary = False
    in_title = False
    got_meta = False
    n_empty_lines = 0
    meta = {}
    tags = {  # tag type -> tag list
        "genres": [],
        "characters": [],
        "relationships": [],
        "warnings": [],
    }
    series = []  # tuples of (name, index)
    chapters = []
    cur_lines = []
    cur_chapter_i = None
    cur_chapter_title = None
    publisher = None

    for line in (fin if not isinstance(fin, str) else fin.splitlines(keepends=True)):
        line = line.replace("\x00", "")  # some database dislikes such strings
        if not in_body:
            # process header
            line = line.strip()
            if not line:
                n_empty_lines += 1
                # body starts after a couple of empty lines
                if got_meta and n_empty_lines >= 3:
                    # leaving header
                    in_body = True
                continue
            else:
                # line is not empty, we need to:
                #   - reset empty line counter
                #   - check if it ends a potential multi line field (e.g. title)
                # check if in title and it ends here
                if n_empty_lines > 0 and in_title and line.startswith("by "):
                    # end of title
                    in_title = False
                    # but continue parsing for now, as we still need to extract the author
                n_empty_lines = 0
            if "title" not in meta:
                meta["title"] = line
                in_title = True
                continue
            if in_title:
                # because for some reason titles can sometimes be multiline
                meta["title"] += "\n" + line
                # in_title will be set to False in a separate check
                continue
            elif in_summary:
                meta["summary"] += ("\n" + line)
                continue
            if line.startswith("by ") and "author" not in meta:
                meta["author"] = line[3:].strip()
                continue
            got_meta = True
            # if (":" not in line) and (meta.get("summary", None) is not None):
            #     # sometimes people manage to  add a newline in the summary
            #     meta["summary"] += ("\n" + line)
            #     continue
            key, value = line.split(": ", 1)
            if key == "Publisher":
                assert publisher is None
                publisher = value.strip()
            elif key in (
                "Category",
                "Language",
                "Rating",
                "Summary",
                "Author URL",
            ):
                if "author" not in meta:
                    # special case: title empty and reached meta information
                    # in this case, the title is the author line
                    meta["author"] = meta["title"][3:].strip()
                    meta["title"] = "INVALID TITLE"
                if key == "Author URL":
                    meta["author_url"] = value.strip()
                else:
                    meta[key.lower()] = value.strip()
                if key.lower() == "summary":
                    in_summary = True
            elif key in (
                "Chapters",
                "Words",
                "Word Count",
                "Word count",
                "Author",
            ):
                # skip these
                continue
            elif key in (
                "Published",
                "Updated",
                "Packaged",
            ):
                meta[key.lower()] = datetime.datetime.fromisoformat(value)
            elif key == "Story URL":
                meta["id"] = id_from_url(value)
                meta["url"] = value
            elif key == "Status":
                meta["is_done"] = is_done_from_status(value)
            elif key in ("Genre", "Genres", "Erotica Tags"):
                for tag in split_tags(value):
                    add_to_dict_list(tags, "genres", tag)
            elif key == "Warnings":
                for tag in split_tags(value):
                    add_to_dict_list(tags, "warnings", tag)
            elif key == "Characters":
                for tag in split_tags(value):
                    add_to_dict_list(tags, "characters", tag)
            elif key == "Relationships":
                for tag in split_tags(value):
                    add_to_dict_list(tags, "relationships", tag)
            elif key in ("Chars/Pairs", "Characters/Pairing"):
                for tag in split_tags(value):
                    if ("&" in tag) or ("/" in tag):
                        add_to_dict_list(tags, "relationships", tag)
                    else:
                        add_to_dict_list(tags, "characters", tag)
            elif key == "Series":
                series_index = int(value[value.rfind("[")+1: value.rfind("]")])
                series_name = value[:value.rfind("[") - 1]
                # ensure that we don't add a series twice - because apparently
                # some fics contain the data multiple times
                if not any([e[0] == series_name for e in series]):
                    series.append((series_name, series_index))
            elif key in ("Series URL", "Collections"):
                # ignore tags
                pass
            elif key in ("Kudos", "Favorites"):
                meta["score"] = int(value)
            elif key == "Comments":
                meta["num_comments"] = int(value)
            else:
                raise ParseError("Unknown metadata key: '{}'".format(key))
        else:
            # process body
            if is_chapter_title_line(line):
                if cur_chapter_i is not None:
                    text = "\n".join(cur_lines)
                    assert publisher is not None
                    chapters.append(
                        RawChapter(
                            index=cur_chapter_i,
                            title=cur_chapter_title,
                            text=text,
                        )
                    )
                chapter_i, cur_chapter_title = line.strip().split(". ", 1)
                chapter_i = int(chapter_i)
                if cur_chapter_i is None:
                    cur_chapter_i = chapter_i
                else:
                    cur_chapter_i = cur_chapter_i + 1
                cur_lines = []  # [line]
            else:
                cur_lines.append(line[:-1])  # remove trailing newline

    # at end of file
    if not meta:
        raise ParseError("Story does not contain any metadata!")

    # check for unconsumed chapter
    if "End file." in cur_lines:
        # TODO: only remove last occurence
        cur_lines.remove("End file.")
    text = "\n".join(cur_lines)
    if text or ((not text) and (not chapters)):
        # either an unconsumed chapter or not story content at all
        if not text:
            # not story content at all, provide a short placeholder text
            # we do this to simply the build later
            text = "**[Story is empty]**"
        if cur_chapter_i is None:
            # only one chapter, no chapter line
            cur_chapter_i = 1
            cur_chapter_title = "Chapter 1"
        assert publisher is not None
        chapters.append(
            RawChapter(
                index=cur_chapter_i,
                title=cur_chapter_title,
                text=text,
            )
        )
    if "category" not in meta:
        # sometimes there are stories without categories
        # We instead put it in a special one
        meta["category"] = "No Category"
    # split categories
    meta["categories"] = split_categories(meta["category"])
    del meta["category"]
    if "summary" not in meta:
        meta["summary"] = ""
    if "language" not in meta:
        meta["language"] = "(Unknown)"
    if "is_done" not in meta:
        meta["is_done"] = False
    if "published" not in meta:
        if "updated" in meta:
            meta["published"] = meta["updated"]
        else:
            meta["published"] = datetime.datetime(year=1, month=1, day=1)
    if "updated" not in meta:
        meta["updated"] = meta["published"]
    if "packaged" not in meta:
        meta["packaged"] = datetime.datetime(year=1, month=1, day=1)
    meta["chapters"] = chapters
    meta["publisher"] = publisher
    # clean title
    meta["title"] = meta["title"].strip()
    # add series
    meta["series"] = []
    for series_name, series_i in series:
        meta["series"].append(
            RawSeriesMembership(
                publisher=publisher,
                name=series_name,
                index=series_i,
            ),
        )
    # add tags
    for tagtype in tags.keys():
        meta[tagtype] = tags[tagtype]
    story = RawStory(
        **meta,
    )
    return story


def is_chapter_title_line(line):
    """
    Check if a line is the chapter title line.

    @param line: line to check
    @type line: L{str}
    @return: True if the line is a chapter title line, False otherwise
    @rtype: L{str}
    """
    return CHAPTER_TITLE_REGEX.match(line)


