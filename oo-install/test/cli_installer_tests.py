
import os
import yaml
import ConfigParser

import ooinstall.cli_installer as cli
import ooinstall.install_transactions

from click.testing import CliRunner
from oo_config_tests import OOCliFixture
from mock import patch


DUMMY_MASTER = "master.my.example.com"
DUMMY_NODE = "node1.my.example.com"
DUMMY_SYSTEM_FACTS = {
    '192.168.1.1': {
        'common': {
            'ip': '192.168.1.1',
            'public_ip': '10.0.0.1',
            'hostname': DUMMY_MASTER,
            'public_hostname': DUMMY_MASTER
        }
    },
    '192.168.1.2': {
        'common': {
            'ip': '192.168.1.2',
            'public_ip': '10.0.0.2',
            'hostname': DUMMY_NODE,
            'public_hostname': DUMMY_NODE
        }
    }
}

ASAMPLE_CONFIG = """
deployment-type: enterprise
masters: [192.168.1.1]
nodes: [192.168.1.1, 192.168.1.2]
validated_facts:
  192.168.1.1: {hostname: master.my.example.com, ip: 192.168.1.1, public_hostname: master.my.example.com, public_ip: 10.0.0.1}
  192.168.1.2: {hostname: node1.my.example.com, ip: 192.168.1.2, public_hostname: node1.my.example.com, public_ip: 10.0.0.2}"""

SAMPLE_CONFIG = """
deployment_type: enterprise
hosts:
  - ip: 10.0.0.1
    hostname: master-private.example.com
    public_ip: 24.222.0.1
    public_hostname: master.example.com
    master: true
    node: true
  - ip: 10.0.0.2
    hostname: node1-private.example.com
    public_ip: 24.222.0.2
    public_hostname: node1.example.com
    node: true
  - ip: 10.0.0.3
    hostname: node2-private.example.com
    public_ip: 24.222.0.3
    public_hostname: node2.example.com
    node: true
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
        print result.exception
        self.assertTrue(result.exit_code > 0)
        self.assertTrue("An ansible path must be provided", result.output)

    @patch('ooinstall.install_transactions.run_main_playbook')
    @patch('ooinstall.install_transactions.load_system_facts')
    def test_cfg_full_run(self, load_facts_mock, run_playbook_mock):
        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
        run_playbook_mock.return_value = 0

        config_file = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), SAMPLE_CONFIG)

        self.cli_args.extend(["-c", config_file])
        result = self.runner.invoke(cli.main, self.cli_args)

        load_facts_args = load_facts_mock.call_args[0]
        self.assertEquals(os.path.join(self.work_dir, ".ansible/hosts"), load_facts_args[0])
        self.assertEquals(os.path.join(self.work_dir, "playbooks/byo/openshift_facts.yml"), load_facts_args[1])
        env_vars = load_facts_args[2]
        self.assertEquals(os.path.join(self.work_dir, '.ansible/callback_facts.yaml'),
            env_vars['OO_INSTALL_CALLBACK_FACTS_YAML'])
        self.assertEqual('/tmp/ansible.log', env_vars['ANSIBLE_LOG_PATH'])
        self.assertEquals(0, result.exit_code)

        # Make sure we ran on the expected masters and nodes:
        # TODO: This needs to be addressed, I don't think these call args are permanent:
        self.assertEquals((['10.0.0.1'], ['10.0.0.1', '10.0.0.2', '10.0.0.3'], ['10.0.0.1', '10.0.0.3', '10.0.0.2']),
            run_playbook_mock.call_args[0])

        # Validate the config was written as we would expect at the end:
        f = open(config_file)
        # Raw yaml to keep OOConfig defaults out of the way and see exactly what was written:
        new_config_yaml = yaml.safe_load(f.read())
        f.close()
        # TODO:

    #@patch('ooinstall.install_transactions.run_main_playbook')
    #@patch('ooinstall.install_transactions.load_system_facts')
    #def test_some_hosts_already_installed(self, load_facts_mock, run_playbook_mock):

    #    # Add a fact that indicates one of our hosts is already installed.
    #    DUMMY_SYSTEM_FACTS['192.168.1.1']['common']['deployment_type'] = 'enterprise'

    #    load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
    #    run_playbook_mock.return_value = 0

    #    config_file = self.write_config(os.path.join(self.work_dir,
    #        'ooinstall.conf'), SAMPLE_CONFIG)

    #    self.cli_args.extend(["-c", config_file])
    #    result = self.runner.invoke(cli.main, self.cli_args)

    #    print result.exception
    #    self.assertEquals(0, result.exit_code)

    #    # Run playbook should only try to install on the *new* node:
    #    self.assertEquals(([], ['192.168.1.2']),
    #        run_playbook_mock.call_args[0])

    @patch('ooinstall.install_transactions.run_main_playbook')
    @patch('ooinstall.install_transactions.load_system_facts')
    def test_inventory_write(self, load_facts_mock, run_playbook_mock):

        # Add an ssh user so we can verify it makes it to the inventory file:
        merged_config = "%s\n%s" % (SAMPLE_CONFIG, "ansible_ssh_user: bob")
        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
        run_playbook_mock.return_value = 0

        config_file = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), merged_config)

        self.cli_args.extend(["-c", config_file])
        self.runner.invoke(cli.main, self.cli_args)

        # Check the inventory file looks as we would expect:
        inventory = ConfigParser.ConfigParser(allow_no_value=True)
        inventory.read(os.path.join(self.work_dir, '.ansible/hosts'))
        self.assertEquals('bob', inventory.get('OSEv3:vars', 'ansible_ssh_user'))
        self.assertEquals('openshift', inventory.get('OSEv3:vars', 'product_type'))


