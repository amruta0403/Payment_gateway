import NextAuth, { NextAuthOptions } from 'next-auth'
import KeycloakProvider from 'next-auth/providers/keycloak'

export const authOptions: NextAuthOptions = {
  providers: [
    KeycloakProvider({
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET!,
      issuer: `${process.env.KEYCLOAK_URL}/realms/${process.env.KEYCLOAK_REALM}`,
    }),
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account) {
        token.accessToken  = account.access_token
        token.refreshToken = account.refresh_token
        token.expiresAt    = account.expires_at
      }
      // Decode JWT to get merchant_id and roles
      if (token.accessToken) {
        try {
          const parts = (token.accessToken as string).split('.')
          const claims = JSON.parse(Buffer.from(parts[1], 'base64url').toString())
          token.merchantId = claims.merchant_id
          token.roles = claims.realm_access?.roles || []
          token.sub = claims.sub
          token.email = claims.email
          token.name = claims.name
        } catch { /* ignore */ }
      }
      return token
    },
    async session({ session, token }) {
      return {
        ...session,
        accessToken: token.accessToken as string,
        merchantId:  token.merchantId as string,
        roles:       token.roles as string[],
        user: {
          ...session.user,
          id:    token.sub as string,
          email: token.email as string,
          name:  token.name as string,
        },
      }
    },
  },
  pages: {
    signIn: '/login',
    error:  '/login',
  },
  session: { strategy: 'jwt', maxAge: 3600 },
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }
