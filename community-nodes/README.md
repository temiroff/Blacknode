# Community Nodes

This folder is the marketplace MVP. Community node packs are ordinary Python
files reviewed through GitHub pull requests.

Submission rules:

- Put reusable nodes in `community-nodes/*.py`.
- Use Blacknode's `@node` decorator with `name`, `category`, typed `inputs`,
  and typed `outputs`.
- Use the Python standard library unless a dependency is already part of the
  project.
- Include deterministic behavior and avoid network calls at import time.
- Add tests when the node has parsing, ranking, database, or API behavior.

Blacknode auto-loads this folder on startup. A user can also reload node files
from the editor Script tab.
