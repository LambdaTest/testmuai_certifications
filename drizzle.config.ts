import { defineConfig } from 'drizzle-kit';

/**
 * Migrations run against the DIRECT connection, not the pooled one — PgBouncer
 * in transaction mode cannot handle DDL and prepared statements reliably.
 */
export default defineConfig({
  schema: './src/db/schema/index.ts',
  out: './src/db/migrations',
  dialect: 'postgresql',
  dbCredentials: {
    url: process.env.DATABASE_URL_UNPOOLED!,
  },
  strict: true,
  verbose: true,
});
