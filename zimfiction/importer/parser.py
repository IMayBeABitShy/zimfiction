"""
This module contains the story parse logic.
"""
import datetime
import re

from ..util import add_to_dict_list, count_words
from ..db.models import Story, Chapter, Author, Category, Tag, Series
from ..exceptions import ParseError


CHAPTER_TITLE_REGEX = re.compile(r"\t[0-9]+\. .+")


def parse_story(session, fin):
    """
    Parse a story.

    @param session: sqlalchemy session to use
    @type session: L{sqlalchemy.orm.Session}
    @param fin: file-like object to read
    @type fin: file-like
    @return: the story
    @rtype: L{zimfiction.db.models.Story}
    """
    in_body = False
    in_summary = False
    in_title = False
    got_meta = False
    n_empty_lines = 0
    meta = {}
    tags = {}  # tag type -> tag list
    chapters = []
    cur_lines = []
    cur_chapter_i = None
    cur_chapter_title = None

    for line in fin:
        if not in_body:
            # process header
            line = line.strip()
            if not line:
                # title will definitely end on empty line
                in_title = False
                # body starts after a couple of empty lines
                n_empty_lines += 1
                if got_meta and n_empty_lines >= 3:
                    # leaving header
                    in_body = True
                continue
            else:
                n_empty_lines = 0
            if "title" not in meta:
                meta["title"] = line
                in_title = True
                continue
            if in_title:
                # because for some reason titles can sometimes be multiline
                meta["title"] += "\n" + line
                # in_title will be set to False in empty line check
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
            if key in (
                "Category",
                "Language",
                "Rating",
                "Summary",
                "Publisher",
                "Author URL",
            ):
                if "author" not in meta:
                    # special case: title empty and reached meta information
                    # in this case, the title is the author line
                    meta["author"] = meta["title"][3:].strip()
                    meta["title"] = "INVALID TITLE"
                meta[key.lower()] = value.strip()
                if key.lower() == "summary":
                    in_summary = True
            elif key in (
                "Chapters",
                "Words",
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
            elif key == "Genre":
                for tag in value.split(", "):
                    add_to_dict_list(tags, "genre", tag)
            elif key == "Warnings":
                for tag in value.split(", "):
                    add_to_dict_list(tags, "warning", tag)
            elif key == "Relationships":
                for tag in value.split(", "):
                    add_to_dict_list(tags, "relationship", tag)
            elif key == "Series":
                series_index = int(value[value.rfind("[")+1: value.rfind("]")])
                series_name = value[:value.rfind("[") - 1]
                meta["series"] = series_name
                meta["series_index"] = series_index
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
                    chapters.append(
                        Chapter(
                            publisher=meta["publisher"],
                            story_id=meta["id"],
                            index=cur_chapter_i,
                            title=cur_chapter_title,
                            text=text,
                            num_words=count_words(text),
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

    # unconsumed chapter
    if "End file." in cur_lines:
        # TODO: only remove last occurence
        cur_lines.remove("End file.")
    text = "\n".join(cur_lines)
    if text:
        if cur_chapter_i is None:
            # only one chapter, no chapter line
            cur_chapter_i = 1
            cur_chapter_title = "Chapter 1"
        chapters.append(
            Chapter(
                publisher=meta["publisher"],
                story_id=meta["id"],
                index=cur_chapter_i,
                title=cur_chapter_title,
                text=text,
                num_words=count_words(text),
            )
        )

    meta["author"] = Author.as_unique(
        session,
        publisher=meta["publisher"],
        name=meta["author"],
        url=meta["author url"]
    )
    if "series" in meta:
        meta["series"] = Series.as_unique(
            session,
            publisher=meta["publisher"],
            name=meta["series"],
        )
    if "category" not in meta:
        # sometimes there are stories without categories
        # We instead put it in a special one
        meta["category"] = "No Category"
    # split categories
    categories = [c.strip() for c in meta["category"].split(",")]
    del meta["category"]
    # convert categories into objeczs
    meta["categories"] = [
        Category.as_unique(
            session,
            publisher=meta["publisher"],
            name=c,
        )
        for c in categories
    ]
    meta["tags"] = [
        Tag.as_unique(session, type=tagtype, name=tagname)
        for tagtype in tags.keys()
        for tagname in tags[tagtype]
    ]
    if "summary" not in meta:
        meta["summary"] = ""
    if "language" not in meta:
        meta["language"] = "(Unknown)"
    meta["chapters"] = chapters
    if "author url" in meta:
        del meta["author url"]

    return Story(
        **meta,
    )


def is_done_from_status(status):
    """
    Check if a story is done depending on the status.

    @param status: status of the story
    @type status: l{str}
    @return: True if the story is finished, otherwise False
    @rtype: L{bool}
    """
    lstatus = status.lower().strip()
    if lstatus in (
        "in-progress",
    ):
        return False
    elif lstatus in (
        "complete",
        "completed",
    ):
        return True
    raise ParseError("Unknown story status: '{}'".format(status))


def id_from_url(url):
    """
    Parse the URL of a story and return the story ID.

    @param url: url of the story
    @type url: L{str}
    @return: the story id
    @rtype: L{int}
    """
    if "fanfiction.net" in url:
        part = url[url.find("/s/") + 3:]
        if "/" in part:
            part = part[:part.find("/")]
        return int(part)
    elif "fictionpress.com" in url:
        part = url[url.find("/s/") + 3:]
        if "/" in part:
            part = part[:part.find("/")]
        return int(part)
    elif "archiveofourown.org" in url:
        part = url[url.find("/works/") + 7:]
        if "/" in part:
            part = part[:part.find("/")]
        return int(part)
    else:
        raise ParseError("Unknown story URL format: '{}'".format(url))


def is_chapter_title_line(line):
    """
    Check if a line is the chapter title line.

    @param line: line to check
    @type line: L{str}
    @return: True if the line is a chapter title line, False otherwise
    @rtype: L{str}
    """
    return CHAPTER_TITLE_REGEX.match(line)


