import { generateSitemap } from './sitemap.mjs';
import { cp, mkdir, rm, writeFile } from 'node:fs/promises';
const root = new URL('../', import.meta.url);
await rm(new URL('dist/', root), { recursive: true, force: true });
await mkdir(new URL('dist/', root), { recursive: true });
await cp(new URL('public/', root), new URL('dist/', root), { recursive: true });
await writeFile(new URL('dist/sitemap.xml', root), await generateSitemap(new URL('public/', root)));
console.log('Built website/dist — static files ready for acecut.goswie.com');
