/**
 * Save text as a file from the browser.
 *
 * The anchor has to be in the document and the object URL has to outlive the
 * click; revoking it immediately (and never attaching the anchor) is the classic
 * combination that makes Firefox and Safari drop the download.
 */
export function downloadTextFile(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // The download starts asynchronously, so the URL has to survive this tick.
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}
