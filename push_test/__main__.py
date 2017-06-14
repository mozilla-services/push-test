import asyncio
import json
import logging

import websockets
import argparse

from push_test.pushclient import PushClient


logger = logging.getLogger(__name__)


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
                        type=int,
                        help="Enable async debug mode",
                        default=None)
    parser.add_argument("--key",
                        type=str,
                        help="VAPID private key file")
    return parser.parse_args()


def get_tasks(task_file):
    with open(task_file) as file:
        tasks = json.loads(file.read())
        return tasks


def main():
    """
    "tasks" is a JSON list of lists, where the first item is the command and
    the second are the arguments.

    For instance
    ```
    [["hello", {}],
     ["register", {}],
     ["push", {data="mary had a little lamb"}],
     ["sleep", {"period": 0.2}],
     ["ack", {}]
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
    args = config()
    loop = asyncio.get_event_loop()
    if args.debug:
        loop.set_debug(True)
        logging.basicConfig(level='DEBUG')
    tasks = get_tasks(args.task_file)

    client = PushClient(args, loop, tasks)

    try:
        loop.run_until_complete(client.run())
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as ex:
        logger.error("Unknown Exception", ex)
    finally:
        loop.close()


if __name__ == "__main__":
    main()
