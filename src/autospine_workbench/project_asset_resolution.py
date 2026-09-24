"""Allow-listed image resolution against one request-local audit observation."""
from pathlib import Path
from .project_errors import AssetNotFoundError

IMAGE_SUFFIXES=frozenset({'.png','.jpg','.jpeg','.webp'})


def resolve(record, project_id, asset, layer_id, assigned_layers):
    if asset=='composite':
        filename=Path(str(record.audit.get('composite_path','composite.png'))).name
        candidate=record.audit_dir/filename
    elif asset in {'embedded-composite','embedded_composite'}:
        filename=Path(str(record.audit.get('embedded_composite_path','embedded_composite.png'))).name
        candidate=record.audit_dir/filename
    elif asset in {'contact-sheet','contact_sheet'}:
        filename=Path(str(record.audit.get('layers_contact_sheet_path','layers_contact_sheet.png'))).name
        candidate=record.audit_dir/filename
    elif asset=='layer':
        if not layer_id:raise AssetNotFoundError(project_id,'layer')
        match=next((raw for _,raw,assigned in assigned_layers(record.audit.get('layers')) if assigned==layer_id),None)
        if match is None:raise AssetNotFoundError(project_id,f'layer:{layer_id}')
        candidate=record.audit_dir/'layers'/Path(str(match.get('crop_path',''))).name
    else:raise AssetNotFoundError(project_id,asset)
    try:
        root=record.audit_dir.resolve(strict=True)
        resolved=candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError,ValueError) as exc:raise AssetNotFoundError(project_id,asset) from exc
    if not resolved.is_file() or resolved.suffix.lower() not in IMAGE_SUFFIXES:
        raise AssetNotFoundError(project_id,asset)
    return resolved


def layers(store,project_id,layer_ids):
    """Keep compatibility with minimal stores; no paths or bytes are cached."""
    batch=getattr(store,'resolve_layer_assets',None)
    if callable(batch):return batch(project_id,layer_ids)
    return {key:Path(store.resolve_asset(project_id,'layer',key)) for key in layer_ids}
