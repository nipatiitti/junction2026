import { defineRelations } from 'drizzle-orm'
import * as schema from './schema.ts'

// Add relations between tables here, they power `db.query.*`.
export const relations = defineRelations(schema)
