import { useEffect, useState } from 'react'
import Editor from '@monaco-editor/react'
import { API_BASE } from '@api'

export default function TemplateStudio() {
  const [files, setFiles] = useState<string[]>([])
  const [name, setName] = useState<string | null>(null)
  const [content, setContent] = useState('')

  useEffect(() => {
    fetch(`${API_BASE}/templates`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` }
    }).then(r => r.json()).then(setFiles)
  }, [])

  const loadFile = (f: string) => {
    fetch(`${API_BASE}/templates/${f}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` }
    })
      .then(r => r.json())
      .then(d => { setName(f); setContent(d.content) })
  }

  const save = () =>
    fetch(`${API_BASE}/templates/${name}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token') || ''}`
      },
      body: JSON.stringify({ content })
    })

  return (
    <div className="min-h-screen p-4">
      <h1 className="text-3xl font-bold mb-4">Studio</h1>
      <p className="mb-4">LLM-Interaktionsraum / Editor.</p>
      <div className='flex h-full'>
        <aside className='w-56 border-r border-gray-200 bg-gray-100'>
          <h3 className='p-2 font-bold'>Templates</h3>
          {files.map(f => (
            <div key={f}
                 className={'cursor-pointer p-2 ' + (f===name?'bg-gray-200':'')}
                 onClick={() => loadFile(f)}>{f}</div>
          ))}
        </aside>
        <main className='flex-1'>
          {name
            ? <>
                <div className='flex items-center justify-between p-2 bg-gray-100 border-b border-gray-200'>
                  <span className='font-mono'>{name}</span>
                  <button onClick={save}
                          className='bg-green-600 text-white px-3 py-1 rounded'>Save</button>
                </div>
                <Editor height='calc(100vh - 3rem)'
                        defaultLanguage='jinja'
                        value={content}
                        onChange={(v) => setContent(v ?? '')} />
              </>
            : <p className='m-4 text-gray-600'>Select a template…</p>}
        </main>
      </div>
    </div>
  )
}
