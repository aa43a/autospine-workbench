"""A torso-driven waist is eligible only with exact reviewed chest support."""


def require_chest_torso(document, ledger):
    bones = [bone['name'] for bone in document['bones']]
    if 'chest' not in bones:
        raise ValueError('skirt_chest_reference_missing')
    chest = bones.index('chest')
    for row in ledger.values():
        if row['name'] not in ('topwear', 'topwear-front') or row['state'] != 'rigid_reviewed':
            continue
        for region in row['regions']:
            slot = region['region_id']
            attachment = document['skins'][0]['attachments'][slot][slot]
            vertices = attachment['vertices']
            # Only exact single-bone weighted attachments have the same material driver.
            if len(vertices) != len(attachment['uvs'])//2*5:
                raise ValueError('skirt_torso_driver_unsupported')
            for i in range(0, len(vertices), 5):
                count, index, _, _, weight = vertices[i:i+5]
                if count != 1 or index != chest or weight != 1:
                    raise ValueError('skirt_torso_driver_unsupported')
