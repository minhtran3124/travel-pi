import { NextResponse, type NextRequest } from 'next/server'
import { isProtected, updateSession } from '@/lib/supabase/middleware'
import { applyLangParam } from '@/lib/i18n/langParam'

export async function proxy(request: NextRequest) {
  let response: NextResponse
  try {
    response = await updateSession(request)
  } catch (error) {
    // Fail closed: an auth-backend outage must not 500 every matched path,
    // including /auth/login — the page a signed-out user needs to recover.
    // No I/O here beyond the pathname read, so this boundary cannot itself throw.
    console.error(`[proxy] updateSession failed for ${request.nextUrl.pathname}:`, error)
    if (isProtected(request.nextUrl.pathname)) {
      const loginUrl = request.nextUrl.clone()
      loginUrl.pathname = '/auth/login'
      loginUrl.search = ''
      loginUrl.searchParams.set(
        'next',
        `${request.nextUrl.pathname}${request.nextUrl.search}`,
      )
      return NextResponse.redirect(loginUrl)
    }
    return NextResponse.next({ request })
  }
  return applyLangParam(request, response)
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
