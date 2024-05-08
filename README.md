# ZimFiction - Convert fiction dumps into a ZIM file

ZimFiction is a tool for converting downloaded fanfiction into ZIM files. These story are usually taken from shared dumps, which in turn usually use [FanFicFare](https://github.com/JimmXinu/FanFicFare) for the download. The resulting ZIM files contain the stories in a easily browsable HTML format.

## Features

- import txt, html and epub dumps
- generate ZIM files of the dump
- statistics in ZIM
- organized by publisher
- browse stories by category, tag, series and author

## Usage

ZimFiction works in two stages: the import and the build phase. The import phase imports directories of stories and inserts them into a database. The build phase takes this database and builds a ZIM file.

Before we begin, be sure you have installed the `zimfiction` package. It is not on pypi, so instead clone the repo and install it (e.g. `pip install path/tp/cloned/repo/`).

First, you need one or more fanfiction dumps. You can probably find one of those rather easily on reddit. Alternatively, you can also create a directory and download fics there using fanficfare (in this case, using `html` as an output format is recommended).

Next, import the fics:

`zimfiction -v import <database> <directory> [--ignore-errors]`

Here, ``database refers to an [sqlalchemy database url](https://docs.sqlalchemy.org/en/20/core/engines.html), e.g. `sqlite:///stories.sqlite`. `directory` is simply the path to one or more directories containing the dumps. As these dumps often miss some metadata, it is recommended to also specify `--ignore-errors`, which tells zimfiction to skip stories it can not parse (e.g. because the publisher is msising).

Finally, build the ZIM:

`zimfiction -v build <database> <zimpath>`

The `database` argument behaves like the one used by `zimfiction import`, the `zimpath` argument specifies the path to write the ZIM file to.
