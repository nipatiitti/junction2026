import { drizzle } from 'drizzle-orm/libsql'
import { DATABASE_URL } from '$app/env/private'
import { relations } from './relations.ts'

if (!DATABASE_URL) throw new Error('DATABASE_URL is not set')

export const db = drizzle({ connection: { url: DATABASE_URL }, relations })
