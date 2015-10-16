import click
import re
import sys
from ooinstall import install_transactions
from ooinstall import OOConfig
from ooinstall.oo_config import Host
from products import SUPPORTED_PRODUCTS, find_product

def validate_ansible_dir(ctx, param, path):
    if not path:
        raise click.BadParameter('An ansible path must be provided')
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
            raise click.BadParameter('"{}" appears to be an invalid hostname. ' \
                                     'Please double-check this value ' \
                                     'and re-enter it.'.format(hostname))
    return hosts

def validate_prompt_hostname(hostname):
    if '' == hostname or is_valid_hostname(hostname):
        return hostname
    raise click.BadParameter('"{}" appears to be an invalid hostname. ' \
                             'Please double-check this value i' \
                             'and re-enter it.'.format(hostname))

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
        del_idx = click.prompt('Select host to delete, y/Y to confirm, ' \
                               'or n/N to add more hosts', default='n')
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

def collect_hosts():
    """
        Collect host information from user. This will later be filled in using
        ansible.

        Returns: a list of host information collected from the user
    """
    click.clear()
    click.echo('***Host Configuration***')
    message = """
The OpenShift Master serves the API and web console.  It also coordinates the
jobs that have to run across the environment.  It can even run the datastore.
For wizard based installations the database will be embedded.  It's possible to
change this later using etcd from Red Hat Enterprise Linux 7.

Any Masters configured as part of this installation process will also be
configured as Nodes.  This is so that the Master will be able to proxy to Pods
from the API.  By default this Node will be unscheduleable but this can be changed
after installation with 'oadm manage-node'.

The OpenShift Node provides the runtime environments for containers.  It will
host the required services to be managed by the Master.

http://docs.openshift.com/enterprise/latest/architecture/infrastructure_components/kubernetes_infrastructure.html#master
http://docs.openshift.com/enterprise/3.0/architecture/infrastructure_components/kubernetes_infrastructure.html#node
    """
    click.echo(message)

    hosts = []
    more_hosts = True
    ip_regex = re.compile(r'^\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}$')

    while more_hosts:
        host_props = {}
        hostname_or_ip = click.prompt('Enter hostname or IP address:',
                                      default='',
                                      value_proc=validate_prompt_hostname)

        if ip_regex.match(hostname_or_ip):
            host_props['ip'] = hostname_or_ip
        else:
            host_props['hostname'] = hostname_or_ip

        host_props['master'] = click.confirm('Will this host be an OpenShift Master?')

        host = Host(**host_props)

        hosts.append(host)

        more_hosts = click.confirm('Do you want to add additional hosts?')
    return hosts

def collect_hosts_temp(host_type, hosts=[]):
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
            response = click.prompt("Please confirm the following {}. " \
                                    "y/Y to confirm, or n/N to edit".format(host_type), default='n')
            response = response.lower()
            if response == 'y':
                break
        else:
            response = click.prompt("No {} entered.  y/Y to confirm, " \
                                    "or n/N to edit".format(host_type), default='n')
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

def get_product():
    message = "\nWhich product to you want to install?\n\n"

    i = 1
    for product in SUPPORTED_PRODUCTS:
        message = "%s\n(%s) %s" % (message, i, product.description)

    click.echo(message)
    response = click.prompt("Choose a product from above: ", default=1)
    product = SUPPORTED_PRODUCTS[response - 1].key

    return product

def confirm_continue(message):
    click.echo(message)
    click.confirm("Are you ready to continue?", default=False, abort=True)
    return

def error_if_missing_info(oo_cfg):
    missing_info = False
    if 'masters' not in oo_cfg.settings or len(oo_cfg.settings['masters']) == 0:
        missing_info = True
        click.echo('For unattended installs, masters must be specified on the '
                   'command line or in the config file: %s' % oo_cfg.config_path)

    if 'nodes' not in oo_cfg.settings or len(oo_cfg.settings['nodes']) == 0:
        missing_info = True
        click.echo('For unattended installs, nodes must be specified on the '
                   'command line or in the config file: %s' % oo_cfg.config_path)

    missing_facts = oo_cfg.calc_missing_facts()
    if len(missing_facts) > 0:
        missing_info = True
        click.echo('For unattended installs, facts must be provided for all masters/nodes:')
        for host in missing_facts:
            click.echo('Host "%s" missing facts: %s' % (host, ", ".join(missing_facts[host])))

    if missing_info:
        sys.exit(1)


def get_missing_info_from_user(oo_cfg):
    """ Prompts the user for any information missing from the given configuration. """
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

    if not oo_cfg.settings.get('ansible_ssh_user', ''):
        oo_cfg.settings['ansible_ssh_user'] = get_ansible_ssh_user()
        click.clear()

    if product_key == '':
        product_key = get_product(product_key)
        click.clear()

    if not oo_cfg.settings.get('deployment_type', ''):
        oo_cfg.deployment_type = get_deployment_type()
        click.clear()

    if not oo_cfg.hosts:
        oo_cfg.hosts = collect_hosts()
        click.clear()

    if not oo_cfg.settings.get('product', '')
        oo_cfg.settings['product'] = get_product()

    return oo_cfg


def collect_new_nodes():
    click.clear()
    click.echo('***New Node Configuration***')
    message = """
Add new nodes here
    """
    click.echo(message)
    return collect_hosts()

def get_installed_hosts(hosts, callback_facts):
    installed_hosts = []
    for host in hosts:
        if(host in callback_facts.keys()
           and 'common' in callback_facts[host].keys()
           and callback_facts[host]['common'].get('version', '')):
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
        for node in installed_nodes:
            click.echo("{} is already an OpenShift Node".format(node))
            hosts_to_run_on.remove(node)
        # for unattended either continue if they force install or exit if they didn't
        if unattended:
            if not force:
                click.echo('Installed environment detected and no additional nodes specified: ' \
                           'aborting. If you want a fresh install, use --force')
                sys.exit(1)
        # for attended ask the user what to do
        else:
            click.echo('Installed environment detected and no additional nodes specified. ')
            response = click.prompt('Do you want to (1) add more nodes or ' \
                                    '(2) perform a clean install?', type=int)
            if response == 1: # add more nodes
                new_nodes = collect_new_nodes()

                hosts_to_run_on.append(new_nodes)

                install_transactions.set_config(oo_cfg)
                callback_facts, error = install_transactions.default_facts(oo_cfg.settings['masters'],
                                                                           oo_cfg.settings['nodes'])
                if error:
                    click.echo("There was a problem fetching the required information. " \
                               "See {} for details.".format(oo_cfg.settings['ansible_log_path']))
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
@click.option('--ansible-log-path',
              type=click.Path(file_okay=True,
                              dir_okay=False,
                              writable=True,
                              readable=True),
              default="/tmp/ansible.log")
@click.option('--unattended', '-u', is_flag=True, default=False)
@click.option('--force', '-f', is_flag=True, default=False)
def main(configuration, ansible_playbook_directory, ansible_log_path, unattended, force):
    oo_cfg = OOConfig(configuration)

    if not ansible_playbook_directory:
        ansible_playbook_directory = oo_cfg.settings.get('ansible_playbook_directory', '')
    validate_ansible_dir(None, None, ansible_playbook_directory)
    oo_cfg.settings['ansible_playbook_directory'] = ansible_playbook_directory
    oo_cfg.ansible_playbook_directory = ansible_playbook_directory

    oo_cfg.settings['ansible_log_path'] = ansible_log_path
    install_transactions.set_config(oo_cfg)

    if unattended:
        error_if_missing_info(oo_cfg)
    else:
        oo_cfg = get_missing_info_from_user(oo_cfg)

    # Lookup a Product based on the key we were given:
    if not oo_cfg.settings['product']:
        click.echo("No product specified in configuration file.")
        sys.exit(1)
    product = find_product(oo_cfg.settings['product'])
    if product is None:
        click.echo("%s is not an installable product." %
            oo_cfg.settings['product'])
        sys.exit(1)

    # TODO: Hack to be removed with the UI refactor:
    # We now have a list of strings for masters/nodes, add Host entries to
    # oo_config if necessary, make sure to check if each string looks like
    # an IP or a hostname so we can set appropriate property on the Host:
    ip_regex = re.compile("^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    all_hostnames = list(set(oo_cfg.settings['masters'] + oo_cfg.settings['nodes']))
    for hostname in all_hostnames:
        # Create a host if one doesn't exist:
        if oo_cfg.get_host(hostname) is None:
            host_props = {}
            if ip_regex.match(hostname):
                host_props['ip'] = hostname
            else:
                host_props['hostname'] = hostname
            host_props['master'] = True
            host = Host(**host_props)
            oo_cfg.hosts.append(host)

        # Flag it as master/node appropriately:
        host = oo_cfg.get_host(hostname)
        if hostname in oo_cfg.settings['masters']:
            host.master = True
        if hostname in oo_cfg.settings['nodes']:
            host.node = True



    # TODO: Technically we should make sure all the hosts are listed in the
    # validated facts.
    click.echo('Gathering information from hosts...')
    callback_facts, error = install_transactions.default_facts(oo_cfg.hosts)
    if error:
        click.echo("There was a problem fetching the required information. " \
                   "Please see {} for details.".format(oo_cfg.settings['ansible_log_path']))
        sys.exit(1)

    hosts_to_run_on, callback_facts = get_hosts_to_run_on(oo_cfg, callback_facts, unattended, force)

    # We already verified this is not the case for unattended installs, so this can
    # only trigger for live CLI users:
    # TODO: if there are *new* nodes and this is a live install, we may need the  user
    # to confirm the settings for new nodes. Look into this once we're distinguishing
    # between new and pre-existing nodes.
    if len(oo_cfg.calc_missing_facts()) > 0:
        validated_facts = confirm_hosts_facts(list(set(oo_cfg.settings['masters'] +
                                                       oo_cfg.settings['nodes'])), callback_facts)
        if validated_facts:
            oo_cfg.settings['validated_facts'] = validated_facts



        # TODO: This is a total hack that Sam will save us from with the UI refactor:
        # We now have a complete list of masters/nodes and validated facts, trash
        # whatever hosts we had on the config and update them for the settings we just
        # accumulated.
        # Eventually we'll just get Host objects from the user and add them to the config.
        for hostname in validated_facts:
            # We know there's a Host object from earlier block:
            host = oo_cfg.get_host(hostname)

            host_props = validated_facts[hostname]
            host.ip = host_props['ip']
            host.public_ip = host_props['public_ip']
            host.hostname = host_props['hostname']
            host.public_hostname = host_props['public_hostname']

    # TODO: Temporary hack as well
    # Reset the backward compatability settings:
    oo_cfg._add_legacy_backward_compat_settings()



    click.echo('Writing updated config to: %s' % oo_cfg.config_path)
    oo_cfg.save_to_disk()

    click.echo('Ready to run installation process.')
    message = """
If changes are needed to the values recorded by the installer please update {}.
""".format(oo_cfg.config_path)
    if not unattended:
        confirm_continue(message)

    error = install_transactions.run_main_playbook(oo_cfg.settings['masters'],
                                                   oo_cfg.settings['nodes'],
                                                   hosts_to_run_on)
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
