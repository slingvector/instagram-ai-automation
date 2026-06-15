import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';

const PROMPTS_FILE = path.join(process.cwd(), '..', 'config', 'ai_prompts.yaml');

export async function GET() {
  try {
    if (fs.existsSync(PROMPTS_FILE)) {
      const content = fs.readFileSync(PROMPTS_FILE, 'utf8');
      const doc = yaml.load(content) || {};
      return NextResponse.json({ prompts: doc });
    }
    return NextResponse.json({ prompts: {} });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

export async function POST(request) {
  try {
    const { key, prompt } = await request.json();
    let doc = {};
    if (fs.existsSync(PROMPTS_FILE)) {
      const content = fs.readFileSync(PROMPTS_FILE, 'utf8');
      doc = yaml.load(content) || {};
    }
    
    doc[key] = prompt;
    
    fs.writeFileSync(PROMPTS_FILE, yaml.dump(doc));
    
    return NextResponse.json({ success: true, prompts: doc });
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
