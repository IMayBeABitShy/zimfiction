"""
This module contains functionality to export a story as a json file.
"""
import json

from .dumper import Dumper
from ..importer.raw import RawStory


class JsonDumper(Dumper):
    """
    A dumper for .json files.
    """

    def get_encoding(self, story):
        return "utf-8"

    def get_filename(self, story):
        return "story-{}-{}.json".format(story.publisher.name, story.id)

    def dump(self, story):
        raw = RawStory.from_story(story)
        data = raw.to_dict()
        return json.dumps(data)
