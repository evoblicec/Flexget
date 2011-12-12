import logging
from optparse import SUPPRESS_HELP
from sqlalchemy.orm.query import Query
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import Executable, ClauseElement, _literal_as_text
from flexget import manager
from flexget.plugin import register_plugin, register_parser_option
from flexget.event import event

log = logging.getLogger('explain_sql')


class Explain(Executable, ClauseElement):

    def __init__(self, stmt):
        self.statement = _literal_as_text(stmt)

        
@compiles(Explain)
def pg_explain(element, compiler, **kw):
    text = 'EXPLAIN QUERY PLAN ' + compiler.process(element.statement)
    return text


class ExplainQuery(Query):
    
    def __iter__(self):
        log.info('Query:\n\t%s' % unicode(self).replace('\n', '\n\t'))
        explain = self.session.execute(Explain(self)).fetchall()
        text = '\n\t'.join('|'.join(str(x) for x in line) for line in explain)
        log.info('Explain Query Plan:\n\t%s' % text)
        return Query.__iter__(self)


@event('manager.execute.started')
def register_sql_explain(man):
    if man.options.explain_sql:
        maininit = manager.Session.__init__
        
        def init(*args, **kwargs):
            return maininit(*args, query_cls=ExplainQuery, **kwargs)
        manager.Session.__init__ = init


@event('manager.execute.completed')
def deregister_sql_explain(man):
    if man.options.explain_sql:
        manager.Session = sessionmaker()


register_parser_option('--explain-sql', action='store_true', dest='explain_sql', default=False,
                       help=SUPPRESS_HELP)
