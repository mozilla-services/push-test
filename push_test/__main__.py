import asyncio
import json
import logging

import websockets
import configargparse

from push_test.pushclient import PushClient


logger = logging.getLogger(__name__)


def config():
    parser = configargparse.ArgumentParser(
        usage="Smoke Test program for autopush",
        default_config_files=["push-test.ini"],
        add_help=True,
    )
    parser.add_argument("-c",
                        "--config",
                        is_config_file=True,
                        help="Config file path")
    parser.add_argument("-t",
                        "--task_file",
                        type=str,
                        help="path to file of JSON commands",
                        default="tasks.json",
                        env_var="TASK_FILE",
                        )
    parser.add_argument("-s",
                        "--server",
                        type=str,
                        help="URL to websocket server",
                        default="wss://push.services.mozilla.com",
                        env_var="SERVER",
                        )
    parser.add_argument("--debug",
                        help="Enable async debug mode",
                        action="store_true",
                        env_var="DEBUG",
                        default=None)
    parser.add_argument("--key",
                        type=str,
                        dest="vapid_key",
                        help="VAPID private key file",
                        env_var="VAPID_KEY")
    parser.add_argument("-e",
                        "--endpoint",
                        type=str,
                        dest="partner_endpoint",
                        help="Partner endpoint override",
                        env_var="ENDPOINT",
                        default=None)
    parser.add_argument("--endpoint_ssl_cert",
                        type=str,
                        dest="partner_endpoint_cert",
                        help="Partner endpoint certificate",
                        env_var="ENDPOINT_SSL_CERT",
                        default=None)
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
