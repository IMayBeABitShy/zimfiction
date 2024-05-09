"""
CLI code for the importer.
"""
import argparse

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from fs import open_fs


from .importer.importer import import_from_fs
from .zimbuild.builder import ZimBuilder, BuildOptions
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
                verbose=ns.verbose,
            )
            session.flush()
            session.commit()


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
    )
    builder.build(ns.outpath, options=build_options)


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
        "directories",
        action="store",
        nargs="+",
        help="directories to import from"
    )

    # parser for the ZIM build
    build_parser = subparsers.add_parser(
        "build",
        help="build a ZIM file",
    )
    build_parser.add_argument(
        "database",
        action="store",
        help="database to store stories in, as sqlalchemy connection URL",
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

    ns = parser.parse_args()

    if ns.command == "import":
        # import from a database
        run_import(ns)
    elif ns.command == "build":
        # build a ZIM
        run_build(ns)
    else:
        raise RuntimeError("Unknown subcommand: {}".format(ns.command))


if __name__ == "__main__":
    main()
