import asyncio
import base64
import io
import json
import unittest

import pytest
import websockets
from mock import Mock, patch

from push_test.pushclient import PushClient, PushException


class TrialSettings(object):
    def __init__(self):
        self.server = "localhost"
        self.key = None


class Test_PushClient(unittest.TestCase):

    async def mock_connect(self):
        mconnect = Mock(spec=websockets.protocol.WebSocketCommonProtocol)
        mconnect.state = 1
        for f in self.mocks:
            setattr(mconnect, f, asyncio.coroutine(self.mocks[f]))
        self.mock_connect = mconnect
        return asyncio.coroutine(mconnect)

    def setUp(self):
        self.mocks = dict(send=Mock(),
                          recv=Mock(return_value="Dummy String"),
                          close=Mock(),
                          close_connection=Mock())
        self.output = io.StringIO()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = PushClient(loop=self.loop, args=TrialSettings())
        self.client.output = self.output
        self.tasks = [
            ["hello", {}],
        ]

    def scan_log(self, phrase):
        self.output.seek(0)
        lines = self.output.readlines()
        return any(phrase in line for line in lines)

    @patch('websockets.connect')
    def test_run(self, m_connect):
        async def go():
            await self.client.run(tasks=self.tasks)

        self.mocks['recv'] = Mock(return_value=json.dumps(
            {"messageType": "hello",
             "status": 200,
             "uaid": "uaidValue",
             "channelID": "chidValue"}
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())
        assert self.client.uaid == "uaidValue"
        assert len(self.client.tasks) == 0
        call_args = json.loads(self.mocks['send'].call_args[0][0])
        assert call_args == dict(messageType="hello", use_webpush=1)
        self.mocks['recv'].assert_called()
        self.mocks['close'].assert_called()
        self.mocks['close_connection'].assert_called()

    @patch('websockets.connect')
    def test_run_conn_closed(self, m_connect):
        async def go():
            await self.client.run(tasks=self.tasks)

        self.mocks['recv'] = Mock(
            side_effect=websockets.exceptions.ConnectionClosed(
                code=1000,
                reason="mock"
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())
        assert len(self.client.tasks) == 0
        call_args = json.loads(self.mocks['send'].call_args[0][0])
        assert call_args == dict(messageType="hello", use_webpush=1)

    @patch('websockets.connect')
    def test_run_bad_recv(self, m_connect):
        async def go():
            with pytest.raises(PushException):
                await self.client.run(tasks=self.tasks)

        self.mocks['recv'] = Mock(return_value=json.dumps(
            {"messageType": "invalid",
             "status": 200,
             "uaid": "uaidValue",
             "channelID": "chidValue"}
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())

    @patch('websockets.connect')
    def test_bad_close_silent(self, m_connect):
        async def go():
            # Can't call .assert_raises() using an await
            await self.client.cmd_connect()
            await self.client.cmd_close()

        self.mocks['close'] = Mock(
            side_effect=websockets.exceptions.ConnectionClosed(
                code=1000,
                reason="mock"
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())

    @patch('websockets.connect')
    def test_hello_no_conn(self, m_connect):
        async def go():
            # Can't call .assert_raises() using an await
            await self.client.cmd_connect()
            self.mock_connect.state = 1
            await self.client.cmd_hello()

        self.mocks['recv'] = Mock(return_value=json.dumps(
            {"messageType": "hello",
             "status": 200,
             "uaid": "uaidValue",
             "channelID": "chidValue"}
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())
        self.mocks['recv'].assert_called()
        self.mocks['close'].assert_called()
        self.mocks['close_connection'].assert_called()

    @patch('websockets.connect')
    def test_hello_w_uaid(self, m_connect):
        async def go():
            conn = await self.client.cmd_connect()
            self.client.connection = conn
            self.mock_connect.state = 1
            await self.client.cmd_hello(uaid="uaidValue")

        self.mocks['recv'] = Mock(return_value=json.dumps(
            {"messageType": "hello",
             "status": 200,
             "uaid": "uaidValue",
             "channelID": "chidValue"}
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())
        assert self.client.uaid == "uaidValue"

    @patch('websockets.connect')
    def test_hello_w_self_uaid(self, m_connect):
        async def go():
            await self.client.cmd_connect()
            self.mock_connect.state = 1
            self.client.uaid = "uaidValue"
            await self.client.cmd_hello()

        self.mocks['recv'] = Mock(return_value=json.dumps(
            {"messageType": "hello",
             "status": 200,
             "uaid": "uaidValue",
             "channelID": "chidValue"}
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())
        assert self.client.uaid == "uaidValue"

    @patch('websockets.connect')
    def test_hello_w_bad_reply(self, m_connect):
        async def go():
            await self.client.cmd_connect()
            self.mock_connect.state = 1
            self.client.uaid = "uaidValue"
            try:
                await self.client.cmd_hello()
                self.fail("bad test")  # pragma: nocover
            except PushException as ex:
                assert type(ex.__cause__) == KeyError
                assert ex.__cause__.args == ('uaid',)
                pass

        self.mocks['recv'] = Mock(return_value=json.dumps(
            {"messageType": "hello",
             "status": 200,
             "channelID": "chidValue"}
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())

    @patch('websockets.connect')
    def test_cmd_ack(self, m_connect):
        async def go():
            await self.client.cmd_connect()
            self.mock_connect.state = 1
            self.client.uaid = "uaidValue"
            self.client.notifications = [
                dict(channelID='channel1', version='version1')
            ]
            print('sending ack')
            await self.client.cmd_ack()
            await self.client.cmd_close()
            print('x ack')
            self.loop.stop()

        self.mocks['recv'] = Mock(return_value=json.dumps(
            {"messageType": "hello",
             "status": 200,
             "uaid": "uaidValue",
             "channelID": "chidValue"}
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())
        assert len(self.client.notifications) == 0
        assert self.scan_log("Sending ACK")


    @patch('websockets.connect')
    @patch('asyncio.sleep')
    def test_cmd_ack_timeout(self, m_sleep, m_connect):

        async def mock_sleep():
            return asyncio.coroutine(Mock())

        async def go():
            # Can't call .assert_raises() using an await
            await self.client.cmd_connect()
            self.mock_connect.state = 1
            self.client.uaid = "uaidValue"
            self.client.notifications = []
            try:
                while True:
                    await self.client.cmd_ack(timeout=1, sleep=0)
            except PushException as ex:
                assert ex.args[0] == 'Timeout waiting for messages'
                self.loop.stop()

        self.mocks['recv'] = Mock(return_value=json.dumps(
                {"messageType": "hello",
                 "status":200,
                 "uaid": "uaidValue"}
            ))
        m_sleep.return_value = asyncio.ensure_future(
            mock_sleep(),
            loop=self.loop
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop
        )
        self.loop.run_until_complete(go())
        assert len(self.client.notifications) == 0
        assert self.scan_log("No notifications recv'd")

    @patch('websockets.connect')
    def test_cmd_register_key(self, m_connect):
        endpoint = "http://localhost/v1/push/longStringOfCrap"
        chid = "chidValue"

        async def go():
            # Can't call .assert_raises() using an await
            await self.client.cmd_connect()
            self.mock_connect.state = 1
            self.client.uaid = "uaidValue"
            await self.client.cmd_register(key="someKey")

        self.mocks['recv'] = Mock(return_value=json.dumps(
            {"messageType": "register",
             "status": 200,
             "uaid": "uaidValue",
             "channelID": chid,
             "pushEndpoint": endpoint}
            )
        )
        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())
        assert self.client.pushEndpoint == endpoint
        assert self.client.channelID == chid
        assert self.scan_log("Sending new channel registration")

    @patch('websockets.connect')
    def test_rcv_notification(self, m_connect):
        test = "Mary had a little lamb, with a nice mint jelly"
        test_coded = base64.urlsafe_b64encode(test.encode()).strip(b'=')

        async def go():
            await self.client.cmd_connect()
            self.mock_connect.state = 1
            self.client.uaid = "uaidValue"
            await self.client.recv_notification(
                data=test_coded.decode(),
                channelID="chidValue",
                version="versionValue")

        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())
        assert self.scan_log(test)

    @patch('websockets.connect')
    def test_cmd_sleep(self, m_connect):
        async def go():
            await self.client.cmd_connect()
            await self.client.cmd_sleep(0)

        m_connect.return_value = asyncio.ensure_future(
            self.mock_connect(),
            loop=self.loop)
        self.loop.run_until_complete(go())

    """
    # Fails: async with aiohttp.ClientSession() missing __aexit__
    # See http://bugs.python.org/issue26467

    @patch('aiohttp.ClientSession', spec=aiohttp.ClientSession)
    def test_post(self, m_session):
        test = "Mary had a little lamb, with a nice mint jelly"
        test_coded = base64.urlsafe_b64encode(test.encode()).strip(b'=')

        async def go():
            self.client.pushEndpoint = "http://localhost/v1/wpush/LSoC"
            await self.client.cmd_push(
                data=test)

        self.loop.run_until_complete(go())
        ok_(self.scan_log(test))
    """
