"""
This module contains the L{Exporter}, which handles the systematic export of stories.
"""
import os

from sqlalchemy import select, func

from ..db.models import Story
from ..reporter import BaseReporter, VoidReporter
from .dumper import Dumper
from .txtdumper import TxtDumper


def get_dumper(format):
    """
    Return the dumper to use for a specific format.

    @param format: format to get dumper for
    @type format: L{str}
    @return: the dumper to use
    @rtype: L{zimfiction.exporter.dumper.Dumper}
    @raises KeyError: if no such format is known
    """
    assert isinstance(format, str)
    if format in ("txt", "text"):
        return TxtDumper()
    else:
        raise KeyError("No dumper for format '{}' known!".format(format))


class Exporter(object):
    """
    The exporter systematically exports stories.

    @ivar session: sqlalchemy session to load stories from
    @type session: L{sqlalchemy.orm.Session}
    @ivar dumper: dumper to use to export stories
    @type dumper: L{zimfiction.exporter.dumper.Dumper}
    @ivar reporter: reporter to use for progress reporters
    @type reporter: L{zimfiction.reporter.BaseReporter}
    """
    def __init__(self, session, dumper, reporter=None):
        """
        The default constructor.

        @param session: sqlalchemy session to load stories from
        @type session: L{sqlalchemy.orm.Session}
        @param dumper: dumper to use to export stories
        @type dumper: L{zimfiction.exporter.dumper.Dumper}
        @param reporter: reporter to use for progress reporters
        @type reporter: L{zimfiction.reporter.BaseReporter} or L{None}
        """
        assert isinstance(dumper, Dumper)
        assert isinstance(reporter, BaseReporter) or (reporter is None)
        self.session = session
        self.dumper = dumper
        if reporter is None:
            reporter = VoidReporter()
        self.reporter = reporter

    def export_to(self, directory, criteria=True):
        """
        Export all stories matching the criteria into the specified directory.

        @param directory: directory to export stories to
        @type directory: L{str}
        @param criteria: a selection criteria passed to C{select(Story).where(criteria)}
        @type criteria: anything accepted by L{sqlalchemy.sql.expression.Select.where}
        """
        # count stories
        n_stories = self.session.execute(
            select(func.count(Story.id))
        ).scalar_one()
        # get stories
        stmt = select(Story).where(criteria)
        stories = self.session.scalars(stmt)
        # export stories
        with self.reporter.with_progress("Exporting...", max=n_stories, unit="stories") as bar:
            for story in stories:
                encoding = self.dumper.get_encoding(story)
                filename = self.dumper.get_filename(story)
                content = self.dumper.dump(story)

                is_binary = (encoding is None)
                mode = ("wb" if is_binary else "w")
                path = os.path.join(directory, filename)
                with open(path, mode, encoding=encoding) as fout:
                    fout.write(content)
                bar.advance(1)
