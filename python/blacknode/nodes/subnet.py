from blacknode.node import node


@node(inputs=[], outputs=[], name="SubnetInput")
def subnet_input(ctx: dict) -> dict:
    # Values are injected directly into the cache by _cook_subnet; this is
    # only called if somehow reached through the normal cook path.
    return dict(ctx)


@node(inputs=[], outputs=[], name="SubnetOutput")
def subnet_output(ctx: dict) -> dict:
    # ctx is populated by edge resolution; return every input as an output
    # so the caller can read any port by name.
    return dict(ctx)
