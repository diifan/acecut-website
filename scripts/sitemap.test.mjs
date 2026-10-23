import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { generateSitemap } from './sitemap.mjs';

test('includes content, excludes verification/noindex, rejects invalid canonicals', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'acecut-sitemap-'));
  const root = pathToFileURL(dir + '/');
  const page = path => `<link rel="canonical" href="https://acecut.goswie.com${path}">`;
  try {
    await writeFile(join(dir, 'index.html'), page('/'));
    await writeFile(join(dir, 'guide.html'), page('/guide'));
    await writeFile(join(dir, 'google123abc.html'), 'google-site-verification: google123abc.html');
    await writeFile(join(dir, 'private.html'), '<meta content="noindex,follow" name="robots">');
    const xml = await generateSitemap(root);
    assert.equal((xml.match(/<loc>/g) ?? []).length, 2);
    assert.ok(xml.includes('/guide</loc>'));
    assert.ok(!xml.includes('google123abc'));
    await writeFile(join(dir, 'bad.html'), page('/different'));
    await assert.rejects(generateSitemap(root), /does not match route/);
    await writeFile(join(dir, 'bad.html'), '<title>No canonical</title>');
    await assert.rejects(generateSitemap(root), /Expected one canonical/);
  } finally { await rm(dir, { recursive: true, force: true }); }
});
