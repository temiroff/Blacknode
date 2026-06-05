"""External integrations that drive a Blacknode workflow from an outside event
source (Slack, etc.). These are runtimes around the graph engine, not graph
nodes — the cook stays synchronous and pull-based; the driver owns the event
loop and runs one cook per incoming message."""
