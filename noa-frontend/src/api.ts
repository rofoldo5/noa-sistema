import axios, { type InternalAxiosRequestConfig } from 'axios'

export const TOKEN_KEY = 'noa.access_token'

export const identityApi = axios.create({ baseURL: '/identity-api', timeout: 15000, headers: { Accept: 'application/json' } })
export const workApi = axios.create({ baseURL: '/work-api', timeout: 30000, headers: { Accept: 'application/json' } })

function applyToken(config: InternalAxiosRequestConfig) {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
}
identityApi.interceptors.request.use(applyToken)
workApi.interceptors.request.use(applyToken)

let lastUnauthorizedAt = 0
const onResponseError = (error: any) => {
  const url = String(error?.config?.url ?? '')
  if (error?.response?.status === 401 && !url.includes('/auth/login') && !url.includes('/auth/register')) {
    const now = Date.now()
    if (now - lastUnauthorizedAt > 1000) {
      lastUnauthorizedAt = now
      window.dispatchEvent(new CustomEvent('noa:unauthorized'))
    }
  }
  return Promise.reject(error)
}
identityApi.interceptors.response.use((response) => response, onResponseError)
workApi.interceptors.response.use((response) => response, onResponseError)

export function apiError(error: unknown, fallback = 'No se pudo completar la operación.'): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return 'No hay conexión con NOA. Comprueba que los servicios estén disponibles.'
    const body = error.response.data as { detail?: unknown; message?: unknown } | undefined
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item: any) => item.msg).filter(Boolean).join('. ') || fallback
    if (typeof body?.message === 'string') return body.message
    if (error.response.status === 413) return 'El archivo supera el tamaño permitido.'
    if (error.response.status === 415) return 'Formato no permitido. Usa una imagen o un video compatible.'
  }
  return fallback
}

export function mediaUrl(path: string) {
  if (/^https?:\/\//i.test(path)) return path
  return `/work-api${path.startsWith('/') ? path : `/${path}`}`
}
