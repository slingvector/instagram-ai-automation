import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  try {
    const db = await getDb();
    
    const activeJobs = await db.all(`
      SELECT * FROM reel_states 
      WHERE state NOT IN ('FAILED', 'POSTED', 'RELAYED_TO_FIREBASE', 'RELAYED_TO_PHONE', 'SYNCED_TO_DRIVE')
      ORDER BY updated_at DESC LIMIT 50
    `);

    const failedJobs = await db.all(`
      SELECT * FROM reel_states 
      WHERE state = 'FAILED'
      ORDER BY updated_at DESC LIMIT 20
    `);

    return NextResponse.json({ active: activeJobs, failed: failedJobs });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
