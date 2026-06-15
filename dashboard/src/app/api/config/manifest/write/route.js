import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function POST(req) {
  try {
    const { filename, content } = await req.json();
    
    if (!filename || !filename.endsWith('.yaml')) {
      return NextResponse.json({ error: 'Invalid manifest filename' }, { status: 400 });
    }

    const filepath = path.resolve(process.cwd(), '../config', filename);
    
    fs.writeFileSync(filepath, content, 'utf8');
    return NextResponse.json({ success: true, message: 'Manifest saved successfully' });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
