export interface SessionUser {
  id: string
  email: string
  name: string
  email_verified_at: string | null
}

export interface AuthError {
  message: string
  status: number
}
