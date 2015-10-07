import os
import unittest
import tempfile

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


class OOConfigTests(unittest.TestCase):

    def setUp(self):
        self.tempfiles = []

    def tearDown(self):
        for path in self.tempfiles:
            os.remove(path)

    def write_config(self, config_str):
        """
        Write given config to a temporary file which will be cleaned
        up in teardown.
        Returns full path to the file.
        """
        f, path = tempfile.mkstemp(prefix='ooconfigtests')
        f = open(path, 'w')
        f.write(config_str)
        self.tempfiles.append(path)
        f.close()
        return path

    def test_load_config(self):

        cfg_path = self.write_config(SAMPLE_CONFIG)
        ooconfig = OOConfig(cfg_path)
        print ooconfig

        masters = ooconfig.settings['masters']
        self.assertEquals(1, len(masters))
        self.assertEquals("10.0.0.1", masters[0])

        self.assertEquals(["10.0.0.1", "10.0.2.1", "10.0.2.2"],
            ooconfig.settings['nodes'])
