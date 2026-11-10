/** localStorage 封装：应用 JWT、云端访问令牌与云端票据的存取。
 *
 * - pv_token：当前身份令牌（应用 JWT 或云端 access token）
 * - pv_ticket：云端签发的短期票据，后端用它确认云端身份（见 cloud/auth.ts）
 */

const TOKEN_KEY = 'pv_token'
const TICKET_KEY = 'pv_ticket'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getTicket(): string | null {
  return localStorage.getItem(TICKET_KEY)
}

export function setTicket(ticket: string): void {
  localStorage.setItem(TICKET_KEY, ticket)
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(TICKET_KEY)
}

export function isAuthed(): boolean {
  return Boolean(getToken())
}
