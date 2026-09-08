import { type NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'
import { applyLangParam } from '@/lib/i18n/langParam'

export async function proxy(request: NextRequest) {
  const response = await updateSession(request)
  return applyLangParam(request, response)
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
