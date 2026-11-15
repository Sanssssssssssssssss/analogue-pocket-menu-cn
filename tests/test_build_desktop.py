# SPDX-License-Identifier: MIT
"""Publication gates must apply to inherited previews as well as new candidates."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import additional_menus
import assistant_workflow
import build_desktop
import delivery
from test_additional_menus import package, put


class DesktopPublication(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.preview = self.base/'preview'
        self.registry = self.base/'registry.json'
        delivery.write(self.registry, {})
        self.registry_patch = patch.object(additional_menus, 'REGISTRY', self.registry)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)

    def manifest(self):
        rows = sorted((delivery.sha(p), p.relative_to(self.preview).as_posix())
                      for p in (self.preview/'packages').rglob('*') if p.is_file())
        (self.preview/'SHA256SUMS.txt').write_text(''.join(f'{h}  {p}\n' for h, p in rows))

    def test_unregistered_inherited_research_core_is_refused_before_build(self):
        package(self.preview/'packages/POKEMINI', 'POKEMINI')
        self.manifest()
        with self.assertRaisesRegex(ValueError, 'reviewed build receipt'):
            build_desktop.build(self.preview, self.base/'out')
        self.assertFalse((self.base/'out').exists())

    def test_inherited_private_payload_is_not_accepted_from_its_self_manifest(self):
        candidate = self.preview/'packages/ATARI2600'
        digest, record = package(candidate, 'ATARI2600')
        delivery.write(self.registry, {'ATARI2600': {digest: record}})
        put(candidate/'private.sav', b'private fixture, never distribute')
        self.manifest()
        with self.assertRaisesRegex(ValueError, 'unreviewed or missing files'):
            build_desktop.build(self.preview, self.base/'out')
        self.assertFalse((self.base/'out').exists())
        self.assertNotIn('private.sav', build_desktop.reviewed_files(candidate, 'ATARI2600'))

    def test_assistant_does_not_enable_an_unreviewed_package_directory(self):
        card = self.base/'card'
        put(card/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        package(self.preview/'packages/POKEMINI', 'POKEMINI')
        workflow = assistant_workflow.Workflow(self.preview/'packages', self.base/'work')
        with patch.object(assistant_workflow.build_menus, 'discover', return_value={'POKEMINI':['fixture.min']}), \
             patch.object(assistant_workflow.compatibility, 'scan', return_value={}):
            found = workflow.inspect(card)
        self.assertFalse(found['packages']['POKEMINI'])
        self.assertIn('reviewed build receipt', found['package_errors']['POKEMINI'])


if __name__ == '__main__':
    unittest.main()
