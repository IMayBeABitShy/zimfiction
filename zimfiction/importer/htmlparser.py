"""
This module contains the html story parse logic.

@var PARSER: parser to use (passed to L{bs4.BeautifulSoup}
@type PARSER: L{str}
"""
import html2text
from bs4 import BeautifulSoup

from .raw import RawStory, RawChapter


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


def parse_html_story(fin):
    """
    Parse a story in html format.

    @param fin: file-like object to read
    @type fin: file-like
    @return: the raw story
    @rtype: L{zimfiction.importer.raw.RawStory}
    """
    html = fin.read()
    soup = BeautifulSoup(html, PARSER)
    # --- header data ---
    header = {}
    # find title, author
    title_h = soup.find("h1")
    title_a = title_h.find("a")
    title = title_a.string
    story_link = title_a["href"]
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
        if value.string is not None:
            header[key] = str(value.string)
        else:
            header[key] = str(value)
    # --- chapters ---
    chapters = []
    for a in soup.find_all(_is_chapter_a):
        chapter_title = a.next.next
        chapter_i = int(a["name"].replace("section", ""))
        chapter_content = a.next_sibling.next_sibling
        chapter_text = html2text.html2text(str(chapter_content))
        chapters.append(
            RawChapter(
                index=chapter_i,
                title=chapter_title,
                text=chapter_text,
            ),
        )
    # --- parsing complete, instantiate raw story ---
    if "Summary" in header:
        summary = header["Summary"]
        del header["Summary"]
    else:
        summary = "[No Summary]"
    if "Story URL" not in header:
        header["Story URL"] = story_link
    final_metadata = RawStory.convert_metadata(header)
    final_metadata["title"] = title
    final_metadata["author"] = author
    final_metadata["summary"] = summary
    final_metadata["chapters"] = chapters
    story = RawStory(**final_metadata)
    return story

