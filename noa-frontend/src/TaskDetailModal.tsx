import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from 'react'
import {
  AtSign, CalendarDays, CheckSquare, ChevronDown, Clock3, Download, FileVideo,
  Image as ImageIcon, LoaderCircle, MessageCircle, Paperclip, Plus, Save, Send, Users, X,
} from 'lucide-react'
import { apiError, mediaUrl, workApi } from './api'
import type { Activity, Attachment, Comment, TaskDetail, TaskSection, User } from './types'

type Props = {
  taskId: string
  people: User[]
  onClose: () => void
  onChanged: () => Promise<void> | void
}

const today = () => new Date().toISOString().slice(0, 10)
const formatTime = (value: string) => new Intl.DateTimeFormat('es', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
const formatBytes = (bytes: number) => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`

export function TaskDetailModal({ taskId, people, onClose, onChanged }: Props) {
  const [task, setTask] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [startDate, setStartDate] = useState(today())
  const [dueDate, setDueDate] = useState('')
  const [newSectionTitle, setNewSectionTitle] = useState('')
  const [newSectionNotes, setNewSectionNotes] = useState('')
  const [sectionOpen, setSectionOpen] = useState(false)
  const [checklistDrafts, setChecklistDrafts] = useState<Record<string, string>>({})
  const [commentBody, setCommentBody] = useState('')
  const [mentionedIds, setMentionedIds] = useState<number[]>([])
  const [files, setFiles] = useState<File[]>([])
  const [commenting, setCommenting] = useState(false)
  const [memberUserId, setMemberUserId] = useState('')
  const [memberRole, setMemberRole] = useState<'RESPONSIBLE' | 'COLLABORATOR'>('COLLABORATOR')
  const [activityOpen, setActivityOpen] = useState(false)

  const peopleById = useMemo(() => new Map(people.map((person) => [person.id, person])), [people])
  const participantPeople = useMemo<User[]>(() => {
    const ids = [...new Set(task?.members.map((member) => member.user_id) ?? [])]
    return ids.map((id) => people.find((person) => person.id === id) ?? ({
      id, name: `Usuario #${id}`, email: '', role: '', active: true, departments: [],
    }))
  }, [task?.members, people])
  const mentionQuery = useMemo(() => {
    const before = commentBody.slice(0, commentBody.lastIndexOf('@'))
    const after = commentBody.slice(commentBody.lastIndexOf('@') + 1)
    return commentBody.includes('@') && !/[\s\n]/.test(after) && (before.length === 0 || /[\s\n]$/.test(before)) ? after.toLowerCase() : null
  }, [commentBody])
  const mentionSuggestions = useMemo(() => {
    if (mentionQuery === null) return []
    return participantPeople.filter((person) => person.name.toLowerCase().replace(/\s+/g, '').includes(mentionQuery.replace(/\s+/g, ''))).slice(0, 6)
  }, [mentionQuery, participantPeople])

  async function loadTask() {
    setLoading(true)
    setError('')
    try {
      const { data } = await workApi.get<TaskDetail>(`/tasks/${taskId}`)
      setTask(data)
      setTitle(data.title)
      setDescription(data.description ?? '')
      setStartDate(data.start_date?.slice(0, 10) || today())
      setDueDate(data.due_date?.slice(0, 10) || '')
    } catch (err) {
      setError(apiError(err, 'No se pudo cargar la tarea.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadTask() }, [taskId])
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function saveTask(event?: FormEvent) {
    event?.preventDefault()
    if (!task) return
    setSaving(true); setError(''); setSuccess('')
    try {
      await workApi.patch(`/tasks/${task.id}`, {
        title: title.trim(), description, start_date: startDate,
        due_date: dueDate || null,
      })
      await loadTask()
      await onChanged()
      setSuccess('Cambios guardados')
    } catch (err) { setError(apiError(err, 'No se pudieron guardar los cambios.')) }
    finally { setSaving(false) }
  }

  async function addSection(event: FormEvent) {
    event.preventDefault()
    if (!task || !newSectionTitle.trim()) return
    setSaving(true); setError('')
    try {
      await workApi.post(`/tasks/${task.id}/sections`, { title: newSectionTitle.trim(), notes: newSectionNotes.trim() })
      setNewSectionTitle(''); setNewSectionNotes(''); setSectionOpen(false)
      await loadTask(); await onChanged()
    } catch (err) { setError(apiError(err, 'No se pudo crear la sección.')) }
    finally { setSaving(false) }
  }

  async function saveSection(section: TaskSection, notes: string) {
    if (notes === section.notes) return
    try {
      await workApi.patch(`/sections/${section.id}`, { notes })
      setSuccess(`Apuntes de ${section.title} guardados`)
      await loadTask()
      await onChanged()
    } catch (err) { setError(apiError(err, 'No se pudieron guardar los apuntes.')) }
  }

  async function addChecklist(section: TaskSection, event: FormEvent) {
    event.preventDefault()
    const draft = (checklistDrafts[section.id] ?? '').trim()
    if (!draft) return
    setError('')
    try {
      await workApi.post(`/sections/${section.id}/checklist`, { title: draft, position: section.checklist.length })
      setChecklistDrafts((current) => ({ ...current, [section.id]: '' }))
      await loadTask(); await onChanged()
    } catch (err) { setError(apiError(err, 'No se pudo añadir el elemento.')) }
  }

  async function toggleChecklist(itemId: string, checked: boolean) {
    setError('')
    try { await workApi.patch(`/checklist/${itemId}`, { is_completed: checked }); await loadTask(); await onChanged() }
    catch (err) { setError(apiError(err, 'No se pudo actualizar el checklist.')) }
  }

  async function addMember(event: FormEvent) {
    event.preventDefault()
    if (!task || !memberUserId) return
    setError('')
    try {
      await workApi.post(`/tasks/${task.id}/members`, { user_id: Number(memberUserId), member_role: memberRole })
      setMemberUserId(''); await loadTask(); await onChanged()
    } catch (err) { setError(apiError(err, 'No se pudo asignar el integrante.')) }
  }

  async function removeMember(userId: number) {
    if (!task || !window.confirm('¿Retirar este integrante de la tarea?')) return
    try { await workApi.delete(`/tasks/${task.id}/members/${userId}`); await loadTask(); await onChanged() }
    catch (err) { setError(apiError(err, 'No se pudo retirar el integrante.')) }
  }

  function insertMention(person: User) {
    const at = commentBody.lastIndexOf('@')
    const next = `${commentBody.slice(0, at)}@${person.name} `
    setCommentBody(next)
    setMentionedIds((current) => [...new Set([...current, person.id])])
  }

  function onCommentKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Escape' && mentionQuery !== null) {
      setCommentBody((current) => current.slice(0, current.lastIndexOf('@')))
    }
  }

  async function postComment(event: FormEvent) {
    event.preventDefault()
    if (!task || (!commentBody.trim() && files.length === 0)) return
    if (files.some((file) => file.size > 100 * 1024 * 1024)) {
      setError('Cada archivo debe pesar como máximo 100 MB.')
      return
    }
    setCommenting(true); setError(''); setSuccess('')
    let commentId: string | null = null
    try {
      const validMentions = mentionedIds.filter((id) => {
        const person = participantPeople.find((candidate) => candidate.id === id)
        return person ? commentBody.includes(`@${person.name}`) : false
      })
      const body = commentBody.trim() || 'Adjuntó archivos.'
      const { data: comment } = await workApi.post<Comment>(`/tasks/${task.id}/comments`, { body, mentioned_user_ids: validMentions })
      commentId = comment.id
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        await workApi.post(`/comments/${commentId}/attachments`, form, { timeout: 120000 })
      }
      setCommentBody(''); setMentionedIds([]); setFiles([])
      const input = document.getElementById('comment-files') as HTMLInputElement | null
      if (input) input.value = ''
      await loadTask(); await onChanged()
      setSuccess(files.length ? 'Comentario y archivos publicados' : 'Comentario publicado')
    } catch (err) {
      if (commentId) {
        await loadTask()
        setError(`El comentario quedó guardado, pero algún archivo pudo fallar: ${apiError(err)}`)
      } else setError(apiError(err, 'No se pudo publicar el comentario.'))
    } finally { setCommenting(false) }
  }

  if (loading && !task) return <div className="modal-backdrop" onMouseDown={onClose}><div className="task-modal loading-modal" onMouseDown={(e) => e.stopPropagation()}><LoaderCircle className="spin" size={26}/> Cargando tarea…</div></div>

  return (
    <div className="modal-backdrop" onMouseDown={onClose} role="presentation">
      <section className="task-modal" role="dialog" aria-modal="true" aria-label="Detalle de tarea" onMouseDown={(event) => event.stopPropagation()}>
        <header className="task-modal__header">
          <div className="task-modal__crumb"><span>Bot empresarial</span><span>/</span><span>Tarea</span></div>
          <button className="icon-button" onClick={onClose} aria-label="Cerrar tarea"><X size={20}/></button>
        </header>
        {error && <div className="notice notice--error task-notice">{error}</div>}
        {success && <div className="notice notice--success task-notice">{success}</div>}
        {!task ? <div className="empty-state">No se pudo cargar esta tarea.</div> : (
          <div className="task-modal__grid">
            <main className="task-content">
              <form onSubmit={saveTask} className="task-title-form">
                <input className="task-title-input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={240} aria-label="Título de la tarea" required/>
                <div className="task-meta-grid">
                  <label className="field"><span><CalendarDays size={14}/> Fecha de inicio</span><input className="input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required/></label>
                  <label className="field"><span><CalendarDays size={14}/> Fecha final <em>Opcional</em></span><input className="input" type="date" value={dueDate} min={startDate} onChange={(e) => setDueDate(e.target.value)}/></label>
                </div>
                <label className="field task-description-field"><span>Apuntes generales</span><textarea className="input textarea" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Contexto, objetivo o notas generales de la tarea…" maxLength={20000}/></label>
                <div className="task-save-row"><span className="muted-small">Los cambios se guardan en el servidor.</span><button className="button button--primary button--small" type="submit" disabled={saving}><Save size={15}/>{saving ? 'Guardando…' : 'Guardar cambios'}</button></div>
              </form>

              <section className="task-section-block">
                <div className="section-heading"><div><h3>Apuntes y checklist</h3><p>Divide el trabajo por áreas: Frontend, Backend, QA…</p></div><button className="button button--secondary button--small" onClick={() => setSectionOpen((open) => !open)}><Plus size={15}/> Añadir sección</button></div>
                {sectionOpen && <form className="new-section-form" onSubmit={addSection}><input className="input" placeholder="Nombre de la sección (ej. Backend)" value={newSectionTitle} onChange={(e) => setNewSectionTitle(e.target.value)} required maxLength={120}/><textarea className="input textarea" placeholder="Apuntes de esta sección" value={newSectionNotes} onChange={(e) => setNewSectionNotes(e.target.value)} rows={2}/><div className="form-actions"><button className="button button--secondary button--small" type="button" onClick={() => setSectionOpen(false)}>Cancelar</button><button className="button button--primary button--small" disabled={saving}>Crear sección</button></div></form>}
                {task.sections.length === 0 && !sectionOpen && <div className="inline-empty"><CheckSquare size={20}/><strong>Aún no hay secciones</strong><span>Crea Frontend, Backend o cualquier área de trabajo que necesites.</span><button className="text-button" onClick={() => setSectionOpen(true)}>Añadir la primera sección</button></div>}
                <div className="sections-list">
                  {task.sections.map((section) => {
                    const completed = section.checklist.filter((item) => item.is_completed).length
                    const total = section.checklist.length
                    return <article className="work-section" key={section.id}>
                      <div className="work-section__heading"><div className="work-section__icon"><CheckSquare size={18}/></div><div className="work-section__title"><h4>{section.title}</h4><span>{total ? `${completed} de ${total} completados` : 'Sin elementos en checklist'}</span></div>{total > 0 && <div className="mini-progress"><span style={{ width: `${completed / total * 100}%` }}/></div>}</div>
                      <textarea className="section-notes" key={`${section.id}-${section.updated_at ?? ''}`} defaultValue={section.notes} rows={Math.min(5, Math.max(2, section.notes.split('\n').length))} placeholder="Apuntes técnicos de esta sección…" onBlur={(e) => void saveSection(section, e.target.value)} aria-label={`Apuntes ${section.title}`}/>
                      <div className="checklist-list">
                        {section.checklist.map((item) => <label className={`checklist-row ${item.is_completed ? 'checklist-row--done' : ''}`} key={item.id}><input type="checkbox" checked={item.is_completed} onChange={(e) => void toggleChecklist(item.id, e.target.checked)}/><span>{item.title}</span></label>)}
                      </div>
                      <form className="checklist-add" onSubmit={(event) => void addChecklist(section, event)}><input value={checklistDrafts[section.id] ?? ''} onChange={(e) => setChecklistDrafts((current) => ({ ...current, [section.id]: e.target.value }))} className="input" placeholder="Añadir elemento al checklist…" maxLength={500}/><button className="icon-button" type="submit" aria-label="Añadir elemento"><Plus size={18}/></button></form>
                    </article>
                  })}
                </div>
              </section>

              <section className="task-section-block members-block">
                <div className="section-heading"><div><h3><Users size={17}/> Integrantes</h3><p>Personas asignadas a esta tarea.</p></div></div>
                <div className="member-list">
                  {task.members.map((member) => {
                    const person = peopleById.get(member.user_id)
                    return <div className="member-chip" key={member.user_id}><span className="avatar avatar--small">{(person?.name ?? `U${member.user_id}`).slice(0, 1).toUpperCase()}</span><span className="member-chip__copy"><strong>{person?.name ?? `Usuario #${member.user_id}`}</strong><small>{member.role === 'RESPONSIBLE' ? 'Responsable' : 'Colaborador'}</small></span>{member.role !== 'RESPONSIBLE' && <button className="icon-button icon-button--tiny" title="Retirar integrante" onClick={() => void removeMember(member.user_id)}><X size={14}/></button>}</div>
                  })}
                </div>
                <form className="member-add" onSubmit={addMember}><select className="input" value={memberUserId} onChange={(e) => setMemberUserId(e.target.value)}><option value="">Seleccionar persona…</option>{people.filter((person) => !task.members.some((member) => member.user_id === person.id)).map((person) => <option value={person.id} key={person.id}>{person.name} · {person.role_name ?? person.role}</option>)}</select><select className="input member-role-select" value={memberRole} onChange={(e) => setMemberRole(e.target.value as 'RESPONSIBLE' | 'COLLABORATOR')}><option value="COLLABORATOR">Colaborador</option><option value="RESPONSIBLE">Responsable</option></select><button className="button button--secondary button--small" disabled={!memberUserId}><Plus size={14}/> Añadir</button></form>
                {people.length <= 1 && <p className="muted-small member-hint">La API de Identidad solo permite mostrar los usuarios autorizados para tu rol. Si faltan compañeros, revisa los permisos de consulta del departamento.</p>}
              </section>

              <section className="activity-block">
                <button className="activity-toggle" onClick={() => setActivityOpen((open) => !open)}><Clock3 size={16}/><span>Actividad de la tarea</span><span className="activity-count">{task.activity.length}</span><ChevronDown size={16} className={activityOpen ? 'rotate' : ''}/></button>
                {activityOpen && <div className="activity-list">{task.activity.length ? task.activity.map((event: Activity) => <div className="activity-row" key={event.id}><span className="activity-dot"/><div><p><strong>{peopleById.get(event.actor_user_id)?.name ?? `Usuario #${event.actor_user_id}`}</strong> {event.summary.toLowerCase()}</p><time>{formatTime(event.created_at)}</time></div></div>) : <p className="muted-small">Todavía no hay actividad registrada.</p>}</div>}
              </section>
            </main>

            <aside className="comments-panel">
              <div className="comments-panel__header"><div><h3><MessageCircle size={18}/> Comentarios</h3><p>Conversación de esta tarea</p></div><span className="comment-count">{task.comments.length}</span></div>
              <div className="comments-feed">
                {task.comments.length === 0 && <div className="comments-empty"><MessageCircle size={24}/><strong>Empieza la conversación</strong><span>Comparte avances, dudas o menciona a un compañero.</span></div>}
                {task.comments.map((comment: Comment) => <article className="comment-item" key={comment.id}>
                  <div className="comment-item__meta"><span className="avatar avatar--small">{(peopleById.get(comment.author_user_id)?.name ?? `U${comment.author_user_id}`).slice(0, 1).toUpperCase()}</span><div><strong>{peopleById.get(comment.author_user_id)?.name ?? `Usuario #${comment.author_user_id}`}</strong><time>{formatTime(comment.created_at)}</time></div></div>
                  <p className="comment-item__body">{comment.body}</p>
                  {comment.mentions.length > 0 && <div className="mention-tags">{comment.mentions.map((id) => <span key={id}><AtSign size={12}/>{peopleById.get(id)?.name ?? `Usuario #${id}`}</span>)}</div>}
                  {comment.attachments.length > 0 && <div className="attachment-grid">{comment.attachments.map((attachment: Attachment) => <AttachmentPreview key={attachment.id} attachment={attachment}/>)}</div>}
                </article>)}
              </div>
              <form className="comment-composer" onSubmit={postComment}>
                <div className="composer-label"><span>Escribir comentario</span><span><AtSign size={13}/> Menciona con @</span></div>
                <div className="composer-input-wrap"><textarea value={commentBody} onChange={(e) => setCommentBody(e.target.value)} onKeyDown={onCommentKeyDown} rows={3} placeholder="Escribe un comentario… usa @ para mencionar" maxLength={10000} aria-label="Comentario"/>
                  {mentionQuery !== null && mentionSuggestions.length > 0 && <div className="mention-menu">{mentionSuggestions.map((person) => <button type="button" key={person.id} onClick={() => insertMention(person)}><span className="avatar avatar--small">{person.name.slice(0, 1).toUpperCase()}</span><span><strong>{person.name}</strong>{person.email && <small>{person.email}</small>}</span></button>)}</div>}
                </div>
                {files.length > 0 && <div className="pending-files">{files.map((file, index) => <span key={`${file.name}-${index}`}>{file.type.startsWith('video/') ? <FileVideo size={13}/> : <ImageIcon size={13}/>} {file.name}<button type="button" onClick={() => setFiles((current) => current.filter((_, i) => i !== index))} aria-label={`Quitar ${file.name}`}><X size={12}/></button></span>)}</div>}
                <div className="composer-actions"><label className="icon-button attach-button" title="Adjuntar imagen o video"><Paperclip size={17}/><input id="comment-files" type="file" accept="image/png,image/jpeg,image/gif,image/webp,video/mp4,video/quicktime,video/webm" multiple hidden onChange={(e) => { const selected = Array.from(e.target.files ?? []); setFiles((current) => [...current, ...selected].slice(0, 8)) }}/></label><span className="muted-small">Imágenes y videos · hasta 100 MB por archivo</span><button className="button button--primary button--small" disabled={commenting || (!commentBody.trim() && files.length === 0)}><Send size={14}/>{commenting ? 'Enviando…' : 'Enviar'}</button></div>
              </form>
            </aside>
          </div>
        )}
      </section>
    </div>
  )
}

function AttachmentPreview({ attachment }: { attachment: Attachment }) {
  const src = mediaUrl(attachment.preview_url)
  const isVideo = attachment.media_type.startsWith('video/')
  return <div className="attachment-card">
    {isVideo ? <video src={src} controls preload="metadata" /> : <a href={src} target="_blank" rel="noreferrer" className="attachment-image-link"><img src={src} loading="lazy" alt={attachment.original_filename}/></a>}
    <div className="attachment-card__footer"><span title={attachment.original_filename}>{isVideo ? <FileVideo size={13}/> : <ImageIcon size={13}/>}<span>{attachment.original_filename}</span></span><small>{formatBytes(attachment.size_bytes)}</small><a className="icon-button icon-button--tiny" href={mediaUrl(attachment.download_url)} title="Descargar archivo"><Download size={14}/></a></div>
  </div>
}
