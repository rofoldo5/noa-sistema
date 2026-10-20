import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  ArrowRight, Bell, CalendarDays, CheckSquare, ChevronDown, CircleHelp, Clock3,
  FolderKanban, LayoutDashboard, ListTodo, LoaderCircle, LogOut, Menu, Plus, Search,
  ShieldCheck, MessageCircle, Users, X,
} from 'lucide-react'
import { apiError, identityApi, TOKEN_KEY, workApi } from './api'
import { TaskDetailModal } from './TaskDetailModal'
import type { Board, Column, Department, Project, TaskCard, User } from './types'

const today = () => new Date().toISOString().slice(0, 10)
const roleLabels: Record<string, string> = { SUPERADMIN: 'SuperAdmin', JEFE: 'Jefe', EMPLEADO: 'Empleado' }
const roleLabel = (role: string) => roleLabels[role] ?? role
const initials = (name: string) => name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
const dateLabel = (date?: string | null) => date ? new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short' }).format(new Date(`${date.slice(0, 10)}T12:00:00`)) : null

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [workspaceLoading, setWorkspaceLoading] = useState(false)
  const [projects, setProjects] = useState<Project[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [people, setPeople] = useState<User[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [board, setBoard] = useState<Board | null>(null)
  const [columns, setColumns] = useState<Column[]>([])
  const [tasks, setTasks] = useState<TaskCard[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [page, setPage] = useState<'board' | 'projects'>('board')
  const [query, setQuery] = useState('')
  const [appError, setAppError] = useState('')
  const [notice, setNotice] = useState('')
  const [projectModalOpen, setProjectModalOpen] = useState(false)
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [quickColumnId, setQuickColumnId] = useState('')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)

  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null); setProjects([]); setDepartments([]); setPeople([]); setBoard(null); setColumns([]); setTasks([])
    setSelectedProjectId(''); setSelectedTaskId(null); setAppError('')
  }, [])

  const loadBoard = useCallback(async (projectId: string) => {
    if (!projectId) { setSelectedProjectId(''); setBoard(null); setColumns([]); setTasks([]); return }
    setAppError('')
    setSelectedProjectId(projectId)
    setBoard(null); setColumns([]); setTasks([])
    try {
      const { data: boards } = await workApi.get<Board[]>(`/projects/${projectId}/boards`)
      let activeBoard = boards[0]
      if (!activeBoard) {
        const { data } = await workApi.post<Board>(`/projects/${projectId}/boards`, { name: 'Tablero principal' })
        activeBoard = data
      }
      const cols = activeBoard.columns?.length ? activeBoard.columns : (await workApi.get<Column[]>(`/boards/${activeBoard.id}/columns`)).data
      setBoard(activeBoard); setColumns(cols)
      const { data: taskList } = await workApi.get<TaskCard[]>(`/boards/${activeBoard.id}/tasks`, { params: { limit: 200 } })
      setTasks(taskList)
    } catch (error) {
      setAppError(apiError(error, 'No se pudo cargar el tablero.'))
    }
  }, [])

  const loadWorkspace = useCallback(async (activeUser: User) => {
    setWorkspaceLoading(true); setAppError('')
    try {
      const [departmentResult, peopleResult, projectResult] = await Promise.allSettled([
        identityApi.get<Department[]>('/departments'),
        identityApi.get<User[]>('/users', { params: { limit: 100 } }),
        workApi.get<Project[]>('/projects', { params: { limit: 100 } }),
      ])
      if (departmentResult.status === 'fulfilled') setDepartments(departmentResult.value.data)
      else setAppError(apiError(departmentResult.reason, 'No se pudieron consultar los departamentos.'))
      if (peopleResult.status === 'fulfilled') {
        const list = peopleResult.value.data
        setPeople(list.some((person) => person.id === activeUser.id) ? list : [activeUser, ...list])
      } else setPeople([activeUser])
      if (projectResult.status === 'fulfilled') {
        const list = projectResult.value.data
        setProjects(list)
        if (list.length) {
          await loadBoard(list[0].id)
        } else {
          setSelectedProjectId(''); setBoard(null); setColumns([]); setTasks([])
        }
      } else {
        setProjects([])
        setAppError((current) => current || apiError(projectResult.reason, 'No se pudieron consultar los proyectos.'))
      }
    } finally { setWorkspaceLoading(false) }
  }, [loadBoard])

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) { setAuthLoading(false); return }
    identityApi.get<User>('/auth/me')
      .then(({ data }) => { setUser(data); void loadWorkspace(data) })
      .catch(() => clearSession())
      .finally(() => setAuthLoading(false))
  }, [clearSession, loadWorkspace])

  useEffect(() => {
    const unauthorized = () => clearSession()
    window.addEventListener('noa:unauthorized', unauthorized)
    return () => window.removeEventListener('noa:unauthorized', unauthorized)
  }, [clearSession])

  async function login(email: string, password: string) {
    const { data } = await identityApi.post<{ access_token: string; token_type: string; user: User }>('/auth/login', { email: email.trim().toLowerCase(), password })
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setUser(data.user)
    await loadWorkspace(data.user)
  }

  async function logout() {
    try { await identityApi.post('/auth/logout') } catch { /* borrar token local aunque la API no responda */ }
    clearSession()
  }

  async function createProject(data: { name: string; description: string; department_id: number }) {
    setAppError(''); setNotice('')
    try {
      const { data: created } = await workApi.post<Project>('/projects', data)
      const { data: list } = await workApi.get<Project[]>('/projects', { params: { limit: 100 } })
      setProjects(list)
      setProjectModalOpen(false); setPage('board')
      await loadBoard(created.id)
      setNotice(`Proyecto “${created.name}” creado.`)
    } catch (error) { throw error }
  }

  async function createTask(data: { title: string; description: string; start_date: string; due_date: string | null; column_id: string }) {
    if (!board) return
    setAppError('')
    try {
      const { data: created } = await workApi.post<TaskCard>(`/boards/${board.id}/tasks`, { title: data.title, description: data.description, start_date: data.start_date, due_date: data.due_date })
      if (data.column_id && data.column_id !== board.columns?.[0]?.id) {
        await workApi.patch(`/tasks/${created.id}`, { column_id: data.column_id, position: 0 })
      }
      await refreshTasks()
      setTaskModalOpen(false); setQuickColumnId(''); setNotice('Tarea creada correctamente.')
    } catch (error) { throw error }
  }

  async function refreshTasks() {
    if (!board) return
    const { data } = await workApi.get<TaskCard[]>(`/boards/${board.id}/tasks`, { params: { limit: 200 } })
    setTasks(data)
  }

  async function moveTask(task: TaskCard, column: Column) {
    if (task.column_id === column.id) return
    setAppError('')
    try {
      await workApi.patch(`/tasks/${task.id}`, { column_id: column.id, position: 0 })
      await refreshTasks()
      setNotice(`“${task.title}” movida a ${column.name}.`)
    } catch (error) { setAppError(apiError(error, 'No se pudo mover la tarea.')) }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null
  const filteredTasks = useMemo(() => tasks.filter((task) => {
    const q = query.trim().toLowerCase()
    return !q || task.title.toLowerCase().includes(q) || task.description.toLowerCase().includes(q)
  }), [tasks, query])
  const totalChecklist = tasks.reduce((sum, task) => sum + task.checklist_total, 0)
  const completedChecklist = tasks.reduce((sum, task) => sum + task.checklist_completed, 0)

  if (authLoading) return <div className="full-screen-loading"><div className="noa-mark"><img src="/noa-eagle.svg" alt="Águila de NOA" /></div><LoaderCircle className="spin" size={22}/><span>Preparando tu espacio…</span></div>
  if (!user) return <LoginScreen onLogin={login}/>

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNavOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar-brand"><div className="noa-mark"><img src="/noa-eagle.svg" alt="Águila de NOA" /></div><div><strong>NOA</strong><small>Trabajo en equipo</small></div><button className="icon-button sidebar-close" onClick={() => setMobileNavOpen(false)} aria-label="Cerrar menú"><X size={19}/></button></div>
        <div className="workspace-switch"><span className="workspace-dot"/><div><strong>Espacio de trabajo</strong><small>{departments.find((d) => user.departments.includes(d.id))?.name ?? 'Mi organización'}</small></div><ChevronDown size={15}/></div>
        <nav className="sidebar-nav">
          <span className="sidebar-label">TRABAJO</span>
          <button className={`nav-item ${page === 'board' ? 'nav-item--active' : ''}`} onClick={() => { setPage('board'); setMobileNavOpen(false) }}><LayoutDashboard size={18}/><span>Tablero Kanban</span></button>
          <button className={`nav-item ${page === 'projects' ? 'nav-item--active' : ''}`} onClick={() => { setPage('projects'); setMobileNavOpen(false) }}><FolderKanban size={18}/><span>Proyectos</span><span className="nav-count">{projects.length}</span></button>
          <span className="sidebar-label sidebar-label--spaced">TU ESPACIO</span>
          <div className="sidebar-projects">
            {projects.slice(0, 6).map((project) => <button key={project.id} className={`project-nav-item ${project.id === selectedProjectId ? 'project-nav-item--active' : ''}`} onClick={() => { setPage('board'); void loadBoard(project.id); setMobileNavOpen(false) }}><span className="project-color-dot"/>{project.name}</button>)}
            {projects.length === 0 && <span className="sidebar-empty">Tus proyectos aparecerán aquí.</span>}
          </div>
          <button className="nav-item nav-item--subtle" onClick={() => setProjectModalOpen(true)}><Plus size={17}/><span>Nuevo proyecto</span></button>
        </nav>
        <div className="sidebar-bottom"><div className="sidebar-help"><span className="help-icon"><CircleHelp size={17}/></span><div><strong>¿Necesitas ayuda?</strong><small>Estamos probando NOA</small></div></div><div className="sidebar-version">NOA · MVP Kanban v1</div></div>
      </aside>
      {mobileNavOpen && <button className="sidebar-overlay" aria-label="Cerrar menú" onClick={() => setMobileNavOpen(false)}/>}

      <main className="main-area">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Abrir menú" onClick={() => setMobileNavOpen(true)}><Menu size={20}/></button>
          <div className="breadcrumbs"><span>NOA</span><span>/</span><strong>{page === 'projects' ? 'Proyectos' : selectedProject?.name ?? 'Tablero Kanban'}</strong></div>
          <div className="topbar-actions"><div className="search-box"><Search size={16}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar tareas…" aria-label="Buscar tareas"/><kbd>⌘ K</kbd></div><button className="icon-button topbar-bell" title="Notificaciones (próximamente)"><Bell size={18}/></button><div className="profile-wrap"><button className="profile-button" onClick={() => setProfileOpen((open) => !open)}><span className="avatar">{initials(user.name)}</span><span className="profile-copy"><strong>{user.name}</strong><small>{roleLabel(user.role)}</small></span><ChevronDown size={15}/></button>{profileOpen && <div className="profile-menu"><div className="profile-menu__info"><strong>{user.name}</strong><span>{user.email}</span></div><button onClick={() => void logout()}><LogOut size={16}/> Cerrar sesión</button></div>}</div></div>
        </header>

        <div className="page-content">
          {appError && <div className="notice notice--error global-notice"><span>{appError}</span><button onClick={() => setAppError('')} aria-label="Cerrar aviso"><X size={15}/></button></div>}
          {notice && <div className="notice notice--success global-notice"><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Cerrar aviso"><X size={15}/></button></div>}
          {page === 'projects' ? (
            <section className="projects-page">
              <div className="page-heading"><div><span className="eyebrow"><FolderKanban size={14}/> ORGANIZACIÓN</span><h1>Proyectos</h1><p>Todo el trabajo del departamento, en un solo lugar.</p></div><button className="button button--primary" onClick={() => setProjectModalOpen(true)}><Plus size={17}/> Nuevo proyecto</button></div>
              {workspaceLoading ? <LoadingPanel label="Cargando proyectos…"/> : projects.length === 0 ? <EmptyProjects onCreate={() => setProjectModalOpen(true)}/> : <div className="projects-grid">{projects.map((project, index) => <button className="project-card" key={project.id} onClick={() => { setPage('board'); void loadBoard(project.id) }}><div className={`project-card__icon project-card__icon--${index % 4}`}><FolderKanban size={21}/></div><div className="project-card__body"><h3>{project.name}</h3><p>{project.description || 'Sin descripción por ahora.'}</p></div><div className="project-card__footer"><span><ListTodo size={15}/>Abrir tablero Kanban</span><ArrowRight size={17}/></div></button>)}</div>}
            </section>
          ) : (
            <section className="board-page">
              <div className="board-heading"><div className="board-heading__copy"><div className="eyebrow"><span className="eyebrow-dot"/> PILOTO · DESARROLLO DE SOFTWARE</div><h1>{selectedProject?.name ?? 'Tu tablero de trabajo'}</h1><p>{selectedProject?.description || 'Organiza los pendientes, comparte avances y mantén las decisiones junto a cada tarea.'}</p><div className="board-heading__meta"><span><Users size={15}/>{people.length} personas visibles</span><span><CheckSquare size={15}/>{completedChecklist}/{totalChecklist} checklist completados</span></div></div><div className="board-heading__actions"><select className="project-select" value={selectedProjectId} onChange={(e) => { if (e.target.value) void loadBoard(e.target.value) }} aria-label="Seleccionar proyecto"><option value="" disabled>Seleccionar proyecto…</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select><button className="button button--primary" onClick={() => { if (selectedProject) { setQuickColumnId(''); setTaskModalOpen(true) } else setProjectModalOpen(true) }}><Plus size={17}/>{selectedProject ? 'Nueva tarea' : 'Crear proyecto'}</button></div></div>
              {!selectedProject && !workspaceLoading ? <EmptyProjects onCreate={() => setProjectModalOpen(true)}/> : workspaceLoading ? <LoadingPanel label="Cargando tablero…"/> : !board ? <div className="load-failure"><strong>No se pudo abrir el tablero.</strong><span>Revisa la conexión y vuelve a intentarlo.</span><button className="button button--secondary button--small" onClick={() => selectedProject && void loadBoard(selectedProject.id)}>Reintentar</button></div> : (
                <div className="kanban-area">
                  <div className="kanban-toolbar"><div className="kanban-toolbar__left"><span className="board-badge"><LayoutDashboard size={14}/> Tablero principal</span><span className="toolbar-separator"/><span className="muted-small">{tasks.length} tareas</span></div><div className="avatar-stack">{people.slice(0, 4).map((person) => <span className="avatar avatar--stack" key={person.id} title={person.name}>{initials(person.name)}</span>)}{people.length > 4 && <span className="avatar avatar--stack avatar--more">+{people.length - 4}</span>}</div></div>
                  <div className="kanban-board" aria-label="Tablero Kanban">
                    {columns.map((column) => {
                      const columnTasks = filteredTasks.filter((task) => task.column_id === column.id).sort((a, b) => a.position - b.position)
                      return <section className="kanban-column" key={column.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const taskId = event.dataTransfer.getData('text/noa-task'); const task = tasks.find((item) => item.id === taskId); if (task) void moveTask(task, column) }}>
                        <div className="kanban-column__header"><div className="column-title-wrap"><span className="column-dot" style={{ backgroundColor: column.color }}/><h2>{column.name}</h2><span className="column-count">{columnTasks.length}</span></div><button className="icon-button icon-button--tiny" title="Opciones de columna" aria-label={`Opciones ${column.name}`}><span className="dots">···</span></button></div>
                        <div className="kanban-column__cards">
                          {columnTasks.map((task) => <button className="task-card" key={task.id} draggable onDragStart={(event) => { event.dataTransfer.setData('text/noa-task', task.id); event.dataTransfer.effectAllowed = 'move' }} onClick={() => setSelectedTaskId(task.id)}>
                            <div className="task-card__top"><span className={`task-status-tag task-status-tag--${column.status_key.toLowerCase()}`}>{column.name}</span><span className="task-card__more">···</span></div>
                            <h3>{task.title}</h3>
                            {task.description && <p className="task-card__description">{task.description}</p>}
                            <div className="task-card__indicators">{task.checklist_total > 0 && <span className={`task-indicator ${task.checklist_completed === task.checklist_total ? 'task-indicator--done' : ''}`}><CheckSquare size={14}/>{task.checklist_completed}/{task.checklist_total}</span>}{task.due_date && <span className={`task-indicator ${task.due_date < today() && column.status_key !== 'DONE' ? 'task-indicator--late' : ''}`}><CalendarDays size={14}/>{dateLabel(task.due_date)}</span>}{task.members.length > 0 && <span className="task-indicator"><Users size={14}/>{task.members.length}</span>}</div>
                            <div className="task-card__footer"><span className="task-card__date"><Clock3 size={13}/>{dateLabel(task.start_date) ?? 'Sin inicio'}</span><span className="task-card__avatars">{task.members.slice(0, 3).map((member) => { const person = people.find((item) => item.id === member.user_id); return <span className="avatar avatar--tiny" key={member.user_id} title={person?.name ?? `Usuario #${member.user_id}`}>{initials(person?.name ?? `U${member.user_id}`)}</span> })}</span></div>
                          </button>)}
                          {columnTasks.length === 0 && <div className="column-empty"><span>Sin tareas</span><small>Arrastra una tarjeta aquí</small></div>}
                        </div>
                        <button className="add-task-inline" onClick={() => { setTaskModalOpen(true); setQuickColumnId(column.id) }}><Plus size={16}/> Añadir tarea</button>
                      </section>
                    })}
                  </div>
                </div>
              )}
            </section>
          )}
          <footer className="page-footer"><span>NOA · Tu trabajo, organizado.</span><span>Versión 1 · MVP Kanban</span></footer>
        </div>
      </main>

      {projectModalOpen && <ProjectModal departments={departments} user={user} onClose={() => setProjectModalOpen(false)} onCreate={createProject}/>}
      {taskModalOpen && board && <CreateTaskModal initialColumnId={quickColumnId} columns={columns} onClose={() => { setTaskModalOpen(false); setQuickColumnId('') }} onCreate={createTask}/>}
      {selectedTaskId && <TaskDetailModal taskId={selectedTaskId} people={people} onClose={() => setSelectedTaskId(null)} onChanged={refreshTasks}/>}
    </div>
  )
}

type LoginScreenProps = { onLogin: (email: string, password: string) => Promise<void> }
function LoginScreen({ onLogin }: LoginScreenProps) {
  const [registerMode, setRegisterMode] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      if (registerMode) {
        const { data } = await identityApi.post<{ message: string }>('/auth/register', { name: name.trim(), email: email.trim().toLowerCase(), password })
        setMessage(data.message || 'Solicitud registrada. Espera la aprobación del administrador.')
        setRegisterMode(false); setPassword('')
      } else await onLogin(email, password)
    } catch (err) { setError(apiError(err, registerMode ? 'No se pudo enviar la solicitud.' : 'No se pudo iniciar sesión.')) }
    finally { setBusy(false) }
  }

  return <main className="login-page">
    <section className="login-hero"><div className="hero-orb hero-orb--one"/><div className="hero-orb hero-orb--two"/><div className="login-hero__content">
      <div className="brand brand--light"><div className="noa-mark noa-mark--light"><img src="/noa-eagle.svg" alt="Águila de NOA" /></div><div><strong>NOA</strong><small>Trabajo en equipo</small></div></div>
      <div className="login-hero__message"><span className="eyebrow eyebrow--light"><ShieldCheck size={15}/> ESPACIO DE TRABAJO</span><h1>El trabajo claro.<br/>El equipo conectado.</h1><p>Organiza proyectos, registra avances y mantén las decisiones junto a cada tarea. Todo en un espacio compartido.</p></div>
      <div className="login-hero__features"><span><CheckSquare size={14}/> Tareas y checklist</span><span><MessageCircle size={14}/> Conversaciones por tarea</span><span><Users size={14}/> Trabajo en equipo</span></div>
      <div className="login-hero__foot"><span>NOA · MVP Kanban</span><span>Datos en tu servidor</span></div>
    </div></section>
    <section className="login-panel"><div className="login-card">
      <div className="login-card__icon"><ShieldCheck size={21}/></div><span className="eyebrow">BIENVENIDO A NOA</span><h2>{registerMode ? 'Solicita acceso' : 'Inicia sesión'}</h2><p className="login-subtitle">{registerMode ? 'Crea tu solicitud. El administrador activará tu cuenta.' : 'Ingresa con tu cuenta de la empresa para continuar.'}</p>
      {error && <div className="notice notice--error">{error}</div>}{message && <div className="notice notice--success">{message}</div>}
      <form className="form-stack" onSubmit={submit}>
        {registerMode && <label className="field"><span>Nombre completo</span><input className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={120} required placeholder="Tu nombre"/></label>}
        <label className="field"><span>Correo electrónico</span><input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="nombre@empresa.com"/></label>
        <label className="field"><span>Contraseña</span><input className="input" type="password" autoComplete={registerMode ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} minLength={registerMode ? 12 : 1} maxLength={128} required placeholder={registerMode ? 'Mínimo 12 caracteres' : 'Tu contraseña'}/></label>
        <button className="button button--primary button--large" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17}/> : null}{busy ? 'Procesando…' : registerMode ? 'Enviar solicitud' : 'Entrar a NOA'}<ArrowRight size={17}/></button>
      </form>
      <div className="login-switch">{registerMode ? '¿Ya tienes cuenta?' : '¿Aún no tienes usuario?'} <button onClick={() => { setRegisterMode((value) => !value); setError(''); setMessage('') }}>{registerMode ? 'Inicia sesión' : 'Solicita acceso'}</button></div>
      <div className="login-security"><ShieldCheck size={15}/> Acceso protegido por el servicio de Identidad de NOA.</div>
    </div></section>
  </main>
}

function LoadingPanel({ label }: { label: string }) {
  return <div className="loading-panel"><LoaderCircle className="spin" size={23}/><span>{label}</span></div>
}

function EmptyProjects({ onCreate }: { onCreate: () => void }) {
  return <div className="empty-projects"><div className="empty-projects__art"><div className="empty-art-card empty-art-card--one"><span/><span/><span/></div><div className="empty-art-card empty-art-card--two"><span/><span/></div><div className="empty-art-center"><FolderKanban size={30}/></div></div><span className="eyebrow">TU ESPACIO DE TRABAJO</span><h2>Empieza con tu primer proyecto</h2><p>Crea un proyecto, agrega tareas y organiza el trabajo de tu equipo en un tablero Kanban.</p><button className="button button--primary" onClick={onCreate}><Plus size={17}/> Crear proyecto</button></div>
}

type ProjectModalProps = { departments: Department[]; user: User; onClose: () => void; onCreate: (data: { name: string; description: string; department_id: number }) => Promise<void> }
function ProjectModal({ departments, user, onClose, onCreate }: ProjectModalProps) {
  const allowed = departments.filter((department) => user.role === 'SUPERADMIN' || user.departments.includes(department.id))
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [departmentId, setDepartmentId] = useState(String(allowed[0]?.id ?? ''))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    if (!departmentId) { setError('No hay un departamento disponible para crear el proyecto.'); return }
    setBusy(true)
    try { await onCreate({ name: name.trim(), description: description.trim(), department_id: Number(departmentId) }) }
    catch (err) { setError(apiError(err)) }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop" onMouseDown={onClose}><section className="simple-modal" role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()}><header className="simple-modal__header"><div><span className="eyebrow">NUEVO ESPACIO</span><h2>Crear proyecto</h2><p>El proyecto tendrá su propio tablero Kanban.</p></div><button className="icon-button" onClick={onClose} aria-label="Cerrar"><X size={20}/></button></header>{error && <div className="notice notice--error">{error}</div>}<form className="form-stack" onSubmit={submit}><label className="field"><span>Nombre del proyecto</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={160} placeholder="Ej. Bot empresarial" required autoFocus/></label><label className="field"><span>Departamento</span><select className="input" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)} required><option value="">Seleccionar departamento…</option>{allowed.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}</select><em>Selecciona el departamento configurado para esta instancia de Trabajo.</em></label><label className="field"><span>Descripción <em>Opcional</em></span><textarea className="input textarea" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} maxLength={10000} placeholder="¿Qué busca conseguir el equipo?"/></label><div className="form-actions"><button type="button" className="button button--secondary" onClick={onClose}>Cancelar</button><button className="button button--primary" disabled={busy}>{busy ? 'Creando…' : 'Crear proyecto'}<ArrowRight size={16}/></button></div></form></section></div>
}

type CreateTaskModalProps = { initialColumnId: string; columns: Column[]; onClose: () => void; onCreate: (data: { title: string; description: string; start_date: string; due_date: string | null; column_id: string }) => Promise<void> }
function CreateTaskModal({ initialColumnId, columns, onClose, onCreate }: CreateTaskModalProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [startDate, setStartDate] = useState(today())
  const [dueDate, setDueDate] = useState('')
  const [columnId, setColumnId] = useState(initialColumnId || columns[0]?.id || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { await onCreate({ title: title.trim(), description: description.trim(), start_date: startDate, due_date: dueDate || null, column_id: columnId }) }
    catch (err) { setError(apiError(err)) }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop" onMouseDown={onClose}><section className="simple-modal" role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()}><header className="simple-modal__header"><div><span className="eyebrow">NUEVA TAREA</span><h2>Agregar al tablero</h2><p>Registra qué hay que hacer y cuándo empieza.</p></div><button className="icon-button" onClick={onClose} aria-label="Cerrar"><X size={20}/></button></header>{error && <div className="notice notice--error">{error}</div>}<form className="form-stack" onSubmit={submit}><label className="field"><span>Título de la tarea</span><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} minLength={1} maxLength={240} required autoFocus placeholder="Ej. Conectar el bot con Telegram"/></label><label className="field"><span>Apuntes generales <em>Opcional</em></span><textarea className="input textarea" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} maxLength={20000} placeholder="Contexto o detalles iniciales…"/></label><div className="form-two-cols"><label className="field"><span>Fecha de inicio</span><input className="input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required/></label><label className="field"><span>Fecha final <em>Opcional</em></span><input className="input" type="date" min={startDate} value={dueDate} onChange={(e) => setDueDate(e.target.value)}/></label></div><label className="field"><span>Columna inicial</span><select className="input" value={columnId} onChange={(e) => setColumnId(e.target.value)}>{columns.map((column) => <option key={column.id} value={column.id}>{column.name}</option>)}</select></label><div className="form-actions"><button type="button" className="button button--secondary" onClick={onClose}>Cancelar</button><button className="button button--primary" disabled={busy || !columnId}>{busy ? 'Creando…' : 'Crear tarea'}<Plus size={16}/></button></div></form></section></div>
}
