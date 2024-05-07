"""
This module contains the html story parse logic.

@var PARSER: parser to use (passed to L{bs4.BeautifulSoup}
@type PARSER: L{str}
"""
import argparse

import html2text
from bs4 import BeautifulSoup

from .txtparser import parse_txt_story


PARSER = "lxml"


def _is_chapter_a(tag):
    """
    Return True if a tag is an a-tag at the start of a section.

    @param tag: tag to check
    @type tag: L{bs4.element.Tag}
    @return: True if the tag fulfils the mentioned condition
    @rtype: L{bool}
    """
    return (tag.name.lower() == "a") and tag.has_attr("name") and tag["name"].startswith("section")


def convert_html(html):
    """
    Convert a html story into a txt/markdown story

    @param html: html of story to convert
    @type htmö: L{str}
    @return: the converted story
    @rtype: L{str}
    """
    soup = BeautifulSoup(html, PARSER)
    # --- header data ---
    header = {}
    # find title, author
    title_h = soup.find("h1")
    title_a = title_h.find("a")
    title = title_a.string
    author_a = title_h.find(class_="authorlink")
    author = author_a.string
    header["Author URL"] = author_a["href"]
    # metadata
    meta_table = soup.find("table")
    for tr in meta_table.find_all("tr"):
        key_td = tr.find("td")
        key = key_td.next.next.replace(":", "").strip()
        value_td = key_td.next_sibling
        value = value_td.next
        header[key] = value
    # --- chapters ---
    pages = []  # list of (chapter_i, chapter_title, chapter_text)
    for a in soup.find_all(_is_chapter_a):
        chapter_title = a.next.next
        chapter_i = int(a["name"].replace("section", ""))
        chapter_content = a.next_sibling.next_sibling
        chapter_text = html2text.html2text(str(chapter_content))
        pages.append((chapter_i, chapter_title, chapter_text))
    # --- parsing complete, output txt ---
    if "Summary" in header:
        summary = header["Summary"]
        del header["Summary"]
    else:
        summary = "[No Summary]"
    text = "\n\n\n{title}\n\nby {author}\n\n\n\n{meta}\nSummary: {summary}\n\n\n\n\n".format(
        title=title,
        author=author,
        meta="\n".join(["{}: {}".format(k, v) for k, v in header.items()]),
        summary=summary,
    )
    pages.sort(key=lambda x: x[0])
    for chapter_index, chapter_title, chapter_text in pages:
        text += "\n\n\t{}. {}\n\n{}".format(
            chapter_index,
            chapter_title,
            chapter_text,
        )
        if not text.endswith("\n"):
            text += "\n"
    return text


def parse_html_story(session, fin):
    """
    Parse a html in epub format.

    @param session: sqlalchemy session to use
    @type session: L{sqlalchemy.orm.Session}
    @param fin: file-like object to read
    @type fin: file-like
    @return: the story
    @rtype: L{zimfiction.db.models.Story}
    """
    html = fin.read()
    txt = convert_html(html)
    return parse_txt_story(session, txt)


def main():
    """
    A main function used for testing the conversion.
    """
    parser = argparse.ArgumentParser(description="convert html fanfics to markdown fanfics")
    parser.add_argument(
        "inpath",
        help="path to read from",
    )
    parser.add_argument(
        "outpath",
        nargs="?",
        default="-",
        help="path to write to",
    )
    ns = parser.parse_args()
    with open(ns.inpath, mode="r", encoding="utf-8") as fin:
        html = fin.read()
        text = convert_html(html)
    if ns.outpath == "-":
        # print to stoud
        print(text)
    else:
        with open(ns.outpath, "w", encoding="utf-8") as fout:
            fout.write(text)


if __name__ == "__main__":
    main()
