export type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  status: number
  code?: string
  fieldErrors?: FieldErrors

  constructor(opts: { message: string; status: number; code?: string; fieldErrors?: FieldErrors }) {
    super(opts.message)
    this.name = 'ApiError'
    this.status = opts.status
    this.code = opts.code
    this.fieldErrors = opts.fieldErrors
  }
}
