RUNNER_TEMPLATE = '''
import json
import sys
import traceback
from pathlib import Path

workspace = Path("/workspace")

try:
    inputs = json.loads((workspace / "input.json").read_text())

    # Import the user's node module
    sys.path.insert(0, str(workspace))
    import node as user_node

    # Find the run() function
    if not hasattr(user_node, "run"):
        raise RuntimeError("Generated node must define a `run` function")

    result = user_node.run(**inputs)

    # Result must be a dict matching declared outputs
    if not isinstance(result, dict):
        raise RuntimeError(f"`run` must return a dict, got {type(result).__name__}")

    (workspace / "output.json").write_text(json.dumps(result))

except Exception as e:
    error_output = {
        "__error__": True,
        "type": type(e).__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
    }
    (workspace / "output.json").write_text(json.dumps(error_output))
    sys.exit(1)
'''
