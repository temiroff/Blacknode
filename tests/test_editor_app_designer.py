from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'editor-server'))
import server


class AppDesignerTests(unittest.TestCase):
    def setUp(self):
        self.session = server.Session()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enterContext(patch.object(server, '_session', self.session))
        self.enterContext(patch.object(server, '_save', lambda *args, **kwargs: None))
        self.enterContext(patch.object(server, '_WORKFLOWS_DIR', self.temp.name))
        self.client = TestClient(server.app)
        workflow = json.loads((ROOT / 'templates' / 'text-pipeline.json').read_text())
        response = self.client.post('/graph', json={
            'nodes': list(workflow['node_meta'].values()), 'edges': workflow['edges'],
            'metadata': {'project_id': 'my-project'}, 'entrypoint': workflow['entrypoint'],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.view = {
            'schema_version': 1, 'id': 'my-app', 'title': 'My App',
            'sections': [{'id': 'main', 'widgets': [
                {'id': 'text', 'type': 'fields', 'items': [{'node_id': 'a', 'param': 'value', 'label': 'Message', 'input': 'text'}]},
                {'id': 'result', 'type': 'metrics', 'items': [{'node_id': 'out', 'port': 'value', 'label': 'Result', 'format': 'text'}]},
                {'id': 'run', 'type': 'actions', 'items': [{'id': 'run', 'label': 'Run', 'cook_target': {'node_id': 'out', 'port': 'value', 'mode': 'once'}}]},
            ]}],
        }

    def test_design_preserves_graph_state_and_saves_with_workflow(self):
        graph = self.session.graph
        graph._cache[('a', 'value')] = 'cached'
        response = self.client.patch('/graph/operator-view', json=self.view)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIs(self.session.graph, graph)
        self.assertEqual(graph._cache[('a', 'value')], 'cached')
        self.assertEqual(response.json()['metadata']['project_id'], 'my-project')
        self.assertEqual(response.json()['metadata']['operator_view'], self.view)
        saved = self.client.post('/workflows', json={'name': 'My App'})
        self.assertEqual(saved.status_code, 200, saved.text)
        payload = json.loads(next(Path(self.temp.name).glob('*.json')).read_text())
        self.assertEqual(payload['metadata']['operator_view'], self.view)

    def test_invalid_reference_does_not_replace_previous_app(self):
        self.session.metadata['operator_view'] = copy.deepcopy(self.view)
        for key, bad_value in [('node_id', 'deleted'), ('param', 'invented')]:
            view = copy.deepcopy(self.view)
            view['sections'][0]['widgets'][0]['items'][0][key] = bad_value
            result = self.client.patch('/graph/operator-view', json=view)
            self.assertEqual(result.status_code, 400, result.text)
            self.assertEqual(self.session.metadata['operator_view'], self.view)
        view = copy.deepcopy(self.view)
        view['sections'][0]['widgets'][1]['items'][0]['port'] = 'invented'
        self.assertEqual(self.client.patch('/graph/operator-view', json=view).status_code, 400)

    def test_customer_app_cannot_change_its_operator_permissions(self):
        with patch.object(server, '_APP_DEPLOYMENT', {'apps': []}):
            response = self.client.patch('/graph/operator-view', json=self.view)
        self.assertEqual(response.status_code, 403)
