import {
  forgotPassword,
  getCsrf,
  getSession,
  login,
  logout,
  register,
  resendVerification,
  resetPassword,
  verifyEmail,
  type LoginPayload,
  type RegisterPayload,
} from '@/shared/api'

export const authApi = {
  ensureCsrf: getCsrf,
  session: getSession,
  login: async (payload: LoginPayload) => {
    await getCsrf()
    return login(payload)
  },
  register: async (payload: RegisterPayload) => {
    await getCsrf()
    return register(payload)
  },
  logout: async () => {
    await getCsrf()
    return logout()
  },
  verifyEmail: async (token: string) => {
    await getCsrf()
    return verifyEmail(token)
  },
  resendVerification: async (email: string) => {
    await getCsrf()
    return resendVerification(email)
  },
  forgotPassword: async (email: string) => {
    await getCsrf()
    return forgotPassword(email)
  },
  resetPassword: async (token: string, password: string) => {
    await getCsrf()
    return resetPassword(token, password)
  },
}
