import { expect, test } from '@playwright/test'

const operatorView = {
  schema_version: 1,
  id: 'robot-viewer',
  title: 'Robot viewer',
  settings: {
    groups: [{
      id: 'scene',
      title: 'Scene',
      items: [{
        node_id: 'viewer',
        param: 'model_path',
        label: 'Robot model',
        input: 'file_path',
        extensions: ['.usd'],
      }],
    }],
  },
  sections: [{
    id: 'main',
    widgets: [{
      type: 'status',
      id: 'status',
      items: [{ label: 'Viewer', node_id: 'viewer', port: 'ready' }],
    }],
  }],
}

const graph = {
  nodes: [{
    id: 'viewer',
    type: 'NewtonScene',
    params: { model_path: '' },
    pos: [0, 0],
    inputs: ['model_path'],
    outputs: ['ready'],
    input_types: { model_path: 'Text' },
    output_types: { ready: 'Bool' },
    input_defaults: { model_path: '' },
  }],
  edges: [],
  metadata: { operator_view: operatorView },
  entrypoint: { node_id: 'viewer', port: 'ready' },
}

test('packaged App opens its granted file picker', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/app-deployment') {
      await route.fulfill({ json: {
        kind: 'blacknode.app-deployment',
        schema_version: 1,
        id: 'demo',
        name: 'Demo',
        start_app: 'robot-viewer',
        access: { role: 'operator', graph_editing: false },
        required_packages: [],
        required_components: [],
        required_adapters: [],
        apps: [{
          id: 'robot-viewer', name: 'Robot viewer', description: '', accent: '#76b900', icon: 'robot',
          required_packages: [], required_components: [], required_adapters: [],
        }],
      } })
    } else if (pathname.endsWith('/activate')) {
      await route.fulfill({ json: { app: { id: 'robot-viewer' }, graph } })
    } else if (pathname === '/api/graph') {
      await route.fulfill({ json: graph })
    } else if (pathname === '/api/filesystem/browse') {
      expect(route.request().postDataJSON()).toEqual({ path: '', extensions: ['.usd'] })
      await route.fulfill({ json: {
        path: '/models', parent: '', roots: ['/models'], selected: '',
        entries: [{ name: 'robot.usd', path: '/models/robot.usd', is_directory: false, size: 4096 }],
      } })
    } else {
      await route.fulfill({ json: { modules: {} } })
    }
  })

  await page.goto('/app/robot-viewer')
  await expect(page.getByRole('heading', { name: 'Robot viewer' })).toBeVisible()
  await page.getByRole('button', { name: 'App settings' }).click()
  await page.getByRole('button', { name: 'Browse…' }).click()
  await expect(page.getByRole('dialog', { name: 'Choose Robot model' })).toBeVisible()
  await expect(page.getByRole('option', { name: /robot\.usd/i })).toBeVisible()
})
