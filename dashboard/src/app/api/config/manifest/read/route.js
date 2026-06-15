import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET(req) {
  try {
    const { searchParams } = new URL(req.url);
    const filename = searchParams.get('file');
    
    if (!filename || !filename.endsWith('.yaml')) {
      return NextResponse.json({ error: 'Invalid manifest filename' }, { status: 400 });
    }

    const filepath = path.resolve(process.cwd(), '../config', filename);
    
    if (!fs.existsSync(filepath)) {
      return NextResponse.json({ error: 'Manifest not found' }, { status: 404 });
    }

    const content = fs.readFileSync(filepath, 'utf8');
    return NextResponse.json({ content });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
