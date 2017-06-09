Autopush Smoke Test Application
===============================

This app is designed to exercise the Autopush server.
Tests can be contained as a JSON file.

e.g.

.. code:: json

    [["hello", {}],
     ["register", {}],
     ["push", {"data": "mary had a little lamb"}],
     ["ack", {}],
    ]

The following commands are available:

*hello* - begin session with autopush server.

``args``
 - `uaid` either None if new session or a previous `uaid`

*register* - register a new Channel

``args``
- `channelID` uuid of the channel to create (None if new)

- `key` - VAPID public key base64 string (optional)

*push* - push to an endpoint

``args``

- `pushEndpoint` - the push endpoint (defaults to registered)

- `data` - Data to push

- `headers` - Dictionary of headers to include in push

*ack* - Acknowledge the last received message

``Args``

- `channelID` - ChannelID of the last message (defaults to last recv'd)

- `version` - message version information (defaults to last recv'd)

*done* - Close down connection

``Args``

- None


