import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_model_review import ROOT, build, verify


class ModelReviewEvidenceTests(unittest.TestCase):
    def test_committed_review_regrades_and_archives_exactly(self):
        manifest = verify(ROOT/'docs/model-review')
        self.assertIn('review.json', manifest['files'])
        data = json.loads((ROOT/'docs/model-review/review.json').read_text())
        self.assertEqual(len(data['episodes']), 3)
        self.assertTrue(all(set(item['reviews']) == {'images-only', 'with-record'}
                            for item in data['episodes']))
        for episode in data['episodes']:
            for selected in episode['reviews'].values():
                self.assertEqual(selected['review']['explanation_status'], 'not_assessed')

    def test_build_keeps_existing_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)/'existing'
            destination.mkdir()
            original = destination/'keep.txt'
            original.write_text('keep')
            with self.assertRaises(ValueError):
                build(destination)
            self.assertEqual(original.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
