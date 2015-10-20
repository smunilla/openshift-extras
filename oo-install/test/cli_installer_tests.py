
import os
import ConfigParser
import yaml

import ooinstall.cli_installer as cli

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

# Substitute in a product name before use:
SAMPLE_CONFIG = """
variant: %s
ansible_ssh_user: root
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

    def assert_result(self, result, exit_code):
        if result.exception is not None or result.exit_code != exit_code:
            print("Unexpected result from CLI execution")
            print("Exit code: %s" % result.exit_code)
            print("Exception: %s" % result.exception)
            print result.exc_info
            import traceback
            traceback.print_exception(*result.exc_info)
            print("Output:\n%s" % result.output)
            self.assertTrue("Exception during CLI execution", False)

    def test_ansible_path_required(self):
        result = self.runner.invoke(cli.main, [])
        self.assert_result(result, 1)
        self.assertTrue("An ansible path must be provided" in result.output)

    @patch('ooinstall.install_transactions.run_main_playbook')
    @patch('ooinstall.install_transactions.load_system_facts')
    def test_cfg_full_run(self, load_facts_mock, run_playbook_mock):
        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
        run_playbook_mock.return_value = 0

        config_file = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), SAMPLE_CONFIG % 'openshift-enterprise')

        self.cli_args.extend(["-c", config_file])
        result = self.runner.invoke(cli.main, self.cli_args)
        self.assert_result(result, 0)

        load_facts_args = load_facts_mock.call_args[0]
        self.assertEquals(os.path.join(self.work_dir, ".ansible/hosts"),
            load_facts_args[0])
        self.assertEquals(os.path.join(self.work_dir,
            "playbooks/byo/openshift_facts.yml"), load_facts_args[1])
        env_vars = load_facts_args[2]
        self.assertEquals(os.path.join(self.work_dir,
            '.ansible/callback_facts.yaml'),
            env_vars['OO_INSTALL_CALLBACK_FACTS_YAML'])
        self.assertEqual('/tmp/ansible.log', env_vars['ANSIBLE_LOG_PATH'])

        # Make sure we ran on the expected masters and nodes:
        hosts = run_playbook_mock.call_args[0][0]
        hosts_to_run_on = run_playbook_mock.call_args[0][1]
        self.assertEquals(3, len(hosts))
        self.assertEquals(3, len(hosts_to_run_on))

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
        merged_config = "%s\n%s" % (SAMPLE_CONFIG % 'openshift-enterprise',
            "ansible_ssh_user: bob")
        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
        run_playbook_mock.return_value = 0

        config_file = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), merged_config)

        self.cli_args.extend(["-c", config_file])
        result = self.runner.invoke(cli.main, self.cli_args)
        self.assert_result(result, 0)

        # Check the inventory file looks as we would expect:
        inventory = ConfigParser.ConfigParser(allow_no_value=True)
        inventory.read(os.path.join(self.work_dir, '.ansible/hosts'))
        self.assertEquals('bob',
            inventory.get('OSEv3:vars', 'ansible_ssh_user'))
        self.assertEquals('openshift-enterprise',
            inventory.get('OSEv3:vars', 'deployment_type'))
        self.assertEquals('openshift',
            inventory.get('OSEv3:vars', 'product_type'))

    def _read_yaml(self, config_file_path):
        f = open(config_file_path, 'r')
        config = yaml.safe_load(f.read())
        f.close()
        return config

    @patch('ooinstall.install_transactions.run_main_playbook')
    @patch('ooinstall.install_transactions.load_system_facts')
    def test_variant_version_latest_assumed(self, load_facts_mock,
        run_playbook_mock):
        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
        run_playbook_mock.return_value = 0

        config_file = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), SAMPLE_CONFIG % 'openshift-enterprise')

        self.cli_args.extend(["-c", config_file])
        result = self.runner.invoke(cli.main, self.cli_args)
        self.assert_result(result, 0)

        written_config = self._read_yaml(config_file)

        self.assertEquals('openshift-enterprise', written_config['variant'])
        # We didn't specify a version so the latest should have been assumed,
        # and written to disk:
        self.assertEquals('3.1', written_config['variant_version'])

        # Make sure the correct value was passed to ansible:
        inventory = ConfigParser.ConfigParser(allow_no_value=True)
        inventory.read(os.path.join(self.work_dir, '.ansible/hosts'))
        self.assertEquals('openshift-enterprise',
            inventory.get('OSEv3:vars', 'deployment_type'))

    @patch('ooinstall.install_transactions.run_main_playbook')
    @patch('ooinstall.install_transactions.load_system_facts')
    def test_variant_version_preserved(self, load_facts_mock,
        run_playbook_mock):
        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
        run_playbook_mock.return_value = 0

        config = SAMPLE_CONFIG % 'openshift-enterprise'
        config = '%s\n%s' % (config, 'variant_version: 3.0')
        config_file = self.write_config(os.path.join(self.work_dir,
            'ooinstall.conf'), config)

        self.cli_args.extend(["-c", config_file])
        result = self.runner.invoke(cli.main, self.cli_args)
        self.assert_result(result, 0)

        written_config = self._read_yaml(config_file)

        self.assertEquals('openshift-enterprise', written_config['variant'])
        # Make sure our older version was preserved:
        # and written to disk:
        self.assertEquals('3.0', written_config['variant_version'])

        inventory = ConfigParser.ConfigParser(allow_no_value=True)
        inventory.read(os.path.join(self.work_dir, '.ansible/hosts'))
        self.assertEquals('enterprise',
            inventory.get('OSEv3:vars', 'deployment_type'))
