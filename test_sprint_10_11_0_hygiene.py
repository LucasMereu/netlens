import os
import unittest

class TestSprint10110Hygiene(unittest.TestCase):
    """
    Test suite for Sprint 10.11.0 Technical Debt & Security Hygiene.
    Verifies zero hardcoded credentials in source files,
    no ephemeral agent paths in routes, and absence of cookies file.
    """

    def setUp(self):
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.app_dir = os.path.join(self.project_root, 'app')
        self.templates_dir = os.path.join(self.project_root, 'templates')

    def test_1_zero_hardcoded_credentials_in_source(self):
        """Test 1: Verify zero hardcoded production credentials in source code and templates."""
        forbidden_patterns = [
            '1720sysApk',
            '0123456789abcdef',
            'b4572701e8599',
            'Mat26luc11',
            'rtvzabbix'
        ]

        violations = []

        # 1. Scan app/ directory (.py files)
        for root, _, files in os.walk(self.app_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        for pattern in forbidden_patterns:
                            if pattern in content:
                                violations.append(f'Found credential pattern "{pattern}" in {file_path}')

        # 2. Scan templates/index.html
        index_html_path = os.path.join(self.templates_dir, 'index.html')
        if os.path.exists(index_html_path):
            with open(index_html_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for pattern in forbidden_patterns:
                    if pattern in content:
                        violations.append(f'Found credential pattern "{pattern}" in {index_html_path}')

        # 3. Scan vlan_replicator.py if exists
        vlan_rep_path = os.path.join(self.project_root, 'vlan_replicator.py')
        if os.path.exists(vlan_rep_path):
            with open(vlan_rep_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for pattern in forbidden_patterns:
                    if pattern in content:
                        violations.append(f'Found credential pattern "{pattern}" in {vlan_rep_path}')

        self.assertEqual(len(violations), 0, f'Credentials found in source: {violations}')

    def test_2_no_ephemeral_brain_paths_in_routes(self):
        """Test 2: Verify no ephemeral brain paths (.gemini/antigravity/brain/) in app/routes."""
        ephemeral_pattern = '.gemini/antigravity/brain'
        routes_dir = os.path.join(self.app_dir, 'routes')
        violations = []

        for root, _, files in os.walk(routes_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if ephemeral_pattern in content:
                            violations.append(f'Found ephemeral brain path in {file_path}')

        self.assertEqual(len(violations), 0, f'Ephemeral paths found in routes: {violations}')

    def test_3_cookies_file_absent(self):
        """Test 3: Verify cookies.txt does NOT exist in project root."""
        cookies_path = os.path.join(self.project_root, 'cookies.txt')
        self.assertFalse(os.path.exists(cookies_path), 'cookies.txt must not exist in repository root')

if __name__ == '__main__':
    unittest.main()
