import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  try {
    const db = await getDb();
    
    const rows = await db.all('SELECT state, COUNT(*) as count FROM reel_states GROUP BY state');
    
    const metrics = {
      TOTAL: 0,
      DISCOVERED: 0,
      DOWNLOADED: 0,
      CAPTIONED: 0,
      JOB_CREATED: 0,
      MEDIA_PROCESSED: 0,
      DRIVE_UPLOADED: 0,
      POSTED: 0,
      FAILED: 0,
    };
    
    for (const row of rows) {
      const st = row.state;
      if (metrics[st] !== undefined) {
        metrics[st] = row.count;
      } else {
        metrics[st] = row.count; // For unexpected states
      }
      metrics.TOTAL += row.count;
    }
    
    return NextResponse.json(metrics);
  } catch (error) {
    console.error('Error fetching metrics:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
