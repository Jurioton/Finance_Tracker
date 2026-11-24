import axios from 'axios'

// One shared HTTP client. It adds the login token to every request automatically.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // Token expired or invalid: log the user out
    if (err.response?.status === 401 && localStorage.getItem('token')) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

// Turns a FastAPI error response into a readable message
export function errorMessage(err) {
  if (!err.response) {
    // No response at all: the backend is down, or the browser blocked it (CORS)
    return `Can't reach the server at ${api.defaults.baseURL}. Check that the backend is running.`
  }
  const detail = err.response.data?.detail
  if (typeof detail === 'string') return detail
  if (typeof detail?.message === 'string') return detail.message
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join(', ')
  return `Something went wrong (error ${err.response.status}). Please try again.`
}

export default api
