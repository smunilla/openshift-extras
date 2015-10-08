
import unittest
import tempfile
import ooinstall.cli_installer as cli

from click.testing import CliRunner
from oo_config_tests import OOCliFixture


class UnattendedCliTests(OOCliFixture):

    def setUp(self):
        OOCliFixture.setUp(self)
        self.work_dir = tempfile.mkdtemp(prefix='ooconfigtests')
        self.tempfiles.append(self.work_dir)

        # Add any arguments you would like to test here, the defaults ensure
        # we only do unattended invocations here, and using temporary files/dirs.
        self.cli_args = ["-u", "-a", self.work_dir]
        self.runner = CliRunner()

    def run_cli(self):
        return self.runner.invoke(cli.main, self.cli_args)

    def test_ansible_path_required(self):
        runner = CliRunner()
        result = runner.invoke(cli.main, [])
        self.assertTrue(result.exit_code > 0)
        self.assertTrue("An ansible path must be provided", result.output)

    def test_no_cfg_full_run(self):
        #print result.output
        pass

