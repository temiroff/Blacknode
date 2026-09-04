import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LocalFilePicker from './LocalFilePicker'

const { browseFiles } = vi.hoisted(() => ({ browseFiles: vi.fn() }))

vi.mock('../api', () => ({
  api: { browseFiles },
}))

describe('LocalFilePicker', () => {
  beforeEach(() => {
    browseFiles.mockReset()
    browseFiles.mockResolvedValue({
      path: '/models',
      parent: '',
      roots: ['/models'],
      selected: '',
      entries: [{ name: 'robot.usd', path: '/models/robot.usd', is_directory: false, size: 2048 }],
    })
  })

  it('browses with the declared extensions and returns the chosen file', async () => {
    const onSelect = vi.fn()
    render(
      <LocalFilePicker
        title="Choose a robot model"
        initialPath="/models"
        extensions={['.usd']}
        onSelect={onSelect}
        onCancel={vi.fn()}
      />,
    )

    expect(await screen.findByRole('option', { name: /robot\.usd/i })).toBeInTheDocument()
    expect(browseFiles).toHaveBeenCalledWith('/models', ['.usd'])
    fireEvent.doubleClick(screen.getByRole('option', { name: /robot\.usd/i }))
    expect(onSelect).toHaveBeenCalledWith('/models/robot.usd')
  })

  it('renders API errors for the operator', async () => {
    browseFiles.mockRejectedValue(new Error('File type is not granted'))
    render(
      <LocalFilePicker
        title="Choose a robot model"
        initialPath="/models"
        extensions={['.usd']}
        onSelect={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    await waitFor(() => expect(screen.getByText('File type is not granted')).toBeInTheDocument())
  })
})
