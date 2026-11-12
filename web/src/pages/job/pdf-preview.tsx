// react-pdf pulls in pdf.js (large), so the CV panel loads this file lazily. Default export for React.lazy.
import { useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { Skeleton } from '@/components/ui/skeleton'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

export default function PdfPreview({ url }: { url: string }) {
  const [pages, setPages] = useState(0)
  const [width, setWidth] = useState(600)
  return (
    <div
      className="grid gap-3 overflow-auto rounded-lg border bg-muted/30 p-2"
      ref={(el) => {
        if (el && Math.abs(el.clientWidth - 16 - width) > 24 && el.clientWidth > 100) setWidth(el.clientWidth - 16)
      }}
    >
      <Document
        file={url}
        onLoadSuccess={(d) => setPages(d.numPages)}
        loading={<Skeleton className="h-96" />}
        error={<p role="alert" className="p-4 text-sm text-destructive">Could not render the PDF. Use "Open PDF" instead.</p>}
      >
        {Array.from({ length: pages }, (_, i) => (
          <Page key={i} pageNumber={i + 1} width={width} renderAnnotationLayer={false} renderTextLayer={false} />
        ))}
      </Document>
    </div>
  )
}
