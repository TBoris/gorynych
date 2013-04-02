'''
Resources for RESTful API.
'''
import os
from string import Template

from twisted.web import resource, server
from twisted.internet import defer

class BadParametersError(Exception):
    '''
    Raised when bad parameters has been passed to the system.
    '''

JSON_TEMPLATES_DIR = 'json_templates'

def load_json_templates(dir):
    result = dict()
    files_list = filter(os.path.isfile,
        map(lambda x: os.path.join(dir, x), os.listdir(dir)))
    for filename in files_list:
        # read every nonempty *.json file and put content into json_templates
        if filename.endswith('.json') and os.stat(filename).st_size > 0:
            result[os.path.basename(filename).split('.')[0]] =\
                                                Template(open(filename).read())
    return result


JSON_TEMPLATES = load_json_templates(os.path.join(os.path.dirname(__file__),
    JSON_TEMPLATES_DIR))


def json_renderer(template_values, template_name,
                  templates_dict=JSON_TEMPLATES):

    def render(value, template):
        ''' Do actual rendering. Return string.
        '''
        return template.substitute(value)

    # get template from a dict
    template = templates_dict.get(template_name)
    if not template:
        raise ValueError("Template with such name doesn't exist.")

    if isinstance(template_values, list):
        # Result will be json array.
        result = '[' + render(template_values[0], template)
        for value in template_values[1:]:
            json_obj = render(value, template)
            result = ','.join((result, json_obj))
        result = ''.join((result, ']'))
        return result

    elif isinstance(template_values, dict):
        return render(template_values, template)
    else:
        raise TypeError("Dictionary must be passed as container for template"
                        " values.")


class APIResource(resource.Resource):
    '''
    Base API resource class.
    '''
    default_content_type = 'application/json'
    renderers = {'application/json': json_renderer}
    name = 'APIResource'
    service_command = {}

    def __init__(self, tree, service):
        resource.Resource.__init__(self)
        self.tree = tree
        self.service = service

    def getChild(self, path, request):
        """
        Dinamically return new child.
        @param path:
        @type path:
        @param request:
        @type request:
        @return: api resource
        @rtype: C{Resource}
        """
        if path == '':
            return self
        return self.tree[path]['leaf'](
                                self.tree[path]['tree'], self.service)

    def render_GET(self, request):
        d = defer.Deferred()
        d.addCallback(parameters_from_request)
        d.addCallbacks(getattr(self.service, self.service_command['get']))
        d.addCallbacks(self.resource_renderer,
                       callbackArgs=[request])
        d.addCallbacks(self.write_request)
        d.callback((request.uri, request.args))
        return server.NOT_DONE_YET

    def render_POST(self, request):
        d = defer.Deferred()
        d.addCallback(parameters_from_request)
        d.addCallbacks(getattr(self.service, self.service_command['post']))
        d.addCallbacks(self.resource_created,
                       callbackArgs=[request], errbackArgs=[])
        d.addCallbacks(self.write_request)
        d.callback((request.uri, request.args))
        return server.NOT_DONE_YET

    def render_PUT(self, request):
        d = defer.Deferred()
        d.addCallback(parameters_from_request)
        d.addCallbacks(getattr(self.service, self.service_command['put']))
        d.addCallbacks(self.change_resource,
                       callbackArgs=[request], errbackArgs=[])
        d.addCallbacks(self.write_request)
        d.callback((request.uri, request.args))
        return server.NOT_DONE_YET

    def resource_renderer(self, res, req):
        '''
        Receive result from Application Service and represent it as http
        entity.
        '''
        content_type = req.responseHeaders.getRawHeaders('content-type',
            'application/json')
        req.setResponseCode(200)
        req.setHeader('Content-Type', content_type)
        resurce_representation = self.read(res)
        body = self.renderers[content_type](resurce_representation, self.name)
        req.setHeader('Content-Length', bytes(len(body)))
        return req, body

    def read(self, res):
        return res

    def resource_created(self, res, req):
        '''
        Handle situation when new resource has been created.
        @type req: L{twisted.web.server.Request}
        '''
        req, body = self.resource_renderer(res, req)
        req.setResponseCode(201)
        return req, body

    def change_resource(self, res, req):
        req, body = self.resource_renderer(res, req)
        return req, body

    def write_request(self, (req, body)):
        '''
        Receive request with body and write it back to channel.
        '''
        req.write(body)
        req.finish()


def parameters_from_request(req):
    '''
    Return parameters from request arguments and/or URL.
    @param req: string which represent request.uri, and dict request.args
    @type req: C{tuple}
    '''
    uri, args = req
    assert isinstance(args, dict), "Wrong args has been passed."
    result = args
    def insert(key, value):
        '''
        Insert only unexistent or unequal to existent values for key.
        '''
        if result.has_key(key) and result[key] != value:
            raise BadParametersError("Two different values for one parameter.")
        else:
            result[key] = value
    path = uri.split('?')[0].split('/')
    # remove '' elements from list
    try:
        while True:
            index = path.index('')
            path.pop(index)
    except ValueError:
        pass
    for index, item in enumerate(path):
        if index % 2:
            insert(path[index - 1], path[index])

    return result


class ContestResourceCollection(APIResource):
    '''
    Resource /contest
    '''
    allowedMethods = ["GET", "POST"]
    service_command = dict(post='create_new_contest', get='get_contests')
    name = 'contest_collection'


class ContestResource(APIResource):
    '''
    Resource /contest/{id}
    '''
    service_command = dict(get='get_contest', put='change_contest')
    name = 'contest'


class RaceResourceCollection(APIResource):
    '''
    Resource /contest/{id}/race
    '''
    service_command = dict(get='get_races', post='create_new_race')

class RaceResource(APIResource):
    '''
    Resource /contest/{id}/race/{id}
    '''
    service_command = dict(get='get_race', put='change_race')

class ParagliderResourceCollection(APIResource):
    '''
    Resource /contest/{id}/race/{id}/paraglider
    '''
    service_command = dict(get='get_race_paragliders')

class ParagliderResource(APIResource):
    '''
    Resource /contest/{id}/race/{id}/paraglider/{id}
    '''
    service_command = dict(get='get_paraglider')
