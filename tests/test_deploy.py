import unittest
from scripts.deploy_host import add_route, ROUTE


class DeploymentTests(unittest.TestCase):
    def test_preserves_existing_configuration_exactly(self):
        original = '''saltvaultvideo.com {
    handle /jelly-cli {
        root * /var/www/jelly-cli
        rewrite * /install.sh
        header Content-Type "text/plain; charset=utf-8"
        file_server
    }
    handle {
        reverse_proxy 192.168.0.11:8096
    }
}
other.example.com {
    reverse_proxy localhost:8080
}
'''
        modified = add_route(original)
        self.assertEqual(modified.replace(ROUTE, '', 1), original)
        self.assertEqual(add_route(modified), modified)

    def test_unexpected_config_is_rejected(self):
        for original in ('other.example.com {}', '    handle /jelly-cli {\n    handle /jelly-cli {', '/jelly-cli/releases exists'):
            with self.assertRaises(RuntimeError):
                add_route(original)
