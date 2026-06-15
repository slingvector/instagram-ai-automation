import { NextResponse } from 'next/server';
import { getDb, getDedupDb } from '@/lib/db';

export async function POST(req) {
  try {
    const { action } = await req.json();

    if (action === 'retry_failed') {
      const db = await getDb();
      await db.run("UPDATE reel_states SET state='DISCOVERED' WHERE state='FAILED'");
      return NextResponse.json({ success: true, message: 'All failed jobs have been reset to DISCOVERED state.' });
    }

    if (action === 'purge_db') {
      const db = await getDb();
      const dedupDb = await getDedupDb();
      
      // Delete all records from dedup tables
      await dedupDb.run("DELETE FROM seen_urls");
      await dedupDb.run("DELETE FROM seen_phash");
      await dedupDb.run("DELETE FROM seen_dm_ids");
      
      // Delete all records from state db
      await db.run("DELETE FROM reel_states");
      
      return NextResponse.json({ success: true, message: 'Databases have been completely purged. Pipeline will restart from scratch.' });
    }

    return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
