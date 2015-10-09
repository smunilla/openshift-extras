import click
import re
import os
import sys
from ooinstall import install_transactions
from ooinstall import OOConfig

class InstallerInfo(object):
    def __init__(self, ansible_ssh_user=None, deployment_type=None, masters=None, nodes=None):
        self.ansible_ssh_user = ansible_ssh_user
        self.deployment_type = deployment_type
        self.masters = masters
        self.nodes = nodes

def validate_ansible_dir(ctx, param, path):
    if not path:
        raise click.BadParameter("An ansible path must be provided".format(path))
    return path
    # if not os.path.exists(path)):
    #     raise click.BadParameter("Path \"{}\" doesn't exist".format(path))

def is_valid_hostname(hostname):
    if not hostname or len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1] # strip exactly one dot from the right, if present
    allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split("."))

def validate_hostname(ctx, param, hosts):
    # if '' == hostname or is_valid_hostname(hostname):
    for hostname in hosts:
        if not is_valid_hostname(hostname):
            raise click.BadParameter('"{}" appears to be an invalid hostname. Please double-check this value and re-enter it.'.format(hostname))
    return hosts

def validate_prompt_hostname(hostname):
    if '' == hostname or is_valid_hostname(hostname):
        return hostname
    raise click.BadParameter('"{}" appears to be an invalid hostname. Please double-check this value and re-enter it.'.format(hostname))

def get_hosts(hosts):
    click.echo('Please input each target host, followed by the return key. When finished, simply press return on an empty line.')
    while True:
        hostname = click.prompt('hostname/IP address', default='', value_proc=validate_prompt_hostname)
        if '' == hostname:
            break
        hosts.append(hostname)
    hosts = list(set(hosts)) # uniquify
    return hosts

def get_ansible_ssh_user():
    click.clear()
    message = """
This installation process will involve connecting to remote hosts via ssh.  Any
account may be used however if a non-root account is used it must have
passwordless sudo access.
"""
    click.echo(message)
    return click.prompt('User for ssh access', default='root')

def list_hosts(hosts):
    hosts_idx = range(len(hosts))
    for idx in hosts_idx:
        click.echo('   {}: {}'.format(idx, hosts[idx]))

def delete_hosts(hosts):
    while True:
        list_hosts(hosts)
        del_idx = click.prompt('Select host to delete, y/Y to confirm, or n/N to add more hosts', default='n')
        try:
            del_idx = int(del_idx)
            hosts.remove(hosts[del_idx])
        except IndexError:
            click.echo("\"{}\" doesn't match any hosts listed.".format(del_idx))
        except ValueError:
            try:
                response = del_idx.lower()
                if response in ['y', 'n']:
                    return hosts, response
                click.echo("\"{}\" doesn't coorespond to any valid input.".format(del_idx))
            except AttributeError:
                click.echo("\"{}\" doesn't coorespond to any valid input.".format(del_idx))
    return hosts, None

def collect_masters():
    click.clear()
    click.echo('***Master Configuration***')
    message = """
The OpenShift Master serves the API and web console.  It also coordinates the
jobs that have to run across the environment.  It can even run the datastore.
For wizard based installations the database will be embedded.  It's possible to
change this later using etcd from Red Hat Enterprise Linux 7.

Any Masters configured as part of this installation process will also be
configured as Nodes.  This is so that the Master will be able to proxy to Pods
from the API.  By default this Node will be unscheduleable but this can be changed
after installation with 'oadm manage-node'.

http://docs.openshift.com/enterprise/latest/architecture/infrastructure_components/kubernetes_infrastructure.html#master
    """
    click.echo(message)
    return collect_hosts('masters')

def collect_nodes(nodes):
    click.clear()
    click.echo('***Node Configuration***')
    message = """
The OpenShift Node provides the runtime environments for containers.  It will
host the required services to be managed by the Master.

By default all Masters will be configured as Nodes.

https://docs.openshift.com/enterprise/3.0/architecture/infrastructure_components/kubernetes_infrastructure.html#node
    """
    click.echo(message)
    return collect_hosts('nodes', nodes)

def collect_hosts(host_type, hosts=[]):
    message = """
Next we will launch an editor for entering {}.  The default editor in your
environment can be overridden exporting the VISUAL environment variable.
    """.format(host_type)
    click.echo(message)
    click.pause()
    while True:
        MARKER = '# Please enter {} one per line.  Hostnames or IPs are valid.\n'.format(host_type)
        message = click.edit("\n".join(hosts) + '\n\n' + MARKER)
        if message is not None:
            msg = message.split(MARKER, 1)[0].rstrip('\n')
            hosts = msg.splitlines()
            if hosts:
                # TODO: A lot more error handling needs to happen here.
                hosts = filter(None, hosts)
            else:
                click.echo('Empty message!')
        else:
            click.echo('You did not enter anything!')

        click.clear()
        if hosts:
            for i, h in enumerate(hosts):
                click.echo("{}) ".format(i+1) + h)
            response = click.prompt("Please confirm the following {}.  y/Y to confirm, or n/N to edit".format(host_type), default='n')
            response = response.lower()
            if response == 'y':
                break
        else:
            response = click.prompt("No {} entered.  y/Y to confirm, or n/N to edit".format(host_type), default='n')
            response = response.lower()
            if response == 'y':
                break
        click.clear()

    return hosts

def confirm_hosts_facts(hosts, callback_facts):
    click.clear()
    message = """
You'll now be asked to edit a file that will be used to validate settings
gathered from the Masters and Nodes.  Since it's often the case that the
hostname for a system inside the cluster is different from the hostname that is
resolveable from commandline or web clients these settings cannot be validated
automatically.

For some cloud providers the installer is able to gather metadata exposed in
the instance so reasonable defaults will be provided.
"""
    notes = """
Format:

installation host,IP,public IP,hostname,public hostname

Notes:
 * The installation host is the hostname from the installer's perspective.
 * The IP of the host should be the internal IP of the instance.
 * The public IP should be the externally accessible IP associated with the instance
 * The hostname should resolve to the internal IP from the instances
   themselves.
 * The public hostname should resolve to the external ip from hosts outside of
   the cloud.
"""

    click.echo(message)
    click.pause()

    default_facts_lines = []
    default_facts = {}
    validated_facts = {}
    for h in hosts:
        default_facts[h] = {}
        default_facts[h]["ip"] = callback_facts[h]["common"]["ip"]
        default_facts[h]["public_ip"] = callback_facts[h]["common"]["public_ip"]
        default_facts[h]["hostname"] = callback_facts[h]["common"]["hostname"]
        default_facts[h]['public_hostname'] = callback_facts[h]["common"]["public_hostname"]

        validated_facts[h] = {}
        default_facts_lines.append(",".join([h,
                                      callback_facts[h]["common"]["ip"],
                                      callback_facts[h]["common"]["public_ip"],
                                      callback_facts[h]["common"]["hostname"],
                                      callback_facts[h]["common"]["public_hostname"]]))

    MARKER = '# Everything after this line is ignored.\n'
    message = click.edit("\n".join(default_facts_lines) + '\n\n' + MARKER + notes)
    if message is not None:
        facts = message.split(MARKER, 1)[0].rstrip('\n')
        facts_lines = facts.splitlines()
        # TODO: A lot more error handling needs to happen here.
        facts_lines = filter(None, facts_lines)
        for l in facts_lines:
            h, ip, public_ip, hostname, public_hostname = l.split(',')
            validated_facts[h]["ip"] = ip.strip()
            validated_facts[h]["public_ip"] = public_ip.strip()
            validated_facts[h]["hostname"] = hostname.strip()
            validated_facts[h]['public_hostname'] = public_hostname.strip()
    else:
        click.echo('No changes made.  Using the defaults.')
        return default_facts
    return validated_facts

def get_deployment_type(deployment_type):
    #TODO: Wording obvs needs some work.
    if deployment_type == '':
        deployment_types = {1: 'enterprise',
                            2: 'openshift-enterprise',
                            3: 'atomic-enterprise',
                            }
        message = """
Which product to you want to install?

(1) OpenShift Enterprise 3.0
(2) OpenShift Enterprise 3.1
(3) Atomic Enterprise 3.1
"""
        click.echo(message)
        response = click.prompt("Choose a product from above: ", default=1)
        deployment_type = deployment_types[response]

    return deployment_type

def confirm_continue(message):
    click.echo(message)
    click.confirm("Are you ready to continue?", default=False, abort=True)
    return

def error_if_missing_info(oo_cfg):
    missing_info = False
    if 'masters' not in oo_cfg.settings or len(oo_cfg.settings['masters']) == 0:
        missing_info = True
        click.echo('For unattended installs, masters must be specified on the'
            'command line or in the config file: %s' % oo_cfg.config_path)

    if 'nodes' not in oo_cfg.settings or len(oo_cfg.settings['nodes']) == 0:
        missing_info = True
        click.echo('For unattended installs, nodes must be specified on the'
            'command line or in the config file: %s' % oo_cfg.config_path)

    missing_facts = oo_cfg.calc_missing_facts()
    if len(missing_facts) > 0:
        missing_info = True
        click.echo('For unattended installs, facts must be provided for all masters/nodes:')
        for host in missing_facts:
            click.echo('Host "%s" missing facts: %s' % (host, ", ".join(missing_facts[host])))

    if missing_info:
        sys.exit(1)


def get_info_from_user(ansible_ssh_user, deployment_type, masters, nodes):
    """ Prompts the user for any information missing from the given configuration. """
    installer_info = InstallerInfo()
    click.clear()

    message = """
Welcome to the OpenShift Enterprise 3 installation.

Please confirm that following prerequisites have been met:

* All systems where OpenShift will be installed are running Red Hat Enterprise
  Linux 7.
* All systems are properly subscribed to the required OpenShift Enterprise 3
  repositories.
* All systems have run docker-storage-setup (part of the Red Hat docker RPM).
* All systems have working DNS that resolves not only from the perspective of
  the installer but also from within the cluster.

When the process completes you will have a default configuration for Masters
and Nodes.  For ongoing environment maintenance it's recommended that the
official Ansible playbooks be used.

For more information on installation prerequisites please see:
https://docs.openshift.com/enterprise/latest/admin_guide/install/prerequisites.html
"""
    confirm_continue(message)
    click.clear()

    if ansible_ssh_user == '':
        ansible_ssh_user = get_ansible_ssh_user()
        click.clear()

    if deployment_type == '':
        deployment_type = get_deployment_type(deployment_type)
        click.clear()

    # TODO: Until the Master can run the SDN itself we have to configure the Masters
    # as Nodes too.
    if not masters:
        masters = collect_masters()
    if not nodes:
        nodes = collect_nodes(masters)
    nodes = list(set(masters + nodes))

    installer_info.masters = masters
    installer_info.nodes = nodes
    installer_info.deployment_type = deployment_type
    installer_info.ansible_ssh_user = ansible_ssh_user

    return installer_info


def collect_new_nodes_from_user():
    click.clear()
    click.echo('***New Node Configuration***')
    message = """
Add new nodes here
    """
    click.echo(message)
    return collect_hosts('new hosts')

def get_installed_hosts(hosts, callback_facts):
    installed_hosts = []
    for host in hosts:
        if(host in facts.keys() and 'common' in facts[host].keys() and facts[host]['common'].get('deployment_type', '')):
            installed_hosts.append(host)
    return installed_hosts

def get_hosts_to_run_on(oo_cfg, callback_facts, unattended, force):
    hosts_to_run_on = list(set(oo_cfg.settings['masters'] + oo_cfg.settings['nodes']))

    # Check if master or nodes already have something installed
    installed_masters = get_installed_hosts(list(oo_cfg.settings['masters']), callback_facts)
    installed_nodes = get_installed_hosts(list(oo_cfg.settings['nodes']), callback_facts)
    if len(installed_masters) > 0 or len(installed_nodes) > 0:
        # present a message listing already installed hosts
        for master in installed_masters:
            click.echo("{} is already an OpenShift Master".format(master))
            hosts_to_run_on.remove(master)
        for node in installed_nodes:
            click.echo("{} is already an OpenShift Node".format(node))
            hosts_to_run_on.remove(node)
        # for unattended either continue if they force install or exit if they didn't
        if unattended:
            if not force:
                click.echo('Installed environment detected and no additional nodes specified: aborting. If you want a fresh install, use --force')
                sys.exit(1)
        # for attended ask the user what to do
        else:
            click.echo('Installed environment detected and no additional nodes specified. ')
            response = click.prompt('Do you want to (1) add more nodes or (2) perform a clean install?',type=int)
            if response == 1: # add more nodes
                new_nodes = collect_new_nodes_from_user()

                hosts_to_run_on.append(new_nodes)

                install_transactions.set_config(oo_cfg)
                callback_facts, error = install_transactions.default_facts(oo_cfg.settings['masters'],oo_cfg.settings['nodes'])
                if error:
                    click.echo("There was a problem fetching the required information.  Please see {} for details.".format(oo_cfg.settings['ansible_log_path']))
                    sys.exit(1)
            else:
                pass # proceeding as normal should do a clean install

    return hosts_to_run_on, callback_facts

@click.command()
@click.option('--configuration', '-c',
              type=click.Path(file_okay=True,
                              dir_okay=False,
                              writable=True,
                              readable=True),
              default=None)
@click.option('--ansible-playbook-directory',
              '-a',
              type=click.Path(exists=True,
                              file_okay=False,
                              dir_okay=True,
                              writable=True,
                              readable=True),
              # callback=validate_ansible_dir,
              envvar='OO_ANSIBLE_PLAYBOOK_DIRECTORY')
@click.option('--ansible-config',
              type=click.Path(file_okay=True,
                              dir_okay=False,
                              writable=True,
                              readable=True),
              default=None)
@click.option('--ansible-log-path',
              type=click.Path(file_okay=True,
                              dir_okay=False,
                              writable=True,
                              readable=True),
              default="/tmp/ansible.log")
@click.option('--deployment-type',
              '-t',
              type=click.Choice(['origin', 'online', 'enterprise','atomic-enterprise','openshift-enterprise']),
              default=None)
@click.option('--unattended', '-u', is_flag=True, default=False)
@click.option('--force', '-f', is_flag=True, default=False)
# TODO: This probably needs to be updated now that hosts -> masters/nodes
@click.option('--host', '-h', 'hosts', multiple=True, callback=validate_hostname)
def main(configuration, ansible_playbook_directory, ansible_config, ansible_log_path, deployment_type, unattended, hosts, force):
    oo_cfg = OOConfig(configuration)

    if not ansible_playbook_directory:
        ansible_playbook_directory = oo_cfg.settings.get('ansible_playbook_directory', '')
    validate_ansible_dir(None, None, ansible_playbook_directory)
    oo_cfg.settings['ansible_playbook_directory'] = ansible_playbook_directory
    oo_cfg.ansible_playbook_directory = ansible_playbook_directory

    oo_cfg.settings['ansible_log_path'] = ansible_log_path
    install_transactions.set_config(oo_cfg)

    # Use CLI hosts if not already specified:
    # NOTE: This implies the config file masters/nodes override CLI.
    # Probably should kill the CLI hosts, this doesn't work so well with masters/nodes.
    masters = oo_cfg.settings.setdefault('masters', hosts)
    nodes = oo_cfg.settings.setdefault('nodes', hosts)
    ansible_ssh_user = oo_cfg.settings.get('ansible_ssh_user', '')

    # TODO: This reverts the above assumption and here the CLI is authoritative. Should
    # probably make this consider config the authoritative source as well. Print a warning
    # if both are specified.
    if not deployment_type:
        deployment_type = oo_cfg.settings.get('deployment_type', '')

    if unattended:
        installer_info = InstallerInfo(ansible_ssh_user, deployment_type, masters, nodes)
        error_if_missing_info(oo_cfg)
    else:
        installer_info = get_info_from_user(ansible_ssh_user, deployment_type, masters, nodes)

    oo_cfg.settings['ansible_ssh_user'] = installer_info.ansible_ssh_user
    oo_cfg.deployment_type = installer_info.deployment_type
    oo_cfg.settings['masters'] = installer_info.masters
    oo_cfg.settings['nodes'] = installer_info.nodes


    # TODO: Technically we should make sure all the hosts are listed in the
    # validated facts.
    click.echo('Gathering information from hosts...')
    callback_facts, error = install_transactions.default_facts(
        oo_cfg.settings['masters'], oo_cfg.settings['nodes'])
    if error:
        click.echo("There was a problem fetching the required information.  Please see {} for details.".format(oo_cfg.settings['ansible_log_path']))
        sys.exit(1)

    hosts_to_run_on, callback_facts = get_hosts_to_run_on(oo_cfg, callback_facts, unattended, force)

    # We already verified this is not the case for unattended installs, so this can
    # only trigger for live CLI users:
    # TODO: if there are *new* nodes and this is a live install, we may need the  user
    # to confirm the settings for new nodes. Look into this once we're distinguishing
    # between new and pre-existing nodes.
    if len(oo_cfg.calc_missing_facts()) > 0:
        validated_facts = confirm_hosts_facts(list(set(oo_cfg.settings['masters'] + oo_cfg.settings['nodes'])), callback_facts)
        if validated_facts:
            oo_cfg.settings['validated_facts'] = validated_facts

    click.echo('Writing updated config to: %s' % oo_cfg.config_path)
    oo_cfg.save_to_disk()

    click.echo('Ready to run installation process.')
    message = """
If changes are needed to the values recorded by the installer please update {}.
""".format(oo_cfg.config_path)
    if not unattended:
        confirm_continue(message)

    error = install_transactions.run_main_playbook(oo_cfg.settings['masters'], oo_cfg.settings['nodes'], hosts_to_run_on)
    if error:
        # The bootstrap script will print out the log location.
        message = """
An error was detected.  After resolving the problem please relaunch the
installation process.
"""
        click.echo(message)
        sys.exit(1)
    else:
        message = """
The installation was successful!

If this is your first time installing please take a look at the Administrator
Guide for advanced options related to routing, storage, authentication and much
more:

http://docs.openshift.com/enterprise/latest/admin_guide/overview.html
"""
        click.echo(message)
        click.pause()

if __name__ == '__main__':
    main()
