import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const state = searchParams.get('state') || 'CAPTIONED';
    const limit = parseInt(searchParams.get('limit') || '50');
    
    const db = await getDb();
    
    let reels;
    if (state === 'FINISHED') {
      reels = await db.all(`
        SELECT * FROM reel_states 
        WHERE state IN ('RELAYED_TO_FIREBASE', 'RELAYED_TO_PHONE', 'SYNCED_TO_DRIVE', 'POSTED')
           OR firebase_url IS NOT NULL 
           OR hls_cdn_url IS NOT NULL 
        ORDER BY updated_at DESC LIMIT ?
      `, [limit]);
    } else {
      reels = await db.all('SELECT * FROM reel_states WHERE state = ? ORDER BY created_at DESC LIMIT ?', [state, limit]);
    }
    
    return NextResponse.json({ reels });
  } catch (error) {
    console.error('Error fetching reels:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

export async function PUT(request) {
  try {
    const body = await request.json();
    const { url, ai_metadata, state } = body;
    
    if (!url) {
      return NextResponse.json({ error: 'URL is required' }, { status: 400 });
    }
    
    const db = await getDb();
    
    let query = 'UPDATE reel_states SET updated_at = CURRENT_TIMESTAMP';
    const params = [];
    
    if (ai_metadata) {
      query += ', ai_metadata = ?';
      params.push(JSON.stringify(ai_metadata));
    }
    
    if (state) {
      query += ', state = ?';
      params.push(state);
    }
    
    query += ' WHERE url = ?';
    params.push(url);
    
    await db.run(query, params);
    
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Error updating reel:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
