import axios from 'axios'

const api = axios.create({ baseURL: 'http://localhost:8000' })

export const analyzeFile = async (file, target) => {
  const form = new FormData()
  form.append('file', file)
  if (target) form.append('target', target)
  const { data } = await api.post('/api/v1/analyze', form)
  return data
}

export const getReport = async (runId) => {
  const { data } = await api.get(`/api/v1/report/${runId}`)
  return data
}

export const getHtmlReport = async (runId) => {
  const { data } = await api.get(`/api/v1/report/${runId}/html`)
  return data
}

export const downloadTerraform = async (runId) => {
  const response = await api.get(`/api/v1/terraform/${runId}`,
    { responseType: 'blob' })
  const url = URL.createObjectURL(response.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `migration-terraform-${runId.slice(0,8)}.zip`
  a.click()
  URL.revokeObjectURL(url)
}

export const getRuns = async () => {
  const { data } = await api.get('/api/v1/runs')
  return data
}

export const deleteRun = async (runId) => {
  const { data } = await api.delete(`/api/v1/runs/${runId}`)
  return data
}

export const getHealth = async () => {
  const { data } = await api.get('/api/v1/health')
  return data
}
