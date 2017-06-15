import asyncio
import base64
import io
import json
import os
import unittest
import tempfile
import uuid

import pytest
import websockets
from py_vapid import Vapid
from mock import Mock, patch

from push_test.pushclient import PushClient, PushException


class TrialSettings(object):
    """Empty setting arguments class, for use by testing and integration"""
    def __init__(self):
        self.server = "localhost"
        self.key = None
        self.debug = False
        self.endpoint = None
        self.endpoint_ssl_cert = None
        self.vapid_key = None
        self.partner_endpoint = None
        self.partner_endpoint_cert = None


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

    def test_init(self):
        args = TrialSettings()
        args.vapid_key = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex)
        vapid = Vapid()
        vapid.generate_keys()
        vapid.save_key(args.vapid_key)
        client = PushClient(loop=self.loop, args=args)
        assert (client.vapid.public_key.public_numbers().encode_point ==
                vapid.public_key.public_numbers().encode_point)
        os.unlink(args.vapid_key)

    @patch('ssl.create_default_context')
    @patch('aiohttp.TCPConnector')
    def test_init_cert(self, m_connector, m_ssl):
        # as data:
        args = TrialSettings()
        args.partner_endpoint_cert = os.path.join(
            tempfile.gettempdir(), uuid.uuid4().hex)
        PushClient(loop=self.loop, args=args)
        assert m_ssl.call_args[1]['cadata'] == args.partner_endpoint_cert
        assert m_connector.call_args[1]['ssl_context'].check_hostname is False
        with open(args.partner_endpoint_cert, "wb"):
            pass
        m_connector.reset_mock()
        m_ssl.reset_mock()
        # as file:
        with open(args.partner_endpoint_cert) as file:
            file.close()
        PushClient(loop=self.loop, args=args)
        assert m_ssl.call_args[1]['cafile'] == args.partner_endpoint_cert
        assert m_connector.call_args[1]['ssl_context'].check_hostname is False
        os.unlink(args.partner_endpoint_cert)

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
                 "status": 200,
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
    def test_cmd_register_c_endpoint(self, m_connect):
        endpoint = "http://localhost/v1/push/longStringOfCrap"
        chid = "chidValue"
        args = TrialSettings()
        args.partner_endpoint = "http://example.com"
        self.client = PushClient(loop=self.loop, args=args)
        self.client.output = self.output

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
        assert (self.client.pushEndpoint ==
                "http://example.com/v1/push/longStringOfCrap")

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

    def test_cache_sign(self):
        claims = {
            "sub": "mailto:a@b.c",
            "aud": "http://a.b",
            "foo": "bar.bell"
        }
        test1 = self.client._cache_sign(claims)
        # signing will alter the claims and add an expiration.
        del(claims['exp'])
        self.client._cache_sign({
            "sub": "mailto:h@i.jo",
            "aud": "http://a.b"
        })
        test3 = self.client._cache_sign(claims)
        assert test1 == test3

    def test_next_task(self):
        async def go():
            try:
                await self.client._next_task()
                assert False, "Invalid command accepted"  # pragma nocover
            except PushException:
                pass

        self.client.tasks = [("invalid", {})]
        self.loop.run_until_complete(go())

    def test_closed_recv(self):
        async def go():
            await self.client.receiver()

        async def abort():
            raise websockets.exceptions.ConnectionClosed(code=0, reason="test")

        self.client.connection = Mock()
        self.client.connection.recv = abort

        self.client.tasks = [("invalid", {})]
        self.loop.run_until_complete(go())
        assert self.scan_log("Websocket Connection closed")

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
