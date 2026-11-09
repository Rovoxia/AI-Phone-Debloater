import type { APIRoute } from 'astro';
import { exec } from 'node:child_process';

// Simple newsletter endpoint using GitHub Actions or third-party service.
// Currently accepts POST and stores to a log file (or can integrate with Mailchimp/Substack).
// For v1, we just log the signup. In production, replace with proper email service.

export const POST: APIRoute = async ({ request }) => {
  try {
    const body = await request.json();
    const email = body.email;

    if (!email || typeof email !== 'string') {
      return new Response(JSON.stringify({ success: false, error: 'Email required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Store in a local file (ephemeral) or could use GitHub API
    // For now just acknowledge
    return new Response(JSON.stringify({ success: true, message: 'Subscribed', email }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (e) {
    return new Response(JSON.stringify({ success: false, error: 'Invalid email' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
};

export const GET: APIRoute = async () => {
  return new Response(JSON.stringify({ status: 'ok' }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
};
