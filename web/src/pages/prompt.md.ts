import type { APIRoute } from 'astro';
import fs from 'node:fs';
import path from 'node:path';

export const prerender = true;

export const GET: APIRoute = async () => {
  const promptPathWeb = path.resolve(process.cwd(), '..', 'prompt', 'master-prompt.md');
  const promptPathRoot = path.resolve(process.cwd(), 'prompt', 'master-prompt.md');
  const finalPath = fs.existsSync(promptPathWeb) ? promptPathWeb : promptPathRoot;
  const content = fs.readFileSync(finalPath, 'utf8');

  return new Response(content, {
    headers: {
      'Content-Type': 'text/markdown; charset=utf-8',
      'Cache-Control': 'public, max-age=3600'
    }
  });
};
