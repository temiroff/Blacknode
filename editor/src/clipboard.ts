/** Copy text even when the modern Clipboard API is unavailable or denied. */
export async function copyTextToClipboard(text: string): Promise<void> {
  if (!text) return

  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return
    }
  } catch {
    // Clipboard permissions can reject on non-secure/local browser contexts.
    // Fall through to the selection-based browser copy command.
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '0'
  textarea.style.top = '0'
  textarea.style.width = '1px'
  textarea.style.height = '1px'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)

  try {
    textarea.focus({ preventScroll: true })
    textarea.select()
    textarea.setSelectionRange(0, text.length)
    if (!document.execCommand('copy')) {
      throw new Error('The browser refused the clipboard copy operation.')
    }
  } finally {
    textarea.remove()
  }
}
