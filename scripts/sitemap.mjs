import { readdir, readFile } from 'node:fs/promises';
import { relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const origin = 'https://acecut.goswie.com';
const escapeXml = value => value.replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

export async function generateSitemap(directory) {
  const root = fileURLToPath(directory);
  const urls = [];
  async function visit(folder) {
    for (const entry of await readdir(folder, { withFileTypes: true })) {
      const path = `${folder}/${entry.name}`;
      if (entry.isDirectory()) { await visit(path); continue; }
      if (!entry.name.endsWith('.html')) continue;
      const source = await readFile(path, 'utf8');
      // Verification files must stay deployed but are not search content.
      if (/^google-site-verification:\s*google[a-z0-9]+\.html\s*$/.test(source)) continue;
      const metas = source.match(/<meta\b[^>]*>/gi) ?? [];
      if (metas.some(tag => /\bname=["'](?:robots|googlebot)["']/i.test(tag) && /\bcontent=["'][^"']*noindex/i.test(tag))) continue;
      const tags = source.match(/<link\b[^>]*>/gi) ?? [];
      const canonical = tags.filter(tag => /\brel=["']canonical["']/i.test(tag));
      if (canonical.length !== 1) throw new Error(`Expected one canonical: ${path}`);
      const url = canonical[0].match(/\bhref=["']([^"']+)["']/i)?.[1];
      const route = '/' + relative(root, path).replaceAll('\\', '/').replace(/(?:^|\/)index\.html$/, '').replace(/\.html$/, '').replace(/\/$/, '');
      if (url !== origin + route) throw new Error(`Canonical does not match route: ${path}`);
      if (urls.includes(url)) throw new Error(`Duplicate canonical: ${url}`);
      urls.push(url);
    }
  }
  await visit(root);
  if (!urls.includes(origin + '/')) throw new Error('Homepage missing from sitemap');
  return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    urls.sort().map(url => `  <url><loc>${escapeXml(url)}</loc></url>`).join('\n') + '\n</urlset>\n';
}
