"""Converted from templates/nvidia-nim.json with blacknode export-python."""
from __future__ import annotations

import _bootstrap  # noqa: F401

import blacknode as bn


g = bn.Graph()

model = g.node('Model', **{'value': 'nim:meta/llama-3.1-8b-instruct'})
_generated_id = model._id
model._id = 'model'
model._params = g._nodes[_generated_id]['params']
g._nodes['model'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('model')

system = g.node('Text', **{'value': 'You are a helpful assistant.'})
_generated_id = system._id
system._id = 'system'
system._params = g._nodes[_generated_id]['params']
g._nodes['system'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('system')

prompt = g.node('Text', **{'value': 'Explain quantum computing briefly.'})
_generated_id = prompt._id
prompt._id = 'prompt'
prompt._params = g._nodes[_generated_id]['params']
g._nodes['prompt'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('prompt')

agent = g.node('LLMAgent', **{})
_generated_id = agent._id
agent._id = 'agent'
agent._params = g._nodes[_generated_id]['params']
g._nodes['agent'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('agent')

out = g.node('Output', **{})
_generated_id = out._id
out._id = 'out'
out._params = g._nodes[_generated_id]['params']
g._nodes['out'] = g._nodes.pop(_generated_id)
g._dirty.discard(_generated_id)
g._dirty.add('out')

g._edges = [
    {'from': 'model', 'from_port': 'value', 'to': 'agent', 'to_port': 'model'},
    {'from': 'system', 'from_port': 'value', 'to': 'agent', 'to_port': 'system'},
    {'from': 'prompt', 'from_port': 'value', 'to': 'agent', 'to_port': 'prompt'},
    {'from': 'agent', 'from_port': 'text', 'to': 'out', 'to_port': 'value'},
]

result = g._cook('out', 'value')
print(result)
