import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';

export async function POST(request) {
  try {
    const { url, rating } = await request.json();
    if (!url || !rating) {
      return NextResponse.json({ error: 'URL and rating are required' }, { status: 400 });
    }

    const db = await getDb();
    
    // 1. Get current reel info to find the source
    const reel = await db.get('SELECT * FROM reel_states WHERE url = ?', [url]);
    if (!reel) {
      return NextResponse.json({ error: 'Reel not found' }, { status: 404 });
    }

    // 2. Update AI Metadata with the rating
    let metadata = {};
    try {
      metadata = JSON.parse(reel.ai_metadata || '{}');
    } catch (e) {}
    metadata.rating = rating;
    metadata.rating_updated_at = new Date().toISOString();

    await db.run('UPDATE reel_states SET ai_metadata = ? WHERE url = ?', [JSON.stringify(metadata), url]);

    // 3. Update YAML weight based on rating
    if (reel.source) {
      const configDir = path.join(process.cwd(), '..', 'config');
      if (fs.existsSync(configDir)) {
        const files = fs.readdirSync(configDir).filter(f => f.endsWith('.yaml'));
        let found = false;

        for (const file of files) {
          if (found) break;
          const filePath = path.join(configDir, file);
          try {
            const content = fs.readFileSync(filePath, 'utf8');
            const doc = yaml.load(content);
            if (doc && doc.sources && Array.isArray(doc.sources)) {
              for (const sourceObj of doc.sources) {
                if (sourceObj.value === reel.source) {
                  // Initialize or update rating_score
                  let score = sourceObj.rating_score || 0;
                  if (rating === 'awesome') score += 2;
                  else if (rating === 'ok') score += 1;
                  else if (rating === 'reject') score -= 2;
                  
                  sourceObj.rating_score = score;
                  
                  // Adjust priority string based on score as an example
                  if (score > 10) sourceObj.priority = 'ultra';
                  else if (score > 5) sourceObj.priority = 'high';
                  else if (score < -5) sourceObj.priority = 'low';

                  fs.writeFileSync(filePath, yaml.dump(doc));
                  found = true;
                  break;
                }
              }
            }
          } catch (err) {
            console.error(`Error processing YAML ${file}:`, err);
          }
        }
      }
    }

    return NextResponse.json({ success: true, new_rating: rating });
  } catch (error) {
    console.error('Error updating rating:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
