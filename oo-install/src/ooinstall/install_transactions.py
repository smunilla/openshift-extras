import subprocess
import os
import yaml

def set_config(cfg):
    global CFG
    CFG = cfg

def generate_inventory(masters, nodes):
    global CFG
    ansible_inventory_directory = CFG.settings['ansible_inventory_directory']
    base_inventory_path = CFG.settings['ansible_inventory_path']
    base_inventory = open(base_inventory_path, 'w')
    base_inventory.write('\n[OSEv3:children]\nmasters\nnodes\n')
    base_inventory.write('\n[OSEv3:vars]\n')
    print "writing ssh user: %s" % CFG.settings['ansible_ssh_user']
    base_inventory.write('ansible_ssh_user={}\n'.format(CFG.settings['ansible_ssh_user']))
    if CFG.settings['ansible_ssh_user'] != 'root':
        base_inventory.write('ansible_sudo=true\n')
    base_inventory.write('deployment_type={}\n'.format(CFG.deployment_type))
    # TODO: Support AEP!
    base_inventory.write('product_type=openshift\n')
    if 'OO_INSTALL_DEVEL_REGISTRY' in os.environ:
        base_inventory.write('oreg_url=rcm-img-docker01.build.eng.bos.redhat.com:5001/openshift3/ose-${component}:${version}\n')
    if 'OO_INSTALL_PUDDLE_REPO_ENABLE' in os.environ:
        base_inventory.write("openshift_additional_repos=[{'id': 'ose-devel', 'name': 'ose-devel', 'baseurl': 'http://buildvm-devops.usersys.redhat.com/puddle/build/OpenShiftEnterprise/3.0/latest/RH7-RHOSE-3.0/$basearch/os', 'enabled': 1, 'gpgcheck': 0}]\n")
    if 'OO_INSTALL_STAGE_REGISTRY' in os.environ:
        base_inventory.write('oreg_url=registry.access.stage.redhat.com/openshift3/ose-${component}:${version}\n')
    base_inventory.write('\n[masters]\n')
    for m in masters:
        write_host(m, base_inventory)
    base_inventory.write('\n[nodes]\n')
    for n in nodes:
        # TODO: Until the Master can run the SDN itself we have to configure the Masters
        # as Nodes too.
        scheduleable = True
        if n in masters and len(masters) != 1:  # If there's only one Node and it's also a Master we want it to be scheduleable
            scheduleable = False
        write_host(n, base_inventory, scheduleable)
    base_inventory.close()
    return base_inventory_path

def write_host(host, inventory, scheduleable=True):
    global CFG
    if 'validated_facts' in CFG.settings and host in CFG.settings['validated_facts']:
        facts = ''
        if 'ip' in CFG.settings['validated_facts'][host]:
            facts += ' openshift_ip={}'.format(CFG.settings['validated_facts'][host]["ip"])
        if 'public_ip' in CFG.settings['validated_facts'][host]:
            facts += ' openshift_public_ip={}'.format(CFG.settings['validated_facts'][host]["public_ip"])
        if 'hostname' in CFG.settings['validated_facts'][host]:
            facts += ' openshift_hostname={}'.format(CFG.settings['validated_facts'][host]["hostname"])
        if 'public_hostname' in CFG.settings['validated_facts'][host]:
            facts += ' openshift_public_hostname={}'.format(CFG.settings['validated_facts'][host]["public_hostname"])
        # TODO: For not write_host is handles both master and nodes.
        # Technically only nodes will never need this.
        if not scheduleable:
            facts += ' openshift_scheduleable=False'
        inventory.write('{} {}\n'.format(host, facts))
    else:
        inventory.write('{}\n'.format(host))
    return


def load_system_facts(inventory_file, os_facts_path, env_vars):
    """
    Retrieves system facts from the remote systems.
    """
    FNULL = open(os.devnull, 'w')
    status = subprocess.call(['ansible-playbook',
                     '--inventory-file={}'.format(inventory_file),
                     os_facts_path],
                     env=env_vars,
                     stdout=FNULL)
    if not status == 0:
        return [], 1
    callback_facts_file = open(CFG.settings['ansible_callback_facts_yaml'], 'r')
    callback_facts = yaml.load(callback_facts_file)
    callback_facts_file.close()
    return callback_facts, 0


def default_facts(masters, nodes):
    global CFG
    inventory_file = generate_inventory(masters, nodes)
    os_facts_path = '{}/playbooks/byo/openshift_facts.yml'.format(CFG.ansible_playbook_directory)

    facts_env = os.environ.copy()
    facts_env["OO_INSTALL_CALLBACK_FACTS_YAML"] = CFG.settings['ansible_callback_facts_yaml']
    facts_env["ANSIBLE_CALLBACK_PLUGINS"] = CFG.settings['ansible_plugins_directory']
    if 'ansible_log_path' in CFG.settings:
        facts_env["ANSIBLE_LOG_PATH"] = CFG.settings['ansible_log_path']
    return load_system_facts(inventory_file, os_facts_path, facts_env)


def run_main_playbook(masters, nodes, hosts_to_run_on):
    global CFG
    inventory_file = generate_inventory(masters, nodes)
    if len(hosts_to_run_on) != len(nodes):
        main_playbook_path = os.path.join(CFG.ansible_playbook_directory, 'playbooks/common/openshift-cluster/scaleup.yml')
    else:
        main_playbook_path = os.path.join(CFG.ansible_playbook_directory, 'playbooks/byo/config.yml')
    facts_env = os.environ.copy()
    if 'ansible_log_path' in CFG.settings:
        facts_env["ANSIBLE_LOG_PATH"] = CFG.settings['ansible_log_path']
    return subprocess.call(['ansible-playbook',
                             '--inventory-file={}'.format(inventory_file),
                             main_playbook_path],
                             env=facts_env)
