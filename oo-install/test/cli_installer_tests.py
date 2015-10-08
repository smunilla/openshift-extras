
import os
import unittest
import tempfile

import ooinstall.cli_installer as cli
import ooinstall.install_transactions

from click.testing import CliRunner
from oo_config_tests import OOCliFixture
from mock import patch


DUMMY_MASTER = "master.my.example.com"
DUMMY_NODE = "node1.my.example.com"
DUMMY_SYSTEM_FACTS = {
    DUMMY_MASTER: {
        "common": {
            'ip': '192.168.1.1',
            'public_ip': '10.0.0.1',
            'hostname': DUMMY_MASTER,
            'public_hostname': DUMMY_MASTER
        }
    },
    DUMMY_NODE: {
        "common": {
            'ip': '192.168.1.2',
            'public_ip': '10.0.0.2',
            'hostname': DUMMY_NODE,
            'public_hostname': DUMMY_NODE
        }
    }
}

SAMPLE_CONFIG = """
Description: This is the configuration file for the OpenShift Ansible-Based Installer.
Name: OpenShift Ansible-Based Installer Configuration
Subscription: {type: none}
Vendor: OpenShift Community
Version: 0.0.1
deployment-type: enterprise
masters: [192.168.1.1]
nodes: [192.168.1.1, 192.168.1.2]
validated_facts:
  192.168.1.1: {hostname: master.my.example.com, ip: 192.168.1.1, public_hostname: master.my.example.com, public_ip: 10.0.0.1}
  192.168.1.2: {hostname: node1.my.example.com, ip: 192.168.1.2, public_hostname: node1.my.example.com, public_ip: 10.0.0.2}
"""

class UnattendedCliTests(OOCliFixture):

    def setUp(self):
        OOCliFixture.setUp(self)
        self.runner = CliRunner()

        # Add any arguments you would like to test here, the defaults ensure
        # we only do unattended invocations here, and using temporary files/dirs.
        self.cli_args = ["-u", "-a", self.work_dir]

    def run_cli(self):
        return self.runner.invoke(cli.main, self.cli_args)

    def test_ansible_path_required(self):
        result = self.runner.invoke(cli.main, [])
        self.assertTrue(result.exit_code > 0)
        self.assertTrue("An ansible path must be provided", result.output)

    @patch('ooinstall.install_transactions.load_system_facts')
    def test_no_cfg_full_run(self, load_facts_mock):
        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)

        config_file = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), SAMPLE_CONFIG)

        self.cli_args.extend(["-c", config_file])
        result = self.runner.invoke(cli.main, self.cli_args)

        load_facts_args = load_facts_mock.call_args[0]
        # TODO: get the first clal argument
        self.assertEquals(os.path.join(self.work_dir, "playbooks/byo/openshift_facts.yml"), load_facts_args[1])
        env_vars = load_facts_args[2]
        # TODO: Fix these
        self.assertEquals(os.path.join(self.work_dir, '.ansible/callback_facts.yaml'),
            env_vars['OO_INSTALL_CALLBACK_FACTS_YAML'])
        self.assertEquals('/home/dgoodwin/src/openshift-extras/oo-install/src/ooinstall/ansible_plugins',
            env_vars['ANSIBLE_CALLBACK_PLUGINS'])
        self.assertEqual('/tmp/ansible.log', env_vars['ANSIBLE_LOG_PATH'])




