"""
This module contains the json->story parse logic.
"""
import json

from .raw import RawStory
from ..exceptions import ParseError


def parse_json_story(session, fin):
    """
    'Parse' a story in json format.

    This is supposed to be used to re-import stories exported by L{zimfiction.exporter.jsondumper.JsonDumper}.

    @param session: sqlalchemy session to use
    @type session: L{sqlalchemy.orm.Session}
    @param fin: file-like object to read or text to parse
    @type fin: file-like or L{str}
    @return: the raw story
    @rtype: L{zimfiction.importer.raw.RawStory}
    """
    data = json.load(fin)
    try:
        story = RawStory.from_dict(data)
    except Exception as e:
        raise ParseError("Invalid or wrongly structure JSON!") from e
    return story
