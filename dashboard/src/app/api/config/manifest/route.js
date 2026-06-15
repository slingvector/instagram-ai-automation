import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';

export async function POST(request) {
  try {
    const { username, niche, manifestFile = 'hot_content_manifest.yaml' } = await request.json();
    
    if (!username || !niche) {
      return NextResponse.json({ error: 'Username and niche are required' }, { status: 400 });
    }

    const manifestPath = path.join(process.cwd(), '..', 'config', manifestFile);
    
    let doc = { sources: [], creators: {}, global_filters: {} };
    if (fs.existsSync(manifestPath)) {
      const content = fs.readFileSync(manifestPath, 'utf8');
      doc = yaml.load(content) || doc;
    }
    
    // Check if it already exists
    if (!doc.sources) doc.sources = [];
    const exists = doc.sources.find(s => s.value === username && s.niche === niche);
    
    if (exists) {
      return NextResponse.json({ success: true, message: 'Creator already exists in manifest', doc });
    }
    
    // Add new source
    doc.sources.push({
      platform: 'instagram',
      priority: 'high',
      type: 'creator',
      value: username,
      niche: niche,
      rating_score: 0
    });
    
    // Add to creators list
    if (!doc.creators) doc.creators = {};
    if (!doc.creators[niche]) doc.creators[niche] = [];
    if (!doc.creators[niche].includes(username)) {
      doc.creators[niche].push(username);
    }
    
    fs.writeFileSync(manifestPath, yaml.dump(doc));
    
    return NextResponse.json({ success: true, message: 'Creator added to manifest. Preflight scrape pending.', doc });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
