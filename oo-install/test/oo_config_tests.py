import os
import unittest
import tempfile
import shutil

from ooinstall.oo_config import OOConfig

SAMPLE_CONFIG = """
deployment-type: enterprise
masters: [10.0.0.1]
nodes: [10.0.0.1, 10.0.0.2, 10.0.0.3]
validated_facts:
  10.0.0.1: {hostname: private.example.com, ip: 10.0.0.1, public_hostname: public.example.com, public_ip: 192.168.0.1}
"""

CONFIG_COMPLETE_FACTS = """
masters: [10.0.0.1]
nodes: [10.0.0.1, 10.0.0.2, 10.0.0.3]
validated_facts:
  10.0.0.1: {hostname: master.example.com, ip: 10.0.0.1, public_hostname: master.example.com, public_ip: 192.168.0.1}
  10.0.0.2: {hostname: node1.example.com, ip: 10.0.0.2, public_hostname: node1.example.com, public_ip: 192.168.0.2}
  10.0.0.3: {hostname: node2.example.com, ip: 10.0.0.3, public_hostname: node2.example.com, public_ip: 192.168.0.3}
"""

CONFIG_INCOMPLETE_FACTS = """
masters: [10.0.0.1]
nodes: [10.0.0.1, 10.0.0.2, 10.0.0.3]
validated_facts:
  10.0.0.1: {hostname: master.example.com, ip: 10.0.0.1, public_hostname: master.example.com, public_ip: 192.168.0.1}
  10.0.0.2: {hostname: node1.example.com, ip: 10.0.0.2}
"""


class OOCliFixture(unittest.TestCase):

    def setUp(self):
        self.tempfiles = []
        self.work_dir = tempfile.mkdtemp(prefix='ooconfigtests')
        self.tempfiles.append(self.work_dir)

    def tearDown(self):
        for path in self.tempfiles:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    def write_config(self, path, config_str):
        """
        Write given config to a temporary file which will be cleaned
        up in teardown.
        Returns full path to the file.
        """
        f = open(path, 'w')
        f.write(config_str)
        f.close()
        return path


class OOConfigTests(OOCliFixture):

    def test_load_config(self):

        cfg_path = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), SAMPLE_CONFIG)
        ooconfig = OOConfig(cfg_path)

        masters = ooconfig.settings['masters']
        self.assertEquals(1, len(masters))
        self.assertEquals("10.0.0.1", masters[0])

        self.assertEquals(["10.0.0.1", "10.0.0.2", "10.0.0.3"],
            ooconfig.settings['nodes'])

    def test_load_complete_validated_facts(self):
        cfg_path = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), CONFIG_COMPLETE_FACTS)
        ooconfig = OOConfig(cfg_path)
        missing_host_facts = ooconfig.calc_missing_facts()
        self.assertEquals(0, len(missing_host_facts))

    def test_load_incomplete_validated_facts(self):
        cfg_path = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), CONFIG_INCOMPLETE_FACTS)
        ooconfig = OOConfig(cfg_path)
        missing_host_facts = ooconfig.calc_missing_facts()
        self.assertEquals(2, len(missing_host_facts))
        self.assertEquals(2, len(missing_host_facts['10.0.0.2']))
        self.assertEquals(4, len(missing_host_facts['10.0.0.3']))

