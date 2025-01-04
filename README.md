# ZimFiction - Convert fiction dumps into a ZIM file

ZimFiction is a tool for converting downloaded fanfiction into ZIM files. These story are usually taken from shared dumps, which in turn usually use [FanFicFare](https://github.com/JimmXinu/FanFicFare) for the download. The resulting ZIM files contain the stories in a easily browsable HTML format.

## Features

- import txt, html and epub dumps
- find additonal tags based on summary, other tags or external dumps
- generate ZIM files of the dump
- statistics in ZIM
- organized by publisher
- browse stories by category, tag, series and author

## Requirements

Building a ZimFiction dump takes both a significant amount of times and resouces, depending on the amount of content you wish to include. A small dump of a couple thousand stories can be converted into a ZIM within a couple of minutes, but even an outdated full dump of multiple major sites may take weeks on a high-end device just for the final phase.

First, you need a lot of disk space. To estimate this, take the total space of all extracted(!) dumps you wish to include, multiply it by three and add some buffer to be safe. Yes, this may be within the 1-2TiB range, but be assured, this is mostly temporarily. You basically need a third of the space just for the raw stories, a third for the database, less than a third for the final ZIM and some more for temporary files. Once you are done and sure you don't need to build such a ZIM a second time, you can delete the dump and database.

Second, you need a lot of RAM. Again, this depends on the amount of stories you wish to include in the ZIM. Small dumps can be build with a couple GiB of RAM or even less, but for the full dump mentioned above 60GiB were already nearly not enough.

Third, you need time. Importing the stories may take a week or more, depending on how you import them. You may want to check the performance of your decompression tools before you begin. For example, some linux distributions ship with an outdated, very slow 7z tool that may increase extraction time by weeks. Running the implication may take another 1-2 days. The final build can take more than a week as well. You can pause the process between the individual imports and each stage, but the implication and final build must happen uninterrupted. These stages can also fail and may need to be restarted. Of course, the time requirements depend on the amount of stories you want to include and device you are using. The observations above are for the full story dump, but making small ZIMs is obviously faster.

## Usage

ZimFiction works in three stages: the import, the implication and the build phase. The import phase imports directories of stories and inserts them into a database. The implication phase is optional and tries to find additional tags of stories in the database. The build phase takes this database and builds a ZIM file.

Before we begin, be sure you have installed the `zimfiction` package. It is not on pypi, so instead clone the repo and install it (e.g. `pip install path/to/cloned/repo/`). You may want to setup a virtual environment to avoid compatibility problems, but this is generally optional.

First, you need one or more fanfiction dumps. You can probably find one of those rather easily on reddit. Alternatively, you can also create a directory and download fics there using fanficfare (in this case, using `html` as an output format is recommended).

Next, import the fics:

`zimfiction -v import <database> <directory> [--ignore-errors] [--workers]`

Here, `database` refers to an [sqlalchemy database url](https://docs.sqlalchemy.org/en/20/core/engines.html), e.g. `sqlite:///stories.sqlite`. You may gain significant performance gains by using a postgresql server hosted on the same device, ideally on a NVME and it is recommended to do so. `directory` is simply the path to one or more directories containing the dumps. As these dumps often miss some metadata, it is recommended to also specify `--ignore-errors`, which tells zimfiction to skip stories it can not parse (e.g. because the publisher is missing). You can set `--workers` to a value larger than 0 to use that many worker processes, which may speed up the import.

Now, optionally, run the implication:

`zimfiction -v find-implications [--delete] [--lazy] [--ao3-mergers PATH] <database>`

Just as before, `database` is a sqlalchemy database URL and should be the same value you used above. `--delete` tells ZimFiction to delete previously implied tags and is generally a good idea to specify. `---lazy` changes to lazy database loading and may either boost or reduce performance. `--ao3-mergers` should refer to a `tags-*.csv` file from the official AO3 data dump. If specified, canonical tags of stories will be searched for and added as implied tags.

Finally, build the ZIM:

`zimfiction -v build [--threaded] [--workers WORKERS] [--log-directory PATH] [--memprofile-directrory PATH] [--no-external-links] [--debug-skip-stories] <database> <zimpath>`

The `database` argument behaves like the one used by `zimfiction import`, the `zimpath` argument specifies the path to write the ZIM file to. You can specifiy `--threaded` to use threads for workers rather than individual processes, but this is not recommended and may significantly reduce performance with no benefit. `--workers` specifies the amount of workers that should be used to render the pages, the number of workers used for compression is unaffected. The remaining arguments are for debug purposes and should probably not be specified unless you are actively debugging the build process.
