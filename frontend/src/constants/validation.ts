/** 前端校验规则常量：与后端一致（docs/api_doc.md 4.1/4.6、backend schemas/auth.py、D2/D26） */

export const USERNAME_RE = /^[\w\u4e00-\u9fa5-]{2,30}$/

export const PASSWORD_RE = /^(?=.*[A-Za-z])(?=.*\d).{8,64}$/

export const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.bmp']

export const MAX_UPLOAD_MB = 10
