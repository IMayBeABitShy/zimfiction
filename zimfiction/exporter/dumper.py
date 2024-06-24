"""
This module contains an abstract interface for dumpers.
"""


class Dumper(object):
    """
    Base class for dumpers.

    A dumper generates a file from a database object.
    """
    def get_encoding(self, story):
        """
        Return the encoding to use.

        If this is L{None}, use a binary output.

        @param story: story to get encoding for
        @type story: L{zimfiction.db.models.Story}
        @return: the encoding to use for the file output.
        @rtype: L{str} or L{None}
        """
        raise NotImplementedError()

    def get_filename(self, story):
        """
        Return the filename a story should be saved as.

        @param story: story to process
        @type story: L{zimfiction.db.models.Story}
        @return: the filename the dump should be saved as
        @rtype: L{str}
        """
        raise NotImplementedError()

    def dump(self, story):
        """
        Dump the story into the output format.

        @param story: story to process
        @type story: L{zimfiction.db.models.Story}
        @return: the dumped story
        @rtype: L{str}
        """
        raise NotImplementedError()
