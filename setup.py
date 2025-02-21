"""setup.py for zimfiction"""

from setuptools import setup


setup(
    name="zimfiction",
    version="1.0.0",
    author="IMayBeABitShy",
    author_email="IMayBeABitShy@gmail.com",
    description="Build ZIM files from fiction dumps",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="fiction fanfiction ZIM",
    url="https://github.com/IMayBeABitShy/zimfiction/",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        ],
    packages=[
        "zimfiction",
        "zimfiction.db",
        "zimfiction.importer",
        "zimfiction.implication",
        "zimfiction.zimbuild",
        "zimfiction.exporter",
        ],
    include_package_data=True,
    install_requires=[
        "fs",
        "fs.archive",
        "py7zr",
        "iocursor",
        "sqlalchemy",
        "libzim >= 1.0.0",
        "htmlmin",
        "jinja2",
        "mistune",
        "EBookLib",
        "html2text",
        "beautifulsoup4",
        "pyScss",
        ],
    extras_require={
        "optimize": [
            "minify-html",
        ],
        "integration": [
            "psutil",
            "setproctitle",
        ],
    },
    entry_points={
        "console_scripts": [
            "zimfiction=zimfiction.cli:main",
        ],
    }
    )
