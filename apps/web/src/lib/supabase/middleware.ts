import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

/**
 * Route prefixes that require a Supabase session. These pages render only
 * trip-backed data, and the API scopes trips/expenses on the subject of the
 * verified bearer token (`apps/api/app/core/auth.py`) — so serving them to a
 * signed-out visitor can only produce 401s, never content.
 */
const PROTECTED_PREFIXES = ['/trips'] as const

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  )
}

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  })

  // With Fluid compute, don't put this client in a global environment
  // variable. Always create a new one on each request.
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          supabaseResponse = NextResponse.next({
            request,
          })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  // Do not run code between createServerClient and
  // supabase.auth.getClaims(). A simple mistake could make it very hard to debug
  // issues with users being randomly logged out.

  // IMPORTANT: If you remove getClaims() and you use server-side rendering
  // with the Supabase client, your users may be randomly logged out.
  const { data } = await supabase.auth.getClaims()

  if (!data?.claims && isProtected(request.nextUrl.pathname)) {
    const loginUrl = request.nextUrl.clone()
    loginUrl.pathname = '/auth/login'
    loginUrl.search = ''
    // `next` is the return path after sign-in — same param name the
    // /auth/confirm and /auth/callback routes already use.
    loginUrl.searchParams.set(
      'next',
      `${request.nextUrl.pathname}${request.nextUrl.search}`,
    )

    const redirectResponse = NextResponse.redirect(loginUrl)
    // Carry over any session cookies the refresh above just rotated, or the
    // browser and server fall out of sync (see the note below).
    for (const cookie of supabaseResponse.cookies.getAll()) {
      redirectResponse.cookies.set(cookie)
    }
    return redirectResponse
  }

  // IMPORTANT: You *must* return the supabaseResponse object as it is.
  // If you're creating a new response object with NextResponse.next() make sure to:
  // 1. Pass the request in it, like so:
  //    const myNewResponse = NextResponse.next({ request })
  // 2. Copy over the cookies, like so:
  //    myNewResponse.cookies.setAll(supabaseResponse.cookies.getAll())
  // 3. Change the myNewResponse object to fit your needs, but avoid changing
  //    the cookies!
  // 4. Finally:
  //    return myNewResponse
  // If this is not done, you may be causing the browser and server to go out
  // of sync and terminate the user's session prematurely!

  return supabaseResponse
}
