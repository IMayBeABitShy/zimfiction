"""
This module contains the json->story parse logic.
"""
import json

from .raw import RawStory
from ..exceptions import ParseError


def parse_json_story(session, fin, force_publisher=None):
    """
    'Parse' a story in json format.

    This is supposed to be used to re-import stories exported by L{zimfiction.exporter.jsondumper.JsonDumper}.

    @param session: sqlalchemy session to use
    @type session: L{sqlalchemy.orm.Session}
    @param fin: file-like object to read or text to parse
    @type fin: file-like or L{str}
    @param force_publisher: if not None, force all stories imported to have this publisher
    @type force_publisher: L{str} or L{None}
    @return: the story
    @rtype: L{zimfiction.db.models.Story}
    """
    data = json.load(fin)
    try:
        raw = RawStory.from_dict(data)
    except Exception as e:
        raise ParseError("Invalid or wrongly structure JSON!") from e
    story = raw.to_story(session=session, force_publisher=force_publisher)
    return story
