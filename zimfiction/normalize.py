"""
This module contains functions for normalizing names of tags, categories... and so on.

Now, this may be a bit unfortunate, but we use the term "normalize" for
two similar, yet different things that happen at different times.

First, functions like L{normalize_tag} create a normalized "encoding" of
the tags to make it safe for use in URLs. This happens during the build
stage.

Secondly, functions like L{normalize_relationship} try to "normalize" a
tags that can be written in different ways such that the same tag is
always written the same way.
"""

# ALLOWED_TAG_LETTERS = re.compile(r"[^\w\.\(\)|\!\?\-]")


def normalize_tag(tag):
    """
    Normalize a tag so it works in URLs.

    @param tag: tag to normalize
    @type tag: L{str}
    @return: the normalized tag
    @rtype: L{str}
    """
    # return ALLOWED_TAG_LETTERS.sub("_", tag)
    # return urllib.parse.quote_plus(tag)
    tag = tag.replace("+", "_plus_").replace(" ", "+").replace("/", "_slash_")
    tag = tag.replace("<", "_lchevron_").replace(">", "_rchevron_")
    return tag


def normalize_relationship(tag):
    """
    Normalize a relationship such that "a/b", "b/a" and "a / b" reference
    the same relationship.

    @param tag: relationship to normalize
    @type tag: L{str}
    @return: the normalized relationship
    @rtype: L{str}
    """
    for sep in ("/", "&"):
        if sep in tag:
            tag = tag.replace(" {} ".format(sep), sep)
        splitted = [e.strip() for e in tag.split(sep)]
        tag = " {} ".format(sep).join(sorted(splitted))
    return tag


def normalize_category(category):
    """
    Normalize a category in order to merge very similiar categories together.

    @param category: name of category to normalize
    @type category: L{str}
    @return: the normalized category name
    @rtype: L{str}
    """
    # remove starting #
    # while there are probably categories using the #, most of them are
    # wrong
    while category.startswith("#"):
        category = category[1:]
    # remove "
    # for the same reason as above
    category = category.replace('"', "").replace("'", "")
    # remove "- Fandom", as we do not need this differentiation
    category = category.replace("- Fandom", "")
    # replace "<" and ">" - they mess with HTML
    category = category.replace("<", "").replace(">", "")
    # remove various special characters
    category = category.replace("\n", "").replace("\\", "").replace("\x00", "").replace("\r", "")
    # strip non-printable start and end characters
    category = category.strip()
    # at this time, the category name may be empty (it really shouldn't)
    # in this case, fall back to a new, catch-all name
    if not category:
        category = "[Unknown category]"
    # ensure first letter is upper case
    category = category[0].upper() + category[1:]
    # done
    return category

