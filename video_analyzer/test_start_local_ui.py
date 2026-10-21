import unittest
from unittest.mock import patch
import local_upload
import start_local_ui


class CompatibilityEntrypointTests(unittest.TestCase):
    def test_repairs_older_html_template(self):
        old = local_upload.HTML
        try:
            local_upload.HTML = "status.append('\n');"
            with patch('start_local_ui.local_upload.main') as main:
                start_local_ui.main()
            self.assertEqual(local_upload.HTML, "status.append('\\n');")
            main.assert_called_once()
        finally:
            local_upload.HTML = old

    def test_corrected_template_unchanged(self):
        old = local_upload.HTML
        try:
            with patch('start_local_ui.local_upload.main') as main:
                start_local_ui.main()
            self.assertEqual(local_upload.HTML, old)
            main.assert_called_once()
        finally:
            local_upload.HTML = old


if __name__ == '__main__':
    unittest.main()
