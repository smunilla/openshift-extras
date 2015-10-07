You can create a virtualenv to run oo-install from source:

virtualenv oo-install
cd oo-install
source ./bin/activate
virtualenv --relocatable .
cd ../src
python setup.py install

The virtualenv bin directory should now be at the start of your $PATH, and oo-install is ready to use from your shell.

