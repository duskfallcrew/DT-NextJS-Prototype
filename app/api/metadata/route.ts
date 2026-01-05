import { NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs/promises';
import mime from 'mime-types';
import exifParser from 'exif-parser';

// PNG chunk parser for AI generation parameters
function parsePNGChunks(buffer: Buffer): Record<string, any> {
  const chunks: Record<string, any> = {};

  // Check PNG signature
  if (buffer.length < 8 || buffer.toString('hex', 0, 8) !== '89504e470d0a1a0a') {
    return chunks;
  }

  let offset = 8; // Skip PNG signature

  while (offset < buffer.length) {
    if (offset + 8 > buffer.length) break;

    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString('ascii', offset + 4, offset + 8);

    if (offset + 12 + length > buffer.length) break;

    const data = buffer.slice(offset + 8, offset + 8 + length);

    // Parse text chunks
    if (type === 'tEXt') {
      const nullIndex = data.indexOf(0);
      if (nullIndex !== -1) {
        const key = data.toString('latin1', 0, nullIndex);
        const value = data.toString('utf8', nullIndex + 1);
        chunks[key] = value;
      }
    } else if (type === 'iTXt') {
      const nullIndex = data.indexOf(0);
      if (nullIndex !== -1) {
        const key = data.toString('latin1', 0, nullIndex);
        // Skip compression flag, compression method, language tag, translated keyword
        let textStart = nullIndex + 1;
        const compressionFlag = data[textStart++];
        const compressionMethod = data[textStart++];

        // Skip language tag (null-terminated)
        while (textStart < data.length && data[textStart] !== 0) textStart++;
        textStart++; // Skip null

        // Skip translated keyword (null-terminated)
        while (textStart < data.length && data[textStart] !== 0) textStart++;
        textStart++; // Skip null

        const value = data.toString('utf8', textStart);
        chunks[key] = value;
      }
    }

    offset += 12 + length; // length + type + data + CRC
  }

  return chunks;
}

// Parse AI generation parameters from various formats
function parseAIMetadata(chunks: Record<string, any>): Record<string, any> {
  const aiData: Record<string, any> = {};

  // A1111/Forge format - stored in "parameters" key
  if (chunks.parameters) {
    const params = chunks.parameters;

    // Extract positive prompt (everything before "Negative prompt:")
    const negativeMatch = params.match(/Negative prompt:\s*(.+?)(?:\n|$)/s);
    const splitIndex = params.indexOf('\nNegative prompt:');

    if (splitIndex !== -1) {
      aiData.prompt = params.substring(0, splitIndex).trim();
      if (negativeMatch) {
        aiData.negative_prompt = negativeMatch[1].split('\n')[0].trim();
      }
    } else {
      // No negative prompt found, everything is the positive prompt
      const lines = params.split('\n');
      aiData.prompt = lines[0].trim();
    }

    // Extract generation settings (last line typically)
    const lines = params.split('\n');
    const settingsLine = lines[lines.length - 1];

    // Parse common parameters
    const stepMatch = settingsLine.match(/Steps:\s*(\d+)/);
    const samplerMatch = settingsLine.match(/Sampler:\s*([^,]+)/);
    const cfgMatch = settingsLine.match(/CFG scale:\s*([\d.]+)/);
    const seedMatch = settingsLine.match(/Seed:\s*(\d+)/);
    const sizeMatch = settingsLine.match(/Size:\s*(\d+x\d+)/);
    const modelMatch = settingsLine.match(/Model:\s*([^,]+)/);

    if (stepMatch) aiData.steps = stepMatch[1];
    if (samplerMatch) aiData.sampler = samplerMatch[1].trim();
    if (cfgMatch) aiData.cfg_scale = cfgMatch[1];
    if (seedMatch) aiData.seed = seedMatch[1];
    if (sizeMatch) aiData.size = sizeMatch[1];
    if (modelMatch) aiData.model = modelMatch[1].trim();
  }

  // ComfyUI format - stored in "prompt" key (JSON workflow)
  if (chunks.prompt) {
    try {
      const workflow = JSON.parse(chunks.prompt);
      aiData.comfyui_workflow = workflow;
      aiData.workflow_type = 'ComfyUI';
    } catch (e) {
      // Not valid JSON, store as-is
      aiData.prompt = chunks.prompt;
    }
  }

  // NovelAI format - stored in "Comment" or "Description" key
  if (chunks.Comment || chunks.Description) {
    try {
      const novelData = JSON.parse(chunks.Comment || chunks.Description);
      if (novelData.prompt) aiData.prompt = novelData.prompt;
      if (novelData.uc) aiData.negative_prompt = novelData.uc;
      if (novelData.steps) aiData.steps = novelData.steps;
      if (novelData.scale) aiData.cfg_scale = novelData.scale;
      if (novelData.seed) aiData.seed = novelData.seed;
      if (novelData.sampler) aiData.sampler = novelData.sampler;
    } catch (e) {
      // Not valid JSON
    }
  }

  return aiData;
}

// Parse Civitai JPEG metadata from EXIF UserComment
function parseCivitaiJPEG(buffer: Buffer): string | null {
  try {
    // Look for APP1 marker (EXIF)
    let offset = 2; // Skip JPEG signature

    while (offset < buffer.length - 1) {
      if (buffer[offset] === 0xFF && buffer[offset + 1] === 0xE1) {
        // Found APP1
        const length = (buffer[offset + 2] << 8) | buffer[offset + 3];
        const exifData = buffer.slice(offset + 4, offset + 2 + length);

        // Look for "UNICODE" prefix (Civitai's UserComment format)
        const unicodeIndex = exifData.indexOf('UNICODE');
        if (unicodeIndex !== -1) {
          // Skip UNICODE\x00\x00 prefix (8 bytes)
          let commentStart = unicodeIndex + 8;
          let commentBytes = exifData.slice(commentStart);

          // Strip null bytes (Civitai stores as UTF-16-LE with nulls between chars)
          const strippedBytes = Buffer.from(commentBytes.filter(b => b !== 0));
          const comment = strippedBytes.toString('utf8');

          // Return if it looks like valid metadata (has "Steps:" for A1111 or "{" for ComfyUI)
          if (comment.includes('Steps:') || comment.trim().startsWith('{')) {
            return comment;
          }
        }
        break;
      }
      offset++;
    }
  } catch (e) {
    // Failed to parse, return null
  }

  return null;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const filePath = searchParams.get('path');

  if (!filePath) {
    return NextResponse.json({ error: 'File path is required' }, { status: 400 });
  }

  // Basic security check to prevent directory traversal
  const resolvedPath = path.resolve(filePath);
   if (!resolvedPath.startsWith(path.resolve('.'))) {
    return NextResponse.json({ error: 'Access denied' }, { status: 403 });
  }

  try {
    const file = await fs.readFile(resolvedPath);
    const stats = await fs.stat(resolvedPath);
    const mimeType = mime.lookup(resolvedPath) || 'application/octet-stream';

    let exifData = {};
    let iptcData = {};

    // Try to parse EXIF data (only works for JPEG/TIFF)
    try {
      const parser = exifParser.create(file);
      const result = parser.parse();
      exifData = result.tags || {};
      iptcData = result.iptc || {};
    } catch (e) {
      // EXIF parsing failed, that's ok for PNGs
    }

    // Parse PNG chunks for AI metadata
    let aiData = {};
    if (mimeType === 'image/png') {
      const chunks = parsePNGChunks(file);
      aiData = parseAIMetadata(chunks);
    } else if (mimeType === 'image/jpeg') {
      // Parse Civitai JPEG metadata from EXIF UserComment
      const civitaiMetadata = parseCivitaiJPEG(file);
      if (civitaiMetadata) {
        aiData = parseAIMetadata({ parameters: civitaiMetadata });
      }
    }

    const metadata = {
      fileName: path.basename(resolvedPath),
      fileSize: stats.size,
      fileType: mimeType,
      lastModified: stats.mtime.toISOString(),
      exif: exifData,
      iptc: iptcData,
      xmp: {}, // exif-parser does not handle xmp
      ai: aiData,
    };

    return NextResponse.json(metadata);
  } catch (error) {
    console.error('Metadata extraction error:', error);
    if (error instanceof Error) {
      if ('code' in error && error.code === 'ENOENT') {
        return NextResponse.json({ error: 'File not found' }, { status: 404 });
      }
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    return NextResponse.json({ error: 'An unknown error occurred' }, { status: 500 });
  }
}
