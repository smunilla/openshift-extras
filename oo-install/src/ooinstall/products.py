""" Defines the supported product versions the installer supports, and metadata
required to run Ansible correctly. """


class Product(object):
    def __init__(self, key, description, ansible_key, aliases=None):
        # Supported product-version values for config file / CLI:
        self.key = key

        # Friendly name for the product:
        self.description = description

        # Value we'll pass to ansible as the deployment type, which can differ:
        self.ansible_key = ansible_key

        # Aliases are legacy keys this product may have been referred to
        # in old configs:
        self.aliases = aliases
        if self.aliases is None:
            self.aliases = []

OSE30 = Product('openshift-enterprise-3.0', 'OpenShift Enterprise 3.0',
    'enterprise', aliases=['enterprise'])
OSE31 = Product('openshift-enterprise-3.1', 'OpenShift Enterprise 3.1',
    'openshift-enterprise')
AEP31 = Product('atomic-enterprise-3.1', 'Atomic OpenShift Enterprise 3.1',
    'atomic-enterprise')

# Ordered list of products we can install, first is the default.
SUPPORTED_PRODUCTS = (OSE31, AEP31, OSE30)


def find_product(key):
    """
    Locate the product object for the key given in config file or on CLI.
    Return None if it's not supported.
    """
    for prod in SUPPORTED_PRODUCTS:
        if prod.key == key:
            return prod
        elif key in prod.aliases:
            return prod
    return None
