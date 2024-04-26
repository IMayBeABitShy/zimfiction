"""
Unique-logic, based on the sqlalchemy unique object recipe.
"""


def _unique(session, cls, hashfunc, queryfunc, constructor, arg, kw):
    cache = getattr(session, '_unique_cache', None)
    if cache is None:
        session._unique_cache = cache = {}

    key = (cls, hashfunc(*arg, **kw))
    if key in cache:
        return cache[key]
    else:
        with session.no_autoflush:
            q = session.query(cls)
            q = queryfunc(q, *arg, **kw)
            obj = q.first()
            if not obj:
                obj = constructor(*arg, **kw)
                session.add(obj)
        cache[key] = obj
        return obj


class UniqueMixin(object):
    """
    Mix-in to make a database object 'unique'.

    A unique object will always refer to a single row, even if it is
    newly created.

    See https://github.com/sqlalchemy/sqlalchemy/wiki/UniqueObject for
    information and usage.
    """

    @classmethod
    def unique_hash(cls, *arg, **kw):
        raise NotImplementedError()

    @classmethod
    def unique_filter(cls, query, *arg, **kw):
        raise NotImplementedError()

    @classmethod
    def as_unique(cls, session, *arg, **kw):
        return _unique(
            session,
            cls,
            cls.unique_hash,
            cls.unique_filter,
            cls,
            arg, kw
        )


def clear_unique_cache(session):
    """
    Clear the unique cache of a session.

    @param session: session to clear unique cache of
    @type session: L{sqlalchemy.orm.Session}
    """
    session._unique_cache = {}
