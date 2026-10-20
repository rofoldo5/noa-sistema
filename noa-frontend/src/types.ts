export interface User {
  id: number
  name: string
  email: string
  role: string
  role_name?: string
  active: boolean
  departments: number[]
  permissions?: string[]
}
export interface Department { id: number; name: string }
export interface Project {
  id: string
  department_id: number
  name: string
  description: string
  status: string
  created_by_user_id?: number
  created_at?: string
  updated_at?: string
  board_id?: string
}
export interface Column {
  id: string
  name: string
  status_key: string
  position: number
  color: string
  is_done: boolean
}
export interface Board { id: string; project_id: string; name: string; board_type: string; columns: Column[] }
export interface TaskMember { user_id: number; role: 'RESPONSIBLE' | 'COLLABORATOR' }
export interface TaskCard {
  id: string
  board_id: string
  column_id: string
  column_name: string
  title: string
  description: string
  start_date: string
  due_date: string | null
  position: number
  created_by_user_id: number
  created_at: string
  updated_at: string
  completed_at: string | null
  archived_at: string | null
  checklist_total: number
  checklist_completed: number
  members: TaskMember[]
}
export interface ChecklistItem {
  id: string
  section_id: string
  title: string
  is_completed: boolean
  position: number
  created_by_user_id: number
  completed_by_user_id?: number | null
  completed_at?: string | null
}
export interface TaskSection {
  id: string
  task_id: string
  title: string
  notes: string
  position: number
  updated_at?: string
  checklist: ChecklistItem[]
}
export interface Attachment {
  id: string
  original_filename: string
  media_type: string
  size_bytes: number
  sha256: string
  uploaded_by_user_id: number
  created_at: string
  preview_url: string
  download_url: string
  preview_url_expires_in: number | null
}
export interface Comment {
  id: string
  task_id: string
  author_user_id: number
  body: string
  mentions: number[]
  attachments: Attachment[]
  created_at: string
  updated_at: string
}
export interface Activity {
  id: string
  actor_user_id: number
  event_type: string
  summary: string
  details: Record<string, unknown>
  created_at: string
}
export interface TaskDetail extends TaskCard {
  sections: TaskSection[]
  comments: Comment[]
  activity: Activity[]
}
