import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const repositories = { 'Garda-Studio/daytandem-releases': 'daytandem', 'Garda-Studio/commandless-releases': 'commandless' };
export async function synchronize({ repository, secret, tag, deleted = false, requestId, fetcher = fetch, pause = ms => new Promise(resolve => setTimeout(resolve, ms)) }) {
  const product = repositories[repository];
  if (!product || !secret || secret.length < 40 || !/^v\d+\.\d+\.\d+$/.test(tag) || !/^[A-Za-z0-9_-]{8,100}$/.test(requestId)) throw Error('Missing/invalid release synchronization configuration');
  for (let attempt = 0; attempt < 12; attempt++) {
    try {
      const response = await fetcher(`https://garda-studio.com/api/releases/sync/${product}`, { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(60_000), headers: { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ requestId, tag, deleted }) });
      if (response.ok) {
        const result = await response.json();
        if (result.ok === true && result.product === product && result.requestId === requestId && Number.isSafeInteger(result.revision) && result.revision > 0) return result;
      }
      if ([400, 401, 403, 404].includes(response.status)) throw Object.assign(Error('Non-retryable synchronization configuration error'), { permanent: true });
    } catch (error) { if (error.permanent) throw error; }
    if (attempt < 11) await pause(300_000);
  }
  throw Error('Site did not acknowledge the catalog after 12 attempts. Last good catalog retained; rerun this workflow.');
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const event = JSON.parse(await readFile(process.env.GITHUB_EVENT_PATH, 'utf8'));
  // Draft/prerelease edits must not alter the stable catalog.
  if (event.release?.draft || event.release?.prerelease) process.exit(0);
  const result = await synchronize({ repository: process.env.GITHUB_REPOSITORY, secret: process.env.SITE_SYNC_SECRET, tag: event.inputs?.tag || event.release?.tag_name, deleted: event.inputs?.deleted === true || event.inputs?.deleted === 'true' || event.action === 'deleted', requestId: `${process.env.GITHUB_RUN_ID}-${process.env.GITHUB_RUN_ATTEMPT}` });
  console.log(`Catalog acknowledged: ${result.product}, revision ${result.revision}.`);
}
