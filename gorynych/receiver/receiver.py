'''
Thinkless copy/paste.
I hope it works.
'''

__author__ = 'Boris Tsema'
import time
import cPickle
import collections

from twisted.internet import protocol, task, defer, reactor
from twisted.application.service import Service
from twisted.python import log

from pika.connection import ConnectionParameters
from pika.adapters.twisted_connection import TwistedProtocolConnection

from gorynych.receiver.parsers import GlobalSatTR203, TeltonikaGH3000UDP,\
                                      MobileTracker, App13Parser, SBDParser, \
                                      RedViewGT60, PathMakerParser
from gorynych.receiver.protocols import TR203ReceivingProtocol, MobileReceivingProtocol,\
                                        App13ProtobuffMobileProtocol, IridiumSBDProtocol, \
                                        RedViewGT60Protocol, PathMakerProtocol

################### Network part ##########################################


class TR203ReceivingFactory(protocol.ServerFactory):

    protocol = TR203ReceivingProtocol

    def __init__(self, service):
        self.service = service


class MobileReceivingFactory(protocol.ServerFactory):
    '''
    Factory for old mobile application which is not used.
    '''

    protocol = MobileReceivingProtocol

    def __init__(self, service):
        self.service = service


class App13ReceivingFactory(protocol.ServerFactory):
    '''
    Factory for mobile application which sends data in protocol buffer format.
    '''

    protocol = App13ProtobuffMobileProtocol

    def __init__(self, service):
        self.service = service


class SBDMobileReceivingFactory(protocol.ServerFactory):
    '''
    Factory for satellite hybrid tracker.
    '''

    protocol = IridiumSBDProtocol

    def __init__(self, service):
        self.service = service


class GT60ReceivingFactory(protocol.ServerFactory):

    protocol = RedViewGT60Protocol

    def __init__(self, service):
        self.service = service


class PmtrackerReceivingFactory(protocol.ServerFactory):

    protocol = PathMakerProtocol

    def __init__(self, service):
        self.service = service


###################### Different receivers ################################

class FileReceiver:
    '''This class just write a message to file.'''
    # XXX: do smth clever with interfaces. It's not good to have a class with
    # just __init__ and one method.

    running = 1

    def __init__(self, filename):
        self.filename = filename

    def write(self, data):
        # XXX: this is a blocking operation. It's bad in Twisted. Rework.
        fd = open(self.filename, 'a')
        fd.write(''.join((str(data), '\r\n')))
        fd.close()

class CheckReceiver:
    running = 1
    def __init__(self, filename):
        self.filename = filename
        # imei: time
        self.messages = collections.defaultdict(dict)
        self.coords = collections.defaultdict(dict)

    def write(self, data):
        '''data is a dict with parsed data.'''
        self.messages[data['imei']] = int(time.time())
        self.coords[data['imei']] = (data['lat'], data['lon'], data['alt'],
        data['h_speed'])


class RabbitMQService(Service):
    '''
    This is base service for consuming data from RabbitMQ.
    All other services with the same goals need to be inherited from this one.
    Every service is working with only one exchange.
    '''

    exchange = 'default'
    exchange_type = 'direct'
    durable_exchange = False
    exchange_auto_delete = False

    queue = 'default' # not sure about this
    queues_durable = False
    queue_auto_delete = False
    queues_exclusive = False
    queues_no_ack = False

    def __init__(self, **kw):
    #        pars = parse_parameters(**kw) # TODO: parameters parsing
        # XXX: workaround
        self.pars = kw
        self.exchange = self.pars.get('exchange',
            self.exchange)
        self.durable_exchange = self.pars.get('durable_exchange',
            self.durable_exchange)
        self.exchange_type = self.pars.get('exchange_type',
            self.exchange_type)
        self.exchange_auto_delete = self.pars.get('auto_delete',
            self.exchange_auto_delete)
        self.queue_auto_delete = self.pars.get('auto_delete_queues',
            self.queue_auto_delete)
        self.queues_durable = self.pars.get('queues_durable',
            self.queues_durable)
        self.queues_exclusive = self.pars.get('queues_exclusive',
            self.queues_exclusive)
        self.queues_no_ack = self.pars.get('queues_no_ack',
            self.queues_no_ack)
        self.opened_queues = {}
        self.running_checker = task.LoopingCall(self.__check_if_running)
        self.running_checker.start(0.5)

    def __check_if_running(self):
        if self.running:
            self.when_started()
            self.running_checker.stop()

    def when_started(self):
        '''Override this method if you want to do something after service have been started.'''
        pass

    def startService(self):
        cc = protocol.ClientCreator(reactor, TwistedProtocolConnection,
            ConnectionParameters())
        d = cc.connectTCP(self.pars['host'], self.pars['port'])
        d.addCallback(lambda protocol: protocol.ready)
        d.addCallback(self.__on_connected)
        d.addCallback(lambda _: Service.startService(self))
        d.addCallback(lambda _:log.msg("Service started on exchange %s type %s."
                                       % (self.exchange, self.exchange_type)))

    def stopService(self):
        for queue in self.opened_queues.keys():
            self.channel.queue_delete(queue=queue)
        Service.stopService(self)

    def __on_connected(self, connection):
        log.msg('RabbitmqSender: connected.')
        self.defer = connection.channel()
        self.defer.addCallback(self.__got_channel)
        self.defer.addCallback(self.create_exchange)

    def __got_channel(self, channel):
        log.msg('RabbitmqSender: got the channel.')
        self.channel = channel

    def create_exchange(self, _):
        return self.channel.exchange_declare(
            exchange=self.exchange,
            durable=self.durable_exchange,
            type=self.exchange_type,
            auto_delete=self.exchange_auto_delete)

    def open(self, queue_name, routing_keys=[], mode='r'):
        '''
        Create and bind queue. Add queue object to self.opened_queues.
        Return Deferred instance which return queue name.
        Usage:
        d = open(queue_name)
        d.addCallback(lambda queue_name: handle(queue_name))
        message_from_queue = read(self.opened_queues[queue_name])
        This method us necessary only for consuming, you needn't call this for
        sending messages to RabbitMQ.
        '''
        assert isinstance(queue_name, str), 'Queue name must be a string.'
        assert len(queue_name) > 0, 'Can not use empty string as queue name.'

        keys = self.process_routing_keys(routing_keys)
        log.msg('Routing keys: %s' % keys)
        d = defer.Deferred()
        log.msg("Opening queue", queue_name)
        d.addCallback(self.create_queue)
        d.addCallback(self.bind_queue, keys)
        if mode == 'r':
            d.addCallback(self.start_consuming)
            d.addCallback(self.get_queue, queue_name)
        if mode == 'w':
            d.addCallback(lambda _:log.msg('Opened for writing.'))
        d.addErrback(log.err)
        d.callback(queue_name)
        return d

    def process_routing_keys(self, routing_keys):
        '''
        Check routing keys, return list with keys. Don't use with 'topic'
        exchange type as it has limitation on routing key length and more
        special formatting can be needed.
        '''
        result = []
        if not routing_keys:
            result.append('')
            return result
        elif not isinstance(routing_keys, list):
            result.append(str(routing_keys))
            return result
        else:
            # Getting flat list.
            flatten_list = ','.join(map(str, routing_keys)).split(',')
            log.msg(flatten_list)
        return flatten_list

    def create_queue(self, queue_name):
        log.msg('Creating queue %s' % queue_name)
        return self.channel.queue_declare(
            queue=queue_name,
            auto_delete=self.queue_auto_delete,
            durable=self.queues_durable,
            exclusive=self.queues_exclusive)

    def bind_queue(self, frame, routing_keys):
        for key in routing_keys:
            log.msg('Bind %s with key %s.' % (frame.method.queue, key))
            self.channel.queue_bind(
                queue=frame.method.queue,
                exchange=self.exchange,
                routing_key=key
            )
        log.msg('Queue %s bound.' % frame.method.queue)
        return frame.method.queue

    def start_consuming(self, queue):
        '''Return queue and consumer tag.'''
        log.msg('Start consuming from queue', queue)
        return self.channel.basic_consume(
            queue=queue,
            no_ack=self.queues_no_ack)

    def get_queue(self, queue_and_consumer_tag, queue_name):
        queue, consumer_tag = queue_and_consumer_tag
        if self.opened_queues.has_key(queue_name):
            raise RuntimeError('Queue has been opened already.')
        else:
            self.opened_queues[queue_name] = queue
            return queue_name

    def read(self, queue_name):
        '''Read opened queue.'''
        #        log.msg(self.opened_queues[queue_name])
        d = self.opened_queues[queue_name].get()
        return d.addCallback(lambda  ret: self.handle_payload(queue_name,
            *ret))

    def handle_payload(self, queue_name, channel, method_frame, header_frame, \
            body):
        '''Override this method for doing something usefull.'''
        log.msg("Message received from queue %s: %s" % (queue_name,body))
        #        log.msg('Also received: %s %s %s' % (channel, method_frame,
        #                                             header_frame))
        #        Also received:
        #        <pika.channel.Channel object at 0x101aa4f10>
        #        <Basic.Deliver(['consumer_tag=ctag1.0', 'redelivered=False', 'routing_key=', 'delivery_tag=4', 'exchange=default'])>
        #        <BasicProperties([])>
        return body

    def write(self, data, key='', exchange=''):
        if data:
            exchange = exchange or self.exchange
            # log.msg('write data %s to exchange %s' % (data, exchange))
            self.channel.basic_publish(exchange=exchange,
                routing_key=key,
                body=self.serialize(data))

    def serialize(self, data):
        return str(data)

    def close(self, queue_name):
        '''Close consuming from queue.'''
        del self.opened_queues[queue_name]
        d = self.channel.queue_delete(queue=queue_name)
        d.addErrback(log.err)


class ReceiverRabbitService(RabbitMQService):

    def serialize(self, data):
        return cPickle.dumps(data, protocol=2)


class ReceiverService(Service):
    parsers = dict(tr203=GlobalSatTR203(), telt_gh3000=TeltonikaGH3000UDP(),
                   mobile=MobileTracker(), app13=App13Parser(),
                   new_mobile_sbd=SBDParser(), gt60=RedViewGT60(),
                   pmtracker=PathMakerParser())

    def __init__(self, sender, audit_log):
        self.sender = sender
        self.audit_log = audit_log
        self.tr203 = GlobalSatTR203()
        ##### checker
        self.messages = dict()
        self.coords = dict()

    def check_message(self, msg, **kw):
        '''
        Checks message correctness. If correct, logs it, else logs the error.
        '''
        receiving_time = time.time()
        device_type = kw.get('device_type', 'tr203')
        d = defer.succeed(msg)
        d.addCallback(self.parsers[device_type].check_message_correctness)
        d.addCallbacks(self.audit_log.log_msg,
            self.audit_log.log_err,
            callbackArgs=[],
            callbackKeywords={'time':receiving_time,
                'proto': kw.get('proto', 'Unknown'),
                'device': kw.get('device_type', 'Unknown')},
            errbackArgs=[],
            errbackKeywords={'data': msg, 'time': receiving_time,
                'proto': kw.get('proto', 'Unknown'),
                'device':kw.get('device_type', 'Unknown')})
        if not self.sender.running:
            log.msg("Received but not sent: %s" % msg)
        d.addErrback(self._handle_error)
        d.addErrback(log.err)
        return d

    def store_point(self, message):
        d = defer.Deferred()
        if isinstance(message, list):
            for item in message:
                # item=item magic is required by lambda to grab item correctly
                # otherwise item is always message[-1]. Do not modify!
                d.addCallback(lambda _, item=item: self.sender.write(item))
                self._save_coords_for_checker(item)
        else:
            d.addCallback(lambda _: self.sender.write(message))
            self._save_coords_for_checker(message)

        d.callback('go!')
        return d

    def handle_message(self, msg, **kw):
        """
        Backwards compatible method: checks message, parses it, assumes
        that result is a point and stores it.
        """
        dev_type = kw.get('device_type', 'tr203')
        result = self.check_message(msg, **kw)
        result.addCallback(self.parsers[dev_type].parse)
        result.addCallback(self.store_point)
        return result

    def _save_coords_for_checker(self, parsed):
        self.messages[parsed['imei']] = int(time.time())
        self.coords[parsed['imei']] = (parsed['lat'], parsed['lon'],
        parsed['alt'], parsed['h_speed'], int(time.time()) )
        return parsed

    def _handle_error(self, failure):
        failure.trap(EOFError)


class AuditLog:
    '''Base class for audit logging classes.'''

    def _format(self, **kw):
        result = kw
        timelist = ['time', 'ts', 'timestamp']
        datalist = ['data', 'msg', 'message']
        for key in kw.keys():
            if key in timelist:
                x = int(kw[key])
                del kw[key]
                result['ts'] = x
            if key in datalist:
                x = str(kw[key])
                del kw[key]
                result['msg'] = x
        return result

    def _write_log(self, log_message):
        raise NotImplementedError('You need to implement log writing.')

    def log_err(self, failure, **kw):
        ''' Receive Failure object.'''
        kwargs = kw
        kwargs['err'] = failure.getErrorMessage()
        formatted_msg = self._format(**kwargs)
        self._write_log(formatted_msg)
        raise EOFError()

    def log_msg(self, msg, **kw):
        kwargs = kw
        kwargs['msg'] = msg
        formatted_msg = self._format(**kwargs)
        self._write_log(formatted_msg)
        return msg


class AuditFileLog(AuditLog):
    '''This class log messages to file.'''

    def __init__(self, logname):
        self.name = logname

    def _write_log(self, log_message):
        fd = open(self.name, 'a')
        fd.write(''.join((bytes(log_message), '\r\n')))
        fd.close()


class DumbAuditLog(AuditLog):
    def _write_log(self, log_message):
        pass


class FakeRabbitMQService(object):
    """
    This is a special class to test classes derived from RabbitMQService.
    Put your derived class as an argument to the constructor and you'll get the
    patched version of it so you can send and read messages without touching
    any actual RabbitMQ mechanics.

    Don't know where to put it. Let it be here for a while.
    """

    def __new__(self, derived_class):
        import mock
        import types

        def mock_write(target, data, key='', exchange=''):
            target.storage = data

        def mock_read(target, queue_name):
            return target.storage

        with mock.patch.object(derived_class, '__init__') as patched:
            patched.return_value = None
            instance = derived_class()
            instance.write = types.MethodType(mock_write, instance)
            instance.read = types.MethodType(mock_read, instance)
            return instance
