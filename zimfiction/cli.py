"""
CLI code for the importer.
"""
import argparse

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from fs import open_fs


from .reporter import StdoutReporter, VoidReporter
from .importer.importer import import_from_fs
from .zimbuild.builder import ZimBuilder, BuildOptions
from .implication.implicator import get_default_implicator, add_all_implications
from .exporter.exporter import Exporter, get_dumper
from .db.models import mapper_registry


def enable_foreign_keys(dbapi_conn):
    """
    Enable foreign key constraints for this connection.

    @param dbapi_conn: database connection
    @type dbapi_conn: L{sqlalchemy.engine.interfaces.DBAPIConnection}
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@event.listens_for(Engine, "connect")
def enable_foreign_keys_on_connect(dbapi_connection, connection_record):
    """
    Enable foreign keys if a sqlite connection has been made.

    @param dbapi_conn: database connection
    @type dbapi_conn: L{sqlalchemy.engine.interfaces.DBAPIConnection}
    @param connection_record: database connection record info
    @type connection_record: L{sqlalchemy.pool.ConnectionPoolEntry}
    """
    # Check if the connection URL is SQLite
    if "sqlite" in str(connection_record.driver_connection):
        enable_foreign_keys(dbapi_connection)


def connect_to_db(ns):
    """
    Create a database connection.

    @param ns: namespace containing connection args
    @type ns: L{argparse.Namespace}
    @return: the connected sqlalchemy engine
    @rtype: L{sqlalchemy.engine.Engine}
    """
    if ns.verbose:
        print("Connecting to database...")
    engine = create_engine(
        ns.database,
        echo=(ns.verbose >= 2),
    )
    if ns.verbose:
        print("Connected.")
    return engine


def run_import(ns):
    """
    Run the import command.

    @param ns: namespace containing arguments
    @type ns: L{argparse.Namespace}
    """
    engine = connect_to_db(ns)
    if ns.verbose:
        print("Creating tables...")
    mapper_registry.metadata.create_all(engine)

    with Session(engine) as session:
        for directory in ns.directories:
            if ns.verbose:
                print("Importing from: ", directory)
            fs = open_fs(directory)
            import_from_fs(
                fs,
                session,
                ignore_errors=ns.ignore_errors,
                limit=ns.limit,
                force_publisher=ns.force_publisher,
                remove=ns.remove,
                verbose=ns.verbose,
            )
            session.flush()
            session.commit()


def run_find_implications(ns):
    """
    Run the find-implications command.

    @param ns: namespace containing arguments
    @type ns: L{argparse.Namespace}
    """
    if ns.verbose > 0:
        reporter = StdoutReporter()
    else:
        reporter = VoidReporter()
    engine = connect_to_db(ns)
    with Session(engine) as session:
        implicator = get_default_implicator(session, ao3_merger_path=ns.ao3_merger_path)
        if ns.delete_existing:
            reporter.msg("Deleting existing implications... ", end="")
            implicator.delete_implications()
            reporter.msg("Done.")
        add_all_implications(session, implicator, reporter=reporter)
    reporter.msg("Found {} implied tags.".format(implicator.n_tags_implied))
    reporter.msg("Found {} implied categories.".format(implicator.n_categories_implied))


def run_build(ns):
    """
    Run the build command.

    @param ns: namespace containing arguments
    @type ns: L{argparse.Namespace}
    """
    engine = connect_to_db(ns)
    builder = ZimBuilder(engine)
    build_options = BuildOptions(
        use_threads=ns.threaded,
        num_workers=ns.workers,
        log_directory=ns.log_directory,
        memprofile_directory=ns.memprofile_directory,
        include_external_links=ns.include_external_links,
        skip_stories=ns.skip_stories,
    )
    builder.build(ns.outpath, options=build_options)


def run_export(ns):
    """
    Run the export command.

    @param ns: namespace containing arguments
    @type ns: L{argparse.Namespace}
    """
    if ns.verbose > 0:
        reporter = StdoutReporter()
    else:
        reporter = VoidReporter()
    dumper = get_dumper(ns.format)
    engine = connect_to_db(ns)
    with Session(engine) as session:
        exporter = Exporter(session, dumper=dumper, reporter=reporter)
        exporter.export_to(ns.directory, criteria=True)


def main():
    """
    The main function.
    """
    # general argparse setup
    parser = argparse.ArgumentParser(
        description="Import stories from a fiction dump into a database",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="be more verbose",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        help="command to execute",
    )

    # parser for the import
    import_parser = subparsers.add_parser(
        "import",
        help="import a fanfic dump",
    )
    import_parser.add_argument(
        "--ignore-errors",
        action="store_true",
        dest="ignore_errors",
        help="continue import even when errors are encountered.",
    )
    import_parser.add_argument(
        "--limit",
        action="store",
        type=int,
        dest="limit",
        default=None,
        help="import at most this many stories",
    )
    import_parser.add_argument(
        "database",
        action="store",
        help="database to store stories in, as sqlalchemy connection URL",
    )
    import_parser.add_argument(
        "--force-publisher",
        action="store",
        dest="force_publisher",
        default=None,
        help="Import all stories under this publisher",
    )
    import_parser.add_argument(
        "--remove",
        action="store_true",
        dest="remove",
        help="Remove imported fics",
    )
    import_parser.add_argument(
        "directories",
        action="store",
        nargs="+",
        help="directories to import from"
    )

    # parser for the implication finder
    implication_parser = subparsers.add_parser(
        "find-implications",
        help="Find implied tags and categories for the story",
    )
    implication_parser.add_argument(
        "database",
        action="store",
        help="database to store stories in, as sqlalchemy connection URL",
    )
    implication_parser.add_argument(
        "--delete",
        action="store_true",
        dest="delete_existing",
        help="delete existing implications",
    )
    implication_parser.add_argument(
        "--ao3-mergers",
        action="store",
        dest="ao3_merger_path",
        default=None,
        help="Path to a CSV file of ao3 tag info to extract merger information from",
    )

    # parser for the ZIM build
    build_parser = subparsers.add_parser(
        "build",
        help="build a ZIM file",
    )
    build_parser.add_argument(
        "database",
        action="store",
        help="database to load stories from, as sqlalchemy connection URL",
    )
    build_parser.add_argument(
        "outpath",
        action="store",
        help="path to write ZIM to",
    )
    build_parser.add_argument(
        "--threaded",
        action="store_true",
        help="use threads instead of processes for workers"
    )
    build_parser.add_argument(
        "--workers",
        action="store",
        type=int,
        default=None,
        help="use this many non-zim workers",
    )
    build_parser.add_argument(
        "--log-directory",
        action="store",
        default=None,
        help="enable logging and write logs into this directory",
    )
    build_parser.add_argument(
        "--memprofile-directory",
        action="store",
        default=None,
        help="enable memory profile and write into this directory",
    )
    build_parser.add_argument(
        "--no-external-links",
        action="store_false",
        dest="include_external_links",
        help="do not include external links to the works",
    )
    build_parser.add_argument(
        "--debug-skip-stories",
        action="store_true",
        dest="skip_stories",
        help="do not include stories (debug option)",
    )

    # parser for the non-ZIM export
    export_parser = subparsers.add_parser(
        "export",
        help="export stories",
    )
    export_parser.add_argument(
        "database",
        action="store",
        help="database to load stories from, as sqlalchemy connection URL",
    )
    export_parser.add_argument(
        "directory",
        action="store",
        help="directory to write stories to",
    )
    export_parser.add_argument(
        "-f",
        "--format",
        action="store",
        default="txt",
        help="Format to export stories as",
    )

    ns = parser.parse_args()

    if ns.command == "import":
        # import from a database
        run_import(ns)
    elif ns.command == "find-implications":
        # find implied tags
        run_find_implications(ns)
    elif ns.command == "build":
        # build a ZIM
        run_build(ns)
    elif ns.command == "export":
        # export stories
        run_export(ns)
    else:
        raise RuntimeError("Unknown subcommand: {}".format(ns.command))


if __name__ == "__main__":
    main()
