import os
import unittest
import tempfile
import shutil

from ooinstall.oo_config import OOConfig

SAMPLE_CONFIG = """
Description: This is the configuration file for the OpenShift Ansible-Based Installer.
Name: OpenShift Ansible-Based Installer Configuration
Subscription: {type: none}
Vendor: OpenShift Community
Version: 0.0.1
ansible_config: /tmp/oo-install-ose-20151006-1249/lib/python2.7/site-packages/ooinstall/ansible.cfg
deployment-type: enterprise
masters: [10.0.0.1]
nodes: [10.0.0.1, 10.0.2.1, 10.0.2.2]
validated_facts:
  10.0.0.1: {hostname: private.example.com, ip: 10.0.0.1, public_hostname: public.example.com, public_ip: 192.168.0.1}
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

        self.assertEquals(["10.0.0.1", "10.0.2.1", "10.0.2.2"],
            ooconfig.settings['nodes'])
