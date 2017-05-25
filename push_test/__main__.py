import asyncio
import base64
import json
import uuid

import aiohttp
import websockets

"""
from push_test.__main__ import PushClient, __main__; 
"""

class PushException(Exception):
    pass

class PushClient(object):

    def __init__(self, args, loop):
        self.config = args
        self.loop = loop
        self.connection = None
        self.pushEndpoint = None
        self.channelID = None
        self.notifications = []

    async def run(self,
                  server="wss://push.services.mozilla.com"):
        if not self.connection:
            self.connection = await websockets.connect(
                server or self.args.server)
        self.recv = asyncio.ensure_future(self.receiver())
        task = self.tasks.pop(0)
        await getattr(self, task[0])(**task[1])
        print("Done run")

    async def process(self, message):
        mtype = "recv_" + message.get('messageType').lower()
        try:
            await getattr(self, mtype)(**message)
        except AttributeError:
            raise PushException("Unknown messageType: {}".format(mtype))

    async def receiver(self):
        while True:
            message = await self.connection.recv()
            await self.process(json.loads(message))

    async def send(self, no_recv=False, **kwargs):
        print(">> {}".format(json.dumps(kwargs)))
        msg = kwargs
        if not self.connection:
            raise PushException("No connection")
        await self.connection.send(json.dumps(msg))
        if no_recv:
            return
        message = await self.connection.recv()
        await self.process(json.loads(message))

    async def hello(self, uaid=None, **kwargs):
        print("Sending Hello")
        await self.send(messageType="hello", use_webpush=1, **kwargs)

    async def ack(self, channelID=None, version=None, **kwargs):
        last = self.notifications[-1]
        print ("Sending ACK")
        await self.send(messageType="ack",
                        channelID=channelID or last['channelID'],
                        version=version or last['version'],
                        no_recv=True)
        print ("Ack sent")
        task = self.tasks.pop(0)
        await getattr(self, task[0])(**task[1])

    async def register(self, channelID=None, key=None, **kwargs):
        print("Sending new channel registration")
        channelID = channelID or self.channelID or str(uuid.uuid4())
        args = dict(messageType='register',
                    channelID=channelID)
        if key:
            args[key] = key
        args.update(kwargs)
        await self.send(**args)

    async def done(self, **kwargs):
        print("done")
        await self.connection.close()
        self.recv.cancel()

    async def recv_hello(self, **msg):
        assert msg['status'] == 200
        try:
            self.uaid = msg['uaid']
            task = self.tasks.pop(0)
            await getattr(self, task[0])(**task[1])
        except KeyError as ex:
            raise PushException from ex

    async def recv_register(self, **msg):
        assert msg['status'] == 200
        try:
            self.pushEndpoint = msg['pushEndpoint']
            self.channelID = msg['channelID']
            print("<< Register for {} : {}",
                  self.channelID,
                  self.pushEndpoint)
            task = self.tasks.pop(0)
            await getattr(self, task[0])(**task[1])
        except KeyError as ex:
            raise PushException from ex

    async def recv_notification(self, **msg):
        def repad(str):
            return str + '===='[len(msg['data']) % 4:]

        msg['_decoded_data'] = base64.urlsafe_b64decode(repad(msg['data']))
        print("<< notification: {}".format(msg['_decoded_data']))
        self.notifications.append(msg)
        task = self.tasks.pop(0)
        await getattr(self, task[0])(**task[1])

    async def _fetch(self, session, url, data):
        # print ("Fetching {}".format(url))
        with aiohttp.Timeout(10, loop=session.loop):
            return await session.post(url=url, data=data)

    async def post(self, url, headers, data):
        loop = asyncio.get_event_loop()
        async with aiohttp.ClientSession(
                loop=loop,
                headers=headers
        ) as session:
            reply = await self._fetch(session, url, data)
            body = await reply.text()
            return body

    async def push(self, data=None, headers=None):
        if data:
            if not headers:
                headers = {
                    "content-encoding": "aesgcm128",
                    "encryption": "salt=test",
                    "encryption-key": "dh=test",
                }
        result = await self.post(self.pushEndpoint, headers, data)
        print(result)


def __main__():
    #TODO: add args
    #TODO: pull tasks from a file
    tasks = [('hello', {}),
             ('register', {}),
             ('push', dict(
                 data="mary had a little lamb",
             )),
             ('ack', {}),
             ('done', {})
             ]

    loop = asyncio.get_event_loop()
    # loop.set_debug(1)

    client = PushClient({}, loop)
    client.tasks = tasks

    try:
        loop.run_until_complete(client.run())
    except websockets.ConnectionClosed:
        pass
    except Exception as ex:
        print("Unknown Exception: {}".format(ex))
    finally:
        loop.close()
