"""External integrations that drive a Blacknode workflow from an outside event
source (Slack, etc.). These are runtimes around the graph engine, not graph
nodes — the cook stays synchronous and pull-based; the driver owns the event
loop and runs one cook per incoming message.

Importing this package registers every built-in driver (via import side effect),
so ``blacknode drivers`` can report what is registered and activated.
"""
from . import registry  # noqa: F401
from . import slack_runtime  # noqa: F401  (registers the "slack" driver)
from . import telegram_runtime  # noqa: F401  (registers the "telegram" driver)
