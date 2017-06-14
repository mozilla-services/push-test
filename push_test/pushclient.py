import asyncio
import base64
import json
import uuid
import sys
import traceback
import logging
import concurrent

import aiohttp
import websockets
from py_vapid import Vapid


class PushException(Exception):
    pass


logger = logging.getLogger(__name__)


def output_msg(out=sys.stdout, **msg):
    print(json.dumps(msg), file=out)


class PushClient():
    """Smoke Test the Autopush push server"""
    def __init__(self, args, loop, tasks=None):
        self.config = args
        self.loop = loop
        self.connection = None
        self.pushEndpoint = None
        self.channelID = None
        self.notifications = []
        self.uaid = None
        self.recv = []
        self.tasks = tasks or []
        self.output = None
        self.vapid_cache = {}
        if args.key:
            self.vapid = Vapid().from_file(args.key)
        else:
            self.vapid = Vapid()
            self.vapid.generate_keys()

    def _cache_sign(self, claims):
        key = hash(json.dumps(claims))
        if key not in self.vapid_cache:
            self.vapid_cache[key] = self.vapid.sign(claims)
        return self.vapid_cache[key]

    async def _next_task(self):
        """Tasks are shared between active "cmd_*" commands
        and async "recv_*" events. Since both are reading off
        the same stack, we centralize that here.

        """
        try:
            task = self.tasks.pop(0)
            args = task[1]
            logging.debug(">>> cmd_{}".format(task[0]))
            await getattr(self, "cmd_" + task[0])(**(task[1]))
            return True
        except IndexError:
            await self.cmd_done()
            return False
        except PushException:
            raise
        except AttributeError:
            raise PushException("Invalid command: {}".format(task[0]))
        except Exception:
            traceback.print_exc()
            raise

    async def run(self,
                  server="wss://push.services.mozilla.com",
                  tasks=None):
        """Connect to a remote server and execute the tasks

        :param server: URL to the Push Server

        """
        if tasks:
            self.tasks = tasks
        if not self.connection:
            await self.cmd_connect(server)
        while await self._next_task():
            pass

    async def process(self, message):
        """Process an incoming websocket message

        :param message: JSON message content
        :return:

        """
        mtype = "recv_" + message.get('messageType').lower()
        logger.debug("<<< {}".format(mtype))
        try:
            await getattr(self, mtype)(**message)
        except AttributeError as ex:
            raise PushException(
                "Unknown messageType: {}".format(mtype)) from ex

    async def receiver(self):
        """Receiver handler for websocket messages

        """
        try:
            while self.connection:
                message = await self.connection.recv()
                await self.process(json.loads(message))
        except websockets.exceptions.ConnectionClosed:
            output_msg(out=self.output, status="Websocket Connection closed")

    # Commands:::

    async def _send(self, no_recv=False, **msg):
        """Send a message out the websocket connection

        :param no_recv: Flag to indicate if response is expected
        :param msg: message content
        :return:

        """
        output_msg(out=self.output, flow="output", msg=msg)
        try:
            await self.connection.send(json.dumps(msg))
            if no_recv:
                return
            message = await self.connection.recv()
            await self.process(json.loads(message))
        except websockets.exceptions.ConnectionClosed as ex:
            pass

    async def cmd_connect(self, server=None, **kwargs):
        """Connect to a remote websocket server

        :param server: Websocket url
        :param kwargs: ignored
        :return:

        """
        srv = self.config.server or server
        output_msg(out=self.output, status="Connecting to {}".format(srv))
        self.connection = await websockets.connect(srv)
        self.recv.append(asyncio.ensure_future(self.receiver()))

    async def cmd_close(self, **kwargs):
        """Close the websocket connection (if needed)

        :param kwargs: ignored
        :return:

        """
        output_msg(out=self.output, status="Closing socket connection")
        if self.connection and self.connection.state == 1:
            try:
                for recv in self.recv:
                    recv.cancel()
                self.recv = []
                await self.connection.close()
            except (websockets.exceptions.ConnectionClosed,
                    concurrent.futures._base.CancelledError):
                pass

    async def cmd_sleep(self, period=5, **kwargs):
        output_msg(out=self.output, status="Sleeping...")
        await asyncio.sleep(period)

    async def cmd_hello(self, uaid=None, **kwargs):
        """Send a websocket "hello" message

        :param uaid: User Agent ID (if reconnecting)

        """
        if not self.connection or self.connection.state != 1:
            await self.cmd_connect()
        output_msg(out=self.output, status="Sending Hello")
        args = dict(messageType="hello", use_webpush=1, **kwargs)
        if uaid:
            args['uaid'] = uaid
        elif self.uaid:
            args['uaid'] = self.uaid
        await self._send(**args)

    async def cmd_ack(self, channelID=None, version=None,
                      timeout=60, **kwargs):
        """Acknowledge a previous mesage

        :param channelID: Channel to acknowledge
        :param version: Version string for message to acknowledge
        :param kwargs: Additional optional arguments
        :param timeout: Time to wait for notifications (used by testing)
        :return:

        """
        timeout = timeout * 2
        while not self.notifications:
            output_msg(
                out=self.output,
                status="No notifications recv'd, Sleeping...")
            await asyncio.sleep(0.5)
            timeout -= 1
            if timeout < 1:
                raise PushException("Timeout waiting for messages")

        self.notifications.reverse()
        for notif in self.notifications:
            output_msg(
                out=self.output,
                status="Sending ACK",
                channelID=channelID or notif['channelID'],
                version=version or notif['version'])
            await self._send(messageType="ack",
                             channelID=channelID or notif['channelID'],
                             version=version or notif['version'],
                             no_recv=True)
        self.notifications = []

    async def cmd_register(self, channelID=None, key=None, **kwargs):
        """Register a new ChannelID

        :param channelID: UUID for the channel to register
        :param key: applicationServerKey for a restricted access channel
        :param kwargs: additional optional arguments
        :return:

        """
        output_msg(
            out=self.output,
            status="Sending new channel registration")
        channelID = channelID or self.channelID or str(uuid.uuid4())
        args = dict(messageType='register',
                    channelID=channelID)
        if key:
            args[key] = key
        args.update(kwargs)
        await self._send(**args)

    async def cmd_done(self, **kwargs):
        """Close all connections and mark as done

        :param kwargs: ignored
        :return:

        """
        output_msg(
            out=self.output,
            status="done")
        await self.cmd_close()
        await self.connection.close_connection()

    """
    recv_* commands handle incoming responses.Since they are asynchronous
    and need to trigger follow-up tasks, they each will need to pull and
    process the next task.
    """

    async def recv_hello(self, **msg):
        """Process a received "hello"

        :param msg: body of response
        :return:

        """
        assert(msg['status'] == 200)
        try:
            self.uaid = msg['uaid']
            await self._next_task()
        except KeyError as ex:
            raise PushException from ex

    async def recv_register(self, **msg):
        """Process a received registration message

        :param msg: body of response
        :return:

        """
        assert(msg['status'] == 200)
        self.pushEndpoint = msg['pushEndpoint']
        self.channelID = msg['channelID']
        output_msg(
            out=self.output,
            flow="input",
            msg=dict(
                message="register",
                channelID=self.channelID,
                pushEndpoint=self.pushEndpoint))
        await self._next_task()

    async def recv_notification(self, **msg):
        """Process a received notification message.
        This event does NOT trigger the next command in the stack.

        :param msg: body of response

        """
        def repad(str):
            return str + '===='[len(msg['data']) % 4:]

        msg['_decoded_data'] = base64.urlsafe_b64decode(
            repad(msg['data'])).decode()
        output_msg(
            out=self.output,
            flow="input",
            message="notification",
            msg=msg)
        self.notifications.append(msg)
        await self.cmd_ack()

    async def _post(self, session, url, data):
        """Post a message to the endpoint

        :param session: async session object
        :param url: pushEndpoint
        :param data: data to send
        :return:

        """
        # print ("Fetching {}".format(url))
        with aiohttp.Timeout(10, loop=session.loop):
            return await session.post(url=url, data=data)

    async def _post_session(self, url, headers, data):
        """create a session to send the post message to the endpoint

        :param url: pushEndpoint
        :param headers: dictionary of headers
        :param data: body of the content to send

        """
        async with aiohttp.ClientSession(
                loop=self.loop,
                headers=headers
        ) as session:
            reply = await self._post(session, url, data)
            return reply

    async def cmd_push(self, data=None, headers=None, claims=None):
        """Push data to the pushEndpoint

        :param data: message content
        :param headers: dictionary of headers
        :return:

        """
        if not self.pushEndpoint:
            raise PushException("No Endpoint, no registration?")
        if not headers:
            headers = {}
        if claims:
            headers.update(self._cache_sign(claims))
        output_msg(
            out=self.output,
            status="Pushing message",
            msg=repr(data))
        if data and 'content-encoding' not in headers:
            headers.update({
                    "content-encoding": "aesgcm128",
                    "encryption": "salt=test",
                    "encryption-key": "dh=test",
                })
        result = await self._post_session(self.pushEndpoint, headers, data)
        body = await result.text()
        output_msg(
            out=self.output,
            flow="http-out",
            pushEndpoint=self.pushEndpoint,
            headers=headers,
            data=repr(data),
            result="{}: {}".format(result.status, body))
