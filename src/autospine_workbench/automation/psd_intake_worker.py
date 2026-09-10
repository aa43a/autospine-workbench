"""Optional PSD extraction subprocess; staging output is not a published project."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_PIXELS = 16_777_216
MAX_LAYERS = 256
MAX_TOTAL_LAYER_PIXELS = 67_108_864


class PsdIntakeError(ValueError):
    def __init__(self, reason_code, message):
        super().__init__(message)
        self.reason_code = reason_code


def inspect_header(source):
    """Reject unsupported or oversized inputs before loading the optional decoder."""
    source = Path(source)
    if not source.is_file() or not 26 <= source.stat().st_size <= MAX_FILE_BYTES:
        raise PsdIntakeError('psd_file_limit', 'PSD file is missing or exceeds 256 MiB')
    with source.open('rb') as stream:
        header = stream.read(26)
    signature, version, reserved, channels, height, width, depth, mode = struct.unpack(
        '>4sH6sHIIHH', header)
    if signature != b'8BPS' or version != 1 or reserved != bytes(6):
        raise PsdIntakeError('invalid_psd_header', 'Expected Photoshop PSD version 1')
    if not 1 <= channels <= 56 or not 1 <= width <= 8192 or not 1 <= height <= 8192 or width * height > MAX_PIXELS:
        raise PsdIntakeError('psd_canvas_limit', 'PSD canvas exceeds supported resource bounds')
    if depth != 8 or mode != 3:
        raise PsdIntakeError('psd_color_mode_unsupported', 'First intake profile supports 8-bit RGB PSD only')
    return width, height


def _inventory(container, depth=0):
    if depth > 16:
        raise PsdIntakeError('psd_layer_limit', 'PSD group nesting exceeds 16')
    for layer in container:
        yield layer, depth
        if layer.is_group():
            yield from _inventory(layer, depth + 1)


def _bounded_layers(psd):
    rows = []
    total = 0
    for layer, depth in _inventory(psd):
        if len(rows) >= MAX_LAYERS:
            raise PsdIntakeError('psd_layer_limit', 'PSD contains more than 256 layer records')
        bbox = tuple(int(v) for v in layer.bbox)
        x1, y1, x2, y2 = bbox
        width, height = x2 - x1, y2 - y1
        if min(width, height) < 0 or max(width, height) > 8192 or width * height > MAX_PIXELS:
            raise PsdIntakeError('psd_layer_limit', 'PSD layer extent exceeds resource bounds')
        if not layer.is_group():
            if str(layer.kind) != 'pixel':
                raise PsdIntakeError('psd_layer_kind_unsupported', 'Rasterize non-pixel layers before importing')
            total += width * height
        if total > MAX_TOTAL_LAYER_PIXELS:
            raise PsdIntakeError('psd_layer_limit', 'Aggregate layer pixels exceed resource bounds')
        rows.append((layer, depth, bbox))
    if not any(not layer.is_group() for layer, _, _ in rows):
        raise PsdIntakeError('psd_no_pixel_layers', 'PSD has no pixel layers')
    return rows


def extract_psd(source, output):
    """Write audit.json last into a NEW directory. Caller owns timeout and promotion.

    Paths in the audit are relative so atomic staging-directory promotion is safe.
    Failed staging directories are never discoverable through a partial audit.json.
    """
    source, output = Path(source).resolve(), Path(output).resolve()
    canvas = inspect_header(source)
    try:
        from psd_tools import PSDImage
        from PIL import Image
    except ImportError as exc:
        raise PsdIntakeError('psd_decoder_unavailable', 'Install optional psd-tools and Pillow in the intake runner') from exc
    if output.exists():
        raise PsdIntakeError('psd_staging_exists', 'Extraction requires a new staging directory')
    try:
        psd = PSDImage.open(source)
        inventory = _bounded_layers(psd)
        if tuple(psd.size) != canvas:
            raise PsdIntakeError('invalid_psd_header', 'Decoded canvas disagrees with header')
        output.mkdir(parents=True)
        (output / 'layers').mkdir()
        composite = psd.composite(force=True)
        if composite is None:
            raise PsdIntakeError('psd_composite_missing', 'PSD composite is unavailable')
        composite.convert('RGBA').save(output / 'composite.png')
        embedded = psd.topil()
        if embedded is not None:
            embedded.convert('RGBA').save(output / 'embedded_composite.png')
        records = []
        pixel_index = 0
        for ordinal, (layer, depth, bbox) in enumerate(inventory):
            x1, y1, x2, y2 = bbox
            record = dict(traversal_index=ordinal, depth=depth, name=str(layer.name),
                          kind=str(layer.kind), is_group=bool(layer.is_group()),
                          visible=bool(layer.is_visible()), opacity=int(layer.opacity),
                          blend_mode=str(layer.blend_mode), bbox=list(bbox),
                          width=x2-x1, height=y2-y1, clipping=bool(layer.clipping))
            if not layer.is_group():
                image = layer.composite(force=True)
                if image is None:
                    image = Image.new('RGBA', (max(1, x2-x1), max(1, y2-y1)))
                image = image.convert('RGBA')
                if image.size != (max(1, x2-x1), max(1, y2-y1)):
                    raise PsdIntakeError('psd_layer_extent_mismatch', 'Rendered layer extent differs from its PSD bbox')
                filename = f'layers/{pixel_index:03d}.png'
                image.save(output / filename)
                from .psd_intake_alpha import alpha_statistics
                record.update(alpha_statistics(image))
                record.update(index=pixel_index, crop_path=filename)
                pixel_index += 1
            records.append(record)
        with source.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        summary = dict(source=source.name, sha256=digest, file_size=source.stat().st_size,
                       canvas=list(canvas), color_mode=str(psd.color_mode), depth=int(psd.depth),
                       channels=int(psd.channels), top_level_layers=len(psd),
                       all_layer_records=len(records), pixel_layers=pixel_index,
                       visible_pixel_layers=sum(r['visible'] for r in records if not r['is_group']),
                       empty_pixel_layers=sum(r.get('empty', False) for r in records),
                       composite_path='composite.png', layers=records,
                       intake_profile='psd-rgb8-v1', authority='none')
        if embedded is not None:
            summary['embedded_composite_path'] = 'embedded_composite.png'
        (output / 'audit.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        return summary
    except PsdIntakeError:
        raise
    except Exception as exc:
        raise PsdIntakeError('psd_extraction_failed', 'PSD decoding or raster extraction failed') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = extract_psd(args.input, args.output)
    except PsdIntakeError as exc:
        print(json.dumps(dict(status='failed', reason_code=exc.reason_code, message=str(exc))))
        return 1
    print(json.dumps(dict(status='succeeded', sha256=report['sha256'], pixel_layers=report['pixel_layers'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
