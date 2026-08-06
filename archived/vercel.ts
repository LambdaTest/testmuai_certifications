import { type VercelConfig } from '@vercel/config/v1';

/**
 * Vercel project configuration.
 *
 * This replaces vercel.json — it is typed and can read env vars. Do not add a
 * vercel.json alongside it.
 *
 * Cron routes must verify the CRON_SECRET header themselves; Vercel does not
 * authenticate them for us. See src/app/api/README.md.
 */
export const config: VercelConfig = {
  framework: 'nextjs',

  crons: [
    // Close out attempts whose timer expired but that were never submitted
    // (browser closed, network dropped). Grades them on whatever was saved.
    { path: '/api/cron/expire-attempts', schedule: '*/5 * * * *' },

    // Mark issued credentials past their expiry date as expired.
    { path: '/api/cron/expire-credentials', schedule: '0 2 * * *' },
  ],
};
