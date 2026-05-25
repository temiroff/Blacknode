# ParseRSS Learned Node Example

This is a reference learned-node directory. To install it manually for local
testing, copy this folder to `nodes/learned/ParseRSS/` and restart Blacknode or
call `blacknode.learned.registry.register_one("ParseRSS")` from Python.

The node parses RSS XML text and returns a list of entries. It does not require
network access.
