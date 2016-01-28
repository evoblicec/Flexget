from __future__ import unicode_literals, division, absolute_import

from math import ceil
from operator import itemgetter
from urllib import unquote

from flask import jsonify, request
from flask_restplus import inputs

from flexget.api import api, APIResource
from flexget.plugins.filter import seen

seen_api = api.namespace('seen', description='Managed Flexget seen entries and fields')

PLUGIN_TASK_NAME = 'seen_plugin_API'  # Name of task to use when adding entries via API

seen_field_object = {
    'type': 'object',
    'properties': {
        'id': {'type': 'integer'},
        'field': {'type': 'string'},
        'value': {'type': 'string'},
        'added': {'type': 'string'},
        'seen_entry_id': {'type': 'integer'}
    }
}

seen_object = {
    'type': 'object',
    'properties': {
        'id': {'type': 'integer'},
        'title': {'type': 'string'},
        'reason': {'type': 'string'},
        'task': {'type': 'string'},
        'added': {'type': 'string'},
        'local': {'type': 'string'},
        'fields': {'type': 'array', 'items': seen_field_object}
    }
}
seen_object_schema = api.schema('seen_object_schema', seen_object)

seen_object_input_schema = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'reason': {'type': 'string'},
        'task': {'type': 'string'},
        'local': {'type': 'boolean', 'default': False},
        'fields': {'type': 'object'}
    },
    'required': ['title', 'fields', 'task'],
    'additional_properties': False
}
seen_object_input_schema = api.schema('seen_object_input_schema', seen_object_input_schema)

seen_search_schema = {
    'type': 'object',
    'properties': {
        'seen_entries': {
            'type': 'array',
            'items': seen_object
        },
        'number_of_seen_entries': {'type': 'integer'},
        'total_number_of_pages': {'type': 'integer'},
        'page_number': {'type': 'integer'}
    }
}
seen_search_schema = api.schema('seen_search_schema', seen_search_schema)

seen_search_parser = api.parser()
seen_search_parser.add_argument('value', help='Search by any field value or leave empty to get entries')
seen_search_parser.add_argument('page', type=int, default=1, help='Page number')
seen_search_parser.add_argument('max', type=int, default=50, help='Seen entries per page')
seen_search_parser.add_argument('is_seen_local', type=inputs.boolean, default=None, help='Get results that are limited'
                                                                                         ' to local seen.')
seen_search_parser.add_argument('sort_by', choices=('title', 'task', 'added', 'local', 'id'), default='added',
                                help="Sort response by attribute")
seen_search_parser.add_argument('order', choices=('asc', 'desc'), default='desc', help='Sorting order.')

seen_delete_parser = api.parser()
seen_delete_parser.add_argument('value', help='Delete by value or leave empty to delete all. BE CAREFUL WITH THIS')
seen_delete_parser.add_argument('is_seen_local', type=inputs.boolean, default=None, help='Get results that are limited'
                                                                                         ' to local seen.')


@seen_api.route('/')
@api.doc(description='Get, delete or create seen entries')
class SeenSearchAPI(APIResource):
    @api.response(404, 'Page does not exist')
    @api.response(200, 'Successfully retrieved seen objects', seen_search_schema)
    @api.doc(parser=seen_search_parser)
    def get(self, session):
        """ Search for seen entries """
        args = seen_search_parser.parse_args()
        value = args['value']
        page = args['page']
        max_results = args['max']
        is_seen_local = args['is_seen_local']
        sort_by = args['sort_by']
        order = args['order']
        # Handles default if it explicitly called
        if order == 'desc':
            order = True
        else:
            order = False

        if value:
            value = unquote(value)
            value = '%' + value + '%'
        seen_entries_list = seen.search(value, is_seen_local, session)
        count = len(seen_entries_list)

        pages = int(ceil(count / float(max_results)))
        seen_entries = []
        if page > pages and pages != 0:
            return {'error': 'page %s does not exist' % page}, 404

        start = (page - 1) * max_results
        finish = start + max_results
        if finish > count:
            finish = count

        for seen_entry_num in range(start, finish):
            seen_entries.append(seen_entries_list[seen_entry_num].to_dict())

        sorted_seen_entries_list = sorted(seen_entries, key=itemgetter(sort_by), reverse=order)

        return jsonify({
            'seen_entries': sorted_seen_entries_list,
            'number_of_seen_entries': count,
            'page_number': page,
            'total_number_of_pages': pages
        })

    @api.response(400, 'A matching seen object is already added')
    @api.response(200, 'Successfully added new seen object', seen_object_schema)
    @api.validate(seen_object_input_schema)
    def post(self, session):
        """ Manually add entries to seen plugin """
        data = request.json
        kwargs = {
            'title': data.get('title'),
            'task_name': PLUGIN_TASK_NAME,
            'fields': data.get('fields'),
            'reason': data.get('reason'),
            'local': data.get('local', False),
            'session': session
        }
        values = [value for value in kwargs['fields'].values()]
        exist = seen.search_by_field_values(field_value_list=values, task_name=PLUGIN_TASK_NAME, local=kwargs['local'],
                                            session=session)
        if exist:
            return {'status': 'error',
                    'message': "Seen entry matching the value '{0}' is already added".format(exist.value)}, 400

        seen_entry = seen.add(**kwargs)
        return jsonify({
            'status': 'success',
            'message': 'successfully added seen object',
            'seen_object': seen_entry
        })

    @api.response(500, 'Delete process failed')
    @api.response(200, 'Successfully delete all entries')
    @api.doc(parser=seen_delete_parser)
    def delete(self, session):
        """ Delete seen entries """
        args = seen_delete_parser.parse_args()
        value = args['value']
        is_seen_local = args['is_seen_local']

        if value:
            value = unquote(value)
            value = '%' + value + '%'
        seen_entries_list = seen.search(value, is_seen_local, session)
        count = len(seen_entries_list)

        for entry in seen_entries_list:
            try:
                seen.forget_by_id(entry.id)
            except ValueError as e:
                return {'status': 'error',
                        'message': 'Could not delete entry ID {0}'.format(entry.id)}, 500
        return {'status': 'success',
                'message': 'Successfully delete {0} entries from DB'.format(count)}


@seen_api.route('/<int:seen_entry_id>')
@api.doc(params={'seen_entry_id': 'ID of seen entry'}, description='Delete a specific seen entry via its ID')
@api.response(500, 'Delete process failed')
@api.response(200, 'Successfully deleted entry')
class SeenSearchAPI(APIResource):
    def delete(self, seen_entry_id, session):
        """ Delete seen entry by ID """
        try:
            seen.forget_by_id(seen_entry_id)
        except ValueError as e:
            return {'status': 'error',
                    'message': 'Could not delete entry ID {0}'.format(seen_entry_id)}, 500
        return {'status': 'success',
                'message': 'Successfully delete seen entry ID {0} from DB'.format(seen_entry_id)}
