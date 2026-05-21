/**
 * services/api.ts
 * ---------------
 * PURPOSE:
 *   Central Axios instance for all HTTP calls to the FastAPI backend.
 *   Every screen imports from here — never creates its own axios instance.
 *
 * CONCEPT — Axios Interceptors
 *   An interceptor is a function that runs on every request or response
 *   before it reaches your component code:
 *
 *   Request interceptor  → automatically attach the JWT token as a header
 *   Response interceptor → catch 401 errors globally, trigger logout
 *
 *   Without interceptors you'd have to write:
 *       headers: { Authorization: `Bearer ${token}` }
 *   on every single API call. The interceptor does it once for all calls.
 *
 * CONCEPT — BASE_URL
 *   When running on a physical device, "localhost" refers to the device itself,
 *   not your development machine. Use your machine's local network IP instead.
 *   - Android emulator:  10.0.2.2  (special alias for host machine)
 *   - Physical device:   your machine's LAN IP (e.g. 192.168.1.100)
 *   - Expo Go on device: same LAN IP
 *   - iOS simulator:     localhost works fine
 *
 *   Change BASE_URL in .env or directly here before testing on a device.
 */

import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ── Config ──────────────────────────────────────────────────────────────────
// Android emulator → 10.0.2.2; physical device → your LAN IP
export const BASE_URL = 'http://192.168.1.3:8000';

const TOKEN_KEY = 'auth_token';

// ── Axios instance ───────────────────────────────────────────────────────────
const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Request interceptor: attach JWT token ────────────────────────────────────
api.interceptors.request.use(
  async (config) => {
    console.log('[API] -->', config.method?.toUpperCase(), config.baseURL, config.url);
    try {
      const token = await AsyncStorage.getItem(TOKEN_KEY);
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch (e) {
      console.warn('[API] AsyncStorage read failed:', e);
    }
    return config;
  },
  (error) => {
    console.error('[API] Request setup error:', error);
    return Promise.reject(error);
  },
);

// ── Response interceptor: log errors ─────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('[API] Response error:', error?.message, error?.response?.status, error?.response?.data);
    return Promise.reject(error);
  },
);

// ── Token helpers (used by AuthContext) ─────────────────────────────────────
export const saveToken  = (token: string) => AsyncStorage.setItem(TOKEN_KEY, token);
export const clearToken = ()              => AsyncStorage.removeItem(TOKEN_KEY);
export const getToken   = ()              => AsyncStorage.getItem(TOKEN_KEY);

// ── Health check ────────────────────────────────────────────────────────────
export type HealthStatus = 'ok' | 'degraded' | 'unreachable';

export async function checkHealth(): Promise<HealthStatus> {
  try {
    const res = await axios.get<{ status: string }>(`${BASE_URL}/health`, { timeout: 4000 });
    return res.data.status === 'ok' ? 'ok' : 'degraded';
  } catch {
    return 'unreachable';
  }
}

// ── Auth endpoints ───────────────────────────────────────────────────────────
export interface LoginPayload    { email: string; password: string }
export interface RegisterPayload { email: string; password: string; full_name: string; department?: string }
export interface TokenResponse   { access_token: string; token_type: string }
export interface UserResponse    { id: number; email: string; full_name: string; role: string; department: string }

export const authApi = {
  login:    (data: LoginPayload)    => api.post<TokenResponse>('/auth/login', data),
  register: (data: RegisterPayload) => api.post<UserResponse>('/auth/register', data),
  me:       ()                      => api.get<UserResponse>('/auth/me'),
};

// ── Admin endpoints ──────────────────────────────────────────────────────────
export interface DocumentInfo {
  id:          number;
  filename:    string;
  department:  string;
  source_type: string;
  chunk_count: number;
  uploaded_at: string;
}

export const adminApi = {
  listDocuments: (department?: string) =>
    api.get<DocumentInfo[]>('/admin/documents', {
      params: department ? { department } : {},
    }),

  getDocument: (id: number) =>
    api.get<DocumentInfo>(`/admin/documents/${id}`),

  deleteDocument: (id: number) =>
    api.delete<{ detail: string }>(`/admin/documents/${id}`),

  uploadDocument: (
    formData: FormData,
    onProgress?: (pct: number) => void,
  ) =>
    api.post('/admin/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded * 100) / e.total));
        }
      },
    }),
};

export default api;
