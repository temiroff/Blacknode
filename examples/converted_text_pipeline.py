"""Converted from templates/text-pipeline.json with blacknode export-python."""
from __future__ import annotations

import _bootstrap  # noqa: F401

import blacknode as bn


g = bn.Graph()

a = g.node('Text', **{'value': 'Hello'})
_generated_id = a._id
a._id = 'a'
a._params = g._nodes[_generated_id]['params']
g._nodes['a'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('a')

b = g.node('Text', **{'value': ' World'})
_generated_id = b._id
b._id = 'b'
b._params = g._nodes[_generated_id]['params']
g._nodes['b'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('b')

concat = g.node('Concat', **{})
_generated_id = concat._id
concat._id = 'concat'
concat._params = g._nodes[_generated_id]['params']
g._nodes['concat'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('concat')

out = g.node('Output', **{})
_generated_id = out._id
out._id = 'out'
out._params = g._nodes[_generated_id]['params']
g._nodes['out'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('out')

g._edges = [
    {'from': 'a', 'from_port': 'value', 'to': 'concat', 'to_port': 'a'},
    {'from': 'b', 'from_port': 'value', 'to': 'concat', 'to_port': 'b'},
    {'from': 'concat', 'from_port': 'value', 'to': 'out', 'to_port': 'value'},
]

result = g._cook('out', 'value')
print(result)
