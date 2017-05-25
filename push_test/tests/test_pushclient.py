import asyncio
import unittest

from push_test.pushclient import PushClient, PushException


class Test_PushClient:

    def setup(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.client = PushClient(loop=self.loop)
        self.tasks = [('done', {})]

    def test_run(self):
        self.client.tasks
