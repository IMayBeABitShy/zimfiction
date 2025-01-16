"""
Extract story dumps into a temporary directory, import the stories, then remove the tempdir.

This is a helper tool for mass importing story dumps without extracting them manually.
"""
import argparse
import os
import subprocess
import contextlib
import shutil
import time
import random
import threading


@contextlib.contextmanager
def in_tempdir():
    """
    Create a temporary directory in the current path and remove it when
    we are done.

    This method differs from the one in the tempfile modules as it
    generates the temporary directory in the current directory. This is
    because sometimes /tmp/ has a max size and we want to be capable
    of exceeding it.

    @return: a context manager providing the path to the directory
    @rtype: a contextmanager providing L{str}
    """
    path = "_temp_{}_{}".format(time.time(), random.randint(0, 99999))
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def is_archive(path):
    """
    Check if a path refers to an archive.

    @param path: path to check
    @type path: L{str}
    @return: whether the path refers to an archive
    @rtype: L{bool}
    """
    fn, ext = os.path.splitext(path)
    ext = ext.lower()
    is_archive = (ext in (".gz", ".zip", ".7z"))
    return is_archive


def extract_archive(inpath, outpath):
    """
    Extract an archive.

    @param inpath: path to the archive to extract.
    @type inpath: L{str}
    @param outpath: path to directory to extract to. Should already exist.
    @type outpath: L{str}
    """
    fn, ext = os.path.splitext(inpath)
    if ext == ".zip":
        command = ["unzip", inpath, "-d", outpath]
    elif ext == ".gz":
        command = ["tar", "-C", outpath, "-xzf", inpath]
    elif ext == ".7z":
        command = ["7zz", "e", "-o"+outpath, inpath]
    else:
        raise ValueError("Unknown archive type: '{}' ({})".format(inpath, ext))
    subprocess.check_call(command)


def run_import(path, db_url, source_group=None, source_name=None):
    """
    Import a directory.

    @param path: path to directory to import from
    @type path: L{str}
    @param db_url: sqlalchemy database url to import to
    @type db_url: L{str}
    @param source_group: name of the source group these stories should be added to
    @type source_group: L{str} or L{None}
    @param source_group: name of the source these stories should be added to
    @type source_group: L{str} or L{None}
    """
    command = ["zimfiction", "--verbose", "import", "--workers", "-1", "--ignore-errors"]
    if source_group is not None:
        command += ["--source-group", source_group]
    if source_name is not None:
        command += ["--source-name", source_name]
    command += [db_url, path]
    subprocess.check_call(command, bufsize=0)


def process_dir(path, db_url, parallel=False, source_group=None, print_ignored=True):
    """
    Process a directory.

    @param path: path to directory to process
    @type path: L{str}
    @param db_url: sqlachemy url of database to import to
    @type db_url: L{str}
    @param parallel: run imports in parallel
    @type parallel: L{bool}
    @param source_group: name of the source group these stories should be added to
    @type source_group: L{str} or L{None}
    @param print_ignored: if nonzero (default), print files skipped
    @type print_ignored: L{bool}
    """
    print("Descending into '{}'...".format(path))
    filenames = os.listdir(path)
    for fn in filenames:
        fp = os.path.join(path, fn)
        process_path(
            fp,
            db_url=db_url,
            parallel=parallel,
            source_group=source_group,
            print_ignored=print_ignored,
        )


def process_file(path, db_url, parallel=False, source_group=None):
    """
    Process a file.

    @param path: path to file to process
    @type path: L{str}
    @param db_url: sqlalchemy url of database to import to
    @type db_url: L{str}
    @param parallel: run imports in parallel
    @type parallel: L{bool}
    @param source_group: name of the source group these stories should be added to
    @type source_group: L{str} or L{None}
    """
    with in_tempdir() as tempdir:
        extract_archive(path, tempdir)
        source_name = os.path.basename(path)
        run_import(tempdir, db_url=db_url, source_group=source_group, source_name=source_name)
        # handle subarchives
        process_dir(
            tempdir,
            db_url=db_url,
            parallel=parallel,
            source_group=source_group,
            print_ignored=False,
        )


def process_path(path, db_url, parallel=False, source_group=None, print_ignored=True):
    """
    Process a path (either file or directory).

    @param path: path to process
    @type path: L{str}
    @param db_url: sqlalchemy url of database to import to
    @type db_url: L{str}
    @param parallel: run imports in parallel
    @type parallel: L{bool}
    @param source_group: name of the source group these stories should be added to
    @type source_group: L{str} or L{None}
    @param print_ignored: if nonzero (default), print files skipped
    @type print_ignored: L{bool}
    """
    threads = []
    if os.path.isdir(path):
        process_dir(
            path,
            db_url=db_url,
            parallel=parallel,
            source_group=source_group,
            print_ignored=print_ignored,
        )
    elif is_archive(path):
        if parallel:
            thr = threading.Thread(
                name="Import thread",
                target=process_file,
                args=(path, ),
                kwargs={"db_url": db_url, "parallel": parallel, "source_group": source_group},
            )
            thr.daemon = False
            threads.append(thr)
            thr.start()
        else:
            process_file(path, db_url=db_url, parallel=parallel, source_group=source_group)
    else:
        if print_ignored:
            print("Neither directory nor archive: '{}', skipping.".format(path))
    for thr in threads:
        thr.join()


def main():
    """
    The main function.
    """
    parser = argparse.ArgumentParser(
        description="Import directly from one or more story archive",
    )
    parser.add_argument(
        "database",
        help="sqlalchemy database URL to import to",
    )
    parser.add_argument(
        "path",
        nargs="+",
        help="directories/files to import from"
    )
    parser.add_argument(
        "-p",
        "--parallel",
        action="store_true",
        help="Import archives inside a directory in parallel",
    )
    parser.add_argument(
        "--source-group",
        action="store",
        help="Name of the source group these stories should be added to",
    )
    ns = parser.parse_args()

    for path in ns.path:
        process_path(path, db_url=ns.database, parallel=ns.parallel, source_group=ns.source_group)



if __name__ == "__main__":
    main()
