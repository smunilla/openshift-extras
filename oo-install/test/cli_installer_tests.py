
import os
import ConfigParser
import yaml

import ooinstall.cli_installer as cli

from click.testing import CliRunner
from oo_config_tests import OOInstallFixture
from mock import patch


DUMMY_SYSTEM_FACTS = {
    '10.0.0.1': {
        'common': {
            'ip': '10.0.0.1',
            'public_ip': '10.0.0.1',
            'hostname': 'master-private.example.com',
            'public_hostname': 'master.example.com'
        }
    },
    '10.0.0.2': {
        'common': {
            'ip': '10.0.0.2',
            'public_ip': '10.0.0.2',
            'hostname': 'node1-private.example.com',
            'public_hostname': 'node1.example.com'
        }
    },
    '10.0.0.3': {
        'common': {
            'ip': '10.0.0.3',
            'public_ip': '10.0.0.3',
            'hostname': 'node2-private.example.com',
            'public_hostname': 'node2.example.com'
        }
    },
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


class OOCliFixture(OOInstallFixture):

    def setUp(self):
        OOInstallFixture.setUp(self)
        self.runner = CliRunner()

        # Add any arguments you would like to test here, the defaults ensure
        # we only do unattended invocations here, and using temporary files/dirs.
        self.cli_args = ["-a", self.work_dir]

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

    def _read_yaml(self, config_file_path):
        f = open(config_file_path, 'r')
        config = yaml.safe_load(f.read())
        f.close()
        return config


class UnattendedCliTests(OOCliFixture):

    def setUp(self):
        OOCliFixture.setUp(self)
        self.cli_args.append("-u")

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


class AttendedCliTests(OOCliFixture):

    def setUp(self):
        OOCliFixture.setUp(self)
        # Doesn't exist but keeps us from reading the local users config:
        self.config_file = os.path.join(self.work_dir, 'config.yml')
        self.cli_args.extend(["-c", self.config_file])
        print "Work dir: %s" % self.work_dir

    def _build_input(self, ssh_user='root', hosts=None, variant_num=1, add_nodes=None):
        """
        Builds a CLI input string with newline characters to simulate
        the full run.
        This gives us only one place to update when the input prompts change.
        """

        inputs = [
            'y',  # let's proceed
            ssh_user,
        ]

        if hosts:
            i = 0
            for (host, is_master) in hosts:
                inputs.append(host)
                inputs.append('y' if is_master else 'n')
                if i < len(hosts) - 1:
                    inputs.append('y')  # Add more hosts
                else:
                    inputs.append('n')  # Done adding hosts
                i += 1

        inputs.append(str(variant_num))  # Choose variant + version

        # TODO: support option 2, fresh install
        if add_nodes:
            inputs.append('1')  # Add more nodes
            i = 0
            for (host, is_master) in add_nodes:
                inputs.append(host)
                inputs.append('y' if is_master else 'n')
                if i < len(add_nodes) - 1:
                    inputs.append('y')  # Add more hosts
                else:
                    inputs.append('n')  # Done adding hosts
                i += 1

        inputs.extend([
            'y',  # confirm the facts
            'y',  # lets do this
        ])

        return '\n'.join(inputs)

    @patch('ooinstall.install_transactions.run_main_playbook')
    @patch('ooinstall.install_transactions.load_system_facts')
    def test_full_run(self, load_facts_mock, run_playbook_mock):
        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
        run_playbook_mock.return_value = 0

        cli_input = self._build_input(hosts=[
            ('10.0.0.1', True),
            ('10.0.0.2', False),
            ('10.0.0.3', False)])
        result = self.runner.invoke(cli.main, self.cli_args,
            input=cli_input)
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

        # Make sure the config file comes out looking right:
        written_config = self._read_yaml(self.config_file)

        for h in written_config['hosts']:
            self.assertTrue(h['node'])
            self.assertTrue('ip' in h)
            self.assertTrue('hostname' in h)
            self.assertTrue('public_ip' in h)
            self.assertTrue('public_hostname' in h)

    @patch('ooinstall.install_transactions.run_main_playbook')
    @patch('ooinstall.install_transactions.load_system_facts')
    def test_new_nodes(self, load_facts_mock, run_playbook_mock):

        # Modify the mock facts to return a version indicating OpenShift
        # is already installed on our master, and the first node.
        DUMMY_SYSTEM_FACTS['10.0.0.1']['common']['version'] = "3.0.0"
        DUMMY_SYSTEM_FACTS['10.0.0.2']['common']['version'] = "3.0.0"

        load_facts_mock.return_value = (DUMMY_SYSTEM_FACTS, 0)
        run_playbook_mock.return_value = 0

        cli_input = self._build_input(hosts=[
            ('10.0.0.1', True),
            ('10.0.0.2', False),
            ],
            add_nodes=[
                ('10.0.0.3', False)
            ])
        result = self.runner.invoke(cli.main, self.cli_args,
            input=cli_input)
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

        # Make sure the config file comes out looking right:
        written_config = self._read_yaml(self.config_file)

        for h in written_config['hosts']:
            self.assertTrue(h['node'])
            self.assertTrue('ip' in h)
            self.assertTrue('hostname' in h)
            self.assertTrue('public_ip' in h)
            self.assertTrue('public_hostname' in h)

# TODO: Test scaleup run on correct hosts when some show up as already installed
