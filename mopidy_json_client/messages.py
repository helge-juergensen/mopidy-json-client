import time
import logging
import json
import threading


logger = logging.getLogger(__name__)


class RequestMessage(object):

    msg_counter = 0

    def __init__(self, method,
                 on_result=None,
                 timeout=0,
                 **params):

        self.id_msg = self._next_id_msg()
        self.method = method
        self.params = params
        self.callback = on_result if on_result \
            else self.unlock
        self.locked = False if on_result or not timeout \
            else True
        self.start_time = time.time()
        self.timeout = timeout
        self.result = None

        self.json_message = self.compose_json_msg()

    @classmethod
    def _next_id_msg(cls):
        cls.msg_counter += 1
        return cls.msg_counter

    def unlock(self, result):
        self.result = result
        self.locked = False

    def compose_json_msg(self):
        json_msg = {
            'id': self.id_msg,
            'method': self.method,
            'params': self.params,
            'jsonrpc': '2.0'}
        return json.dumps(json_msg)

    def wait_for_result(self):
        while self.locked:
            if time.time() - self.start_time > self.timeout:
                # TODO: raise Error right
                # raise TimeoutError('Time-out on request')
                #'[TIMEOUT] On request: {method}s ({timeout}d secs)'.format(self.requests[id_msg]))
                logger.info('[TIMEOUT] On request: %s (%d secs)',
                            self.method,self.timeout)

                return None
            time.sleep(0.1)  # To save resouces
        return self.result


class ResponseMessage(object):

    _on_event = None
    _on_result = None
    _on_error = None

    @classmethod
    def set_handlers(cls,
                     on_msg_event=None,
                     on_msg_result=None,
                     on_msg_error=None):

        cls._on_event = on_msg_event
        cls._on_result = on_msg_result
        cls._on_error = on_msg_error

    @classmethod
    def parse_json_message(self, message):
         # Unpack received message
        msg_data = json.loads(message)

        # JSON-RPC Message(response to a request)
        if 'jsonrpc' in msg_data:
            # Check for integrity
            assert msg_data['jsonrpc'] == '2.0', 'Wrong JSON-RPC version: %s' % msg_data['jsonrpc']
            assert 'id' in msg_data, 'JSON-RPC message has no id'

            # Process received message
            msg_id = msg_data.get('id')
            error_data = msg_data.get('error')
            result_data = msg_data.get('result')

            if error_data and self._on_error:
                threading.Thread(
                    name='Error-ID%d' % msg_id,
                    target=self._on_error,
                    kwargs={'id_msg': msg_id,
                            'error': self.format_app_error(error_data)},
                    ).start()

            # Send result even if 'None' to close request
            if self._on_result:
                threading.Thread(
                    name='Result-ID%d' % msg_id,
                    target=self._on_result,
                    kwargs={'id_msg': msg_id,
                            'result': result_data},
                    ).start()

        # Mopidy CoreListener Event
        elif 'event' in msg_data:
            if self._on_event:
                event = msg_data.pop('event')
                threading.Thread(
                    target=self._on_event,
                    kwargs={'event': event,
                            'event_data': msg_data}
                    ).start()

        # Received not-parseable message
        else:
            #print ('Unparseable JSON-RPC message received: %s', message=message)
            logger.warning('Unparseable JSON-RPC message received', message=message)


    @staticmethod
    def format_app_error(input_error):
        ''' Compose custom error message with four fields
                title: error title
                error: error text
                type: error type (i.e. excepction class)
                traceback: traceback info gathered
        '''
        output = {}

        output['title'] = input_error.get('message')
        inner_data = input_error.get('data')
        if isinstance(inner_data, basestring):
            output['error'] = inner_data
        elif 'message' in input_error:
            output['error'] = inner_data.get('message')
            output['type'] = inner_data.get('type')
            output['traceback'] = inner_data.get('traceback')
        else:
            output['error'] = 'Error #' + input_error.get('code')

        return output
