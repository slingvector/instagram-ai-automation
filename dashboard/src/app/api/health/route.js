import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import fs from 'fs';

const execAsync = promisify(exec);

export async function GET() {
  const health = {
    adb: 'error',
    firebase: 'error',
    manifest: 'error'
  };

  try {
    // Check ADB Connection
    const { stdout } = await execAsync('adb devices');
    if (stdout.includes('\tdevice')) {
      health.adb = 'online';
    } else {
      health.adb = 'offline';
    }
  } catch (e) {
    health.adb = 'error';
  }

  try {
    // Check Firebase Key
    const keyPath = path.resolve(process.cwd(), '../modernos-edge-agent-key.json');
    if (fs.existsSync(keyPath)) {
      health.firebase = 'online';
    } else {
      health.firebase = 'offline';
    }
  } catch (e) {
    health.firebase = 'error';
  }

  try {
    // Check Manifests config directory
    const configPath = path.resolve(process.cwd(), '../config');
    if (fs.existsSync(configPath)) {
      health.manifest = 'online';
    } else {
      health.manifest = 'offline';
    }
  } catch (e) {
    health.manifest = 'error';
  }

  return NextResponse.json(health);
}
