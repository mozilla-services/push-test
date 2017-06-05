import asyncio
import json
import sys

import websockets
import argparse

from push_test.pushclient import PushClient, output

"""
from push_test.__main__ import PushClient, __main__;
"""

def config():
    parser = argparse.ArgumentParser(
        usage="Smoke Test program for autopush",
        add_help=True,
    )
    parser.add_argument("--task_file",
                        type=str,
                        help="path to file of JSON commands",
                        default="tasks.json"
                        )
    parser.add_argument("--server",
                        type=str,
                        help="URL to websocket server",
                        default="wss://push.services.mozilla.com")
    parser.add_argument("--debug",
                        type=bool,
                        help="Enable async debug mode",
                        default=False)
    return parser.parse_args()


def get_tasks(task_file):
    with open(task_file) as file:
        tasks = json.loads(file.read())
        return tasks

def main():
    args = config()
    tasks = get_tasks(args.task_file)
    """
    "tasks" is a JSON list of lists, where the first item is the command and
    the second are the arguments.

    For instance
    ```
    [["hello", {}],
     ["register", {}],
     ["push", {data="mary had a little lamb"}],
     ["ack", {}],
    ]
    ```
    First executes a websocket `hello`.
    Then `register`s for an endpoint (the endpoint is stored as a default).
    Then `push`s via HTTPS to the endpoint the a notification with the body of
        `data`.
    Then `ack`s the response.
    And calls `done` to clean up.
    A "done" will be appended if not present.

    """
    loop = asyncio.get_event_loop()
    loop.set_debug(args.debug)

    client = PushClient(args, loop)
    client.tasks = tasks

    try:
        loop.run_until_complete(client.run())
    except websockets.ConnectionClosed:
        pass
    except Exception as ex:
        print("Unknown Exception: {}".format(ex))
    finally:
        loop.close()
