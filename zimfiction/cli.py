"""
CLI code for the importer.
"""
import argparse

try:
    import multiprocessing
    multiprocessing.set_start_method("forkserver")
except Exception:
    # multiprocessing may not be available
    multiprocessing = None

from sqlalchemy.orm import Session

from .reporter import StdoutReporter, VoidReporter
from .importer.importer import import_from_fs
from .zimbuild.builder import ZimBuilder, BuildOptions
from .implication.implicator import get_default_implicator, add_all_implications
from .exporter.exporter import Exporter, get_dumper
from .db.models import mapper_registry
from .db.connection import ConnectionConfig


def _connection_config_from_ns(ns):
    """
    Generate a connection configuration from the argparse namespace.

    @param ns: namespace containing arguments
    @type ns: L{argparse.Namespace}
    @return: the connection config
    @rtype: L{zimfiction.db.connection.ConnectionConfig}
    """
    config = ConnectionConfig(
        url=ns.database,
        verbose=(ns.verbose >= 2),
    )
    return config


def run_import(ns):
    """
    Run the import command.

    @param ns: namespace containing arguments
    @type ns: L{argparse.Namespace}
    """
    engine = _connection_config_from_ns(ns).connect()
    if ns.verbose:
        print("Creating tables...")
    mapper_registry.metadata.create_all(engine)

    with Session(engine) as session:
        for directory in ns.directories:
            if ns.verbose:
                print("Importing from: ", directory)
            import_from_fs(
                directory,
                session,
                workers=ns.workers,
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
    engine = _connection_config_from_ns(ns).connect()
    with Session(engine) as session:
        implicator = get_default_implicator(session, ao3_merger_path=ns.ao3_merger_path)
        if ns.delete_existing:
            reporter.msg("Deleting existing implications... ", end="")
            implicator.delete_implications()
            reporter.msg("Done.")
        add_all_implications(session, implicator, eager=ns.eager, reporter=reporter)
    reporter.msg("Found {} implied tags.".format(implicator.n_tags_implied))
    reporter.msg("Found {} implied categories.".format(implicator.n_categories_implied))


def run_build(ns):
    """
    Run the build command.

    @param ns: namespace containing arguments
    @type ns: L{argparse.Namespace}
    """
    connection_config = _connection_config_from_ns(ns)
    builder = ZimBuilder(connection_config)
    build_options = BuildOptions(
        use_threads=ns.threaded,
        num_workers=ns.workers,
        log_directory=ns.log_directory,
        eager=ns.eager,
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
    engine = _connection_config_from_ns(ns).connect()
    with Session(engine) as session:
        exporter = Exporter(session, dumper=dumper, grouped=ns.grouped, reporter=reporter)
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
        "--workers",
        action="store",
        type=int,
        default=0,
        help="Number of workers to use for import. May not be available with all filesystems.",
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
        "--lazy",
        action="store_false",
        dest="eager",
        help="Do not eager load stories",
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
        "--lazy",
        action="store_false",
        dest="eager",
        help="Do not eager load stories, tags, ...",
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
    export_parser.add_argument(
        "--grouped",
        action="store_true",
        help="Group stories by publisher and id in subdirectories",
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
