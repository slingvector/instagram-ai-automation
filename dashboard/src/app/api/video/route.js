import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const gcsUri = searchParams.get('gcs_uri');
    
    if (!gcsUri) {
      return new Response('gcs_uri is required', { status: 400 });
    }
    
    // Extract the filename from gs://.../reels/filename.mp4
    const filename = path.basename(gcsUri);
    // Resolve to the local download folder in the workspace
    const filePath = path.join(process.cwd(), '../data/downloads', filename);
    
    if (!fs.existsSync(filePath)) {
      console.warn(`Local video file not found for ${gcsUri} at ${filePath}`);
      return new Response('Video not found locally', { status: 404 });
    }
    
    const stat = fs.statSync(filePath);
    const fileSize = stat.size;
    const range = request.headers.get('range');
    
    if (range) {
      const parts = range.replace(/bytes=/, "").split("-");
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
      
      const chunksize = (end - start) + 1;
      const fileStream = fs.createReadStream(filePath, { start, end });
      
      return new Response(fileStream, {
        status: 206,
        headers: {
          'Content-Range': `bytes ${start}-${end}/${fileSize}`,
          'Accept-Ranges': 'bytes',
          'Content-Length': chunksize.toString(),
          'Content-Type': 'video/mp4',
        },
      });
    } else {
      const fileStream = fs.createReadStream(filePath);
      return new Response(fileStream, {
        headers: {
          'Content-Length': fileSize.toString(),
          'Content-Type': 'video/mp4',
        },
      });
    }
  } catch (error) {
    console.error('Error serving local video:', error);
    return new Response(error.message, { status: 500 });
  }
}
