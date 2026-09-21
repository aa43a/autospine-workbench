from io import BytesIO
import unittest
from zipfile import ZipFile
from m4_motion_delivery_check import verify_archive


def archive(rows):
    output=BytesIO()
    with ZipFile(output,'w') as result:
        for name,raw in rows:result.writestr(name,raw)
    return output.getvalue()


class DeliveryTests(unittest.TestCase):
    def test_exact_inventory_and_bytes(self):
        files={'skeleton.json':b'{}','image.png':b'original'}
        self.assertEqual(verify_archive(archive(files.items()),files),2)
        for rows in ([('skeleton.json',b'{}')],
                     [('skeleton.json',b'{}'),('image.png',b'changed')],
                     list(files.items())+[('extra',b'')]):
            with self.assertRaises(ValueError):verify_archive(archive(rows),files)

    def test_duplicate_zip_entries_rejected(self):
        with self.assertWarns(UserWarning):
            raw=archive([('a',b'x'),('a',b'x')])
        with self.assertRaisesRegex(ValueError,'inventory'):
            verify_archive(raw,{'a':b'x'})
