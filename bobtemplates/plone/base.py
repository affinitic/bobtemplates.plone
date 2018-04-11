# -*- coding: utf-8 -*-
from colorama import Fore
from colorama import Style
from datetime import date
from mrbob.bobexceptions import MrBobError
from mrbob.bobexceptions import SkipQuestion
from mrbob.bobexceptions import ValidationError
from six.moves import input

import keyword
import os
import re
import string
import subprocess
import sys


try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser


def git_support_enabled(configurator, question):
    if configurator.variables.get('package.git.disabled'):
        raise SkipQuestion(u'GIT support is disabled!.')


def echo(msg, msg_type=None):
    msg = str(msg)
    if msg_type == 'warning':
        colored_msg = Fore.YELLOW + msg + Style.RESET_ALL
    if msg_type == 'error':
        colored_msg = Fore.RED + msg + Style.RESET_ALL
    if msg_type == 'info':
        colored_msg = Fore.GREEN + Style.DIM + msg + \
            Style.RESET_ALL
    if not msg_type:
        colored_msg = msg + Style.RESET_ALL
    print(colored_msg)


class BobConfig(object):
    def __init__(self):
        self.version = None
        self.git_init = None
        self.template = None


def git_support(configurator):
    """ check if GIT support is disabled/enabled
    """
    git_support = True
    if configurator.variables.get('package.git.disabled'):
        git_support = False
    return git_support


def git_init(configurator):
    if not git_support(configurator):
        echo('GIT support disabled!')
        return
    params = [
        'git',
        'init',
    ]
    echo('RUN: {0}'.format(' '.join(params)), 'info')
    try:
        result = subprocess.check_output(
            params,
            cwd=configurator.target_directory,
        )
    except subprocess.CalledProcessError as e:
        echo(e.output, 'warning')
    else:
        if result:
            echo(result, 'info')


def git_commit(configurator, msg):
    if not git_support(configurator):
        echo('GIT support disabled!')
        return
    non_interactive = configurator.bobconfig.get('non_interactive')
    working_dir = configurator.variables.get(
        'package.root_folder') or configurator.target_directory
    params1 = [
        'git',
        'add',
        '.',
    ]
    params2 = [
        'git',
        'commit',
        '-m',
        '"{0}"'.format(msg),
    ]
    git_autocommit = None
    run_git_commit = True
    if configurator.variables.get('package.git.autocommit'):
        git_autocommit = True
    if not non_interactive and not git_autocommit:
        echo(
            'Should we run?:\n{0}\n{1}\nin: {2}'.format(
                ' '.join(params1),
                ' '.join(params2),
                working_dir,
            ),
            'info',
        )
        run_git_commit = (input('[y]/n: ') or 'y').lower() == 'y'

    if not run_git_commit and not git_autocommit:
        echo('Skip git commit!', 'warning')
        return

    echo('RUN: {0}'.format(' '.join(params1)), 'info')
    try:
        result1 = subprocess.check_output(
            params1,
            cwd=working_dir,
        )
    except subprocess.CalledProcessError as e:
        echo(e.output, 'warning')
    else:
        if result1:
            echo(result1, 'info')

    echo('RUN: {0}'.format(' '.join(params2)), 'info')
    try:
        result2 = subprocess.check_output(
            params2,
            cwd=working_dir,
        )
    except subprocess.CalledProcessError as e:
        echo(e.output, 'warning')
    else:
        echo(result2, 'info')


def git_clean_state_check(configurator, question):
    if not git_support(configurator):
        echo('GIT support disabled!')
        return
    params = [
        'git',
        'status',
        '--porcelain',
    ]
    echo('\nRUN: {0}'.format(' '.join(params)), 'info')
    try:
        result = subprocess.check_output(
            params,
            cwd=configurator.target_directory,
        )
    except subprocess.CalledProcessError as e:
        echo(e.output, 'error')
    else:
        if not result:
            echo(u'Git state is clean.\n', 'info')
            raise SkipQuestion(
                u'Git state is clean, so we skip this question.',
            )
        echo(
            u'git status result:\n----------------------------\n{0}'.format(
                result,
            ),
            'warning',
        )


def check_klass_name(configurator, question, answer):
    if keyword.iskeyword(answer):
        raise ValidationError(u'{key} is a reserved Python keyword'.format(key=answer))  # NOQA: E501
    if not re.match('[a-zA-Z_][a-zA-Z0-9_]*$', answer):
        raise ValidationError(u'{key} is not a valid class identifier'.format(key=answer))  # NOQA: E501
    return answer


def read_bobtemplates_ini(configurator):
    bob_config = BobConfig()
    config = ConfigParser()
    path = configurator.target_directory + '/bobtemplate.cfg'
    config.read(path)
    if not config.sections():
        return
    bob_config.version = config.get('main', 'version')
    bob_config.git_init = None
    if config.has_option('main', 'git_init'):
        bob_config.git_init = config.get('main', 'git_init')
    return bob_config


def set_global_vars(configurator):
    bob_config = read_bobtemplates_ini(configurator)
    configurator.variables['year'] = date.today().year
    version = configurator.variables.get('plone.version')
    if not version and bob_config:
        print('>>> reading Plone version from bobtemplate.cfg')
        version = bob_config.version
    set_plone_version_variables(configurator, version)


def set_plone_version_variables(configurator, version):
    version = configurator.variables.get('plone.version', version)
    if not version:
        return
    if 'plone.is_plone5' not in configurator.variables:
        # Find out if it is supposed to be Plone 5.
        if version.startswith('5'):
            configurator.variables['plone.is_plone5'] = True
        else:
            configurator.variables['plone.is_plone5'] = False
    if 'plone.minor_version' not in configurator.variables:
        # extract minor version (4.3)
        # (according to https://plone.org/support/version-support-policy)
        # this is used for the trove classifier in setup.py of the product
        configurator.variables['plone.minor_version'] = \
            '.'.join(version.split('.')[:2])


def get_git_info(value):
    """Try to get information from the git-config."""
    gitargs = ['git', 'config', '--get']
    try:
        result = subprocess.check_output(gitargs + [value]).strip()
        return result
    except (OSError, subprocess.CalledProcessError):
        pass


def validate_packagename(configurator):
    """Find out if the name target-dir entered when invoking the command can be
    a valid python-package."""
    package_dir = os.path.basename(configurator.target_directory)
    fail = False

    allowed = set(string.ascii_letters + string.digits + '.-_')
    if not set(package_dir).issubset(allowed):
        fail = True

    if package_dir.startswith('.') or package_dir.endswith('.'):
        fail = True

    parts = len(package_dir.split('.'))
    if parts < 2 or parts > 3:
        fail = True

    if fail:
        msg = (
            "Error: '{0}' is not a valid packagename.\n"
            'Please use a valid name (like collective.myaddon or '
            'plone.app.myaddon)'.format(package_dir)
        )
        sys.exit(msg)


def post_plone_version(configurator, question, answer):
    """Find out if it is supposed to be Plone 5."""
    set_plone_version_variables(configurator, answer)
    return answer


def pre_username(configurator, question):
    """Get email from git and validate package name."""
    # validate_packagename should be run before asking the first question.
    validate_packagename(configurator)

    default = get_git_info('user.name')
    if default and question:
        question.default = default


def pre_email(configurator, question):
    """Get email from git."""
    default = get_git_info('user.email')
    if default and question:
        question.default = default


def is_string_in_file(configurator, file_path, match_str):
    """Simple check if a given string is in a file.

    You can use this before adding new lines with update_file.

    """
    with open(file_path, 'r+') as xml_file:
        contents = xml_file.readlines()
    for index, line in enumerate(contents):
        if match_str in line:
            return True
    return False


def make_path(*args):
    """generate path string."""
    return os.sep.join(args)


def update_file(configurator, file_path, match_str, insert_str):
    """Insert insert_str into given file, by match_str."""
    changed = False

    with open(file_path, 'r+') as xml_file:
        contents = xml_file.readlines()
        if match_str in contents[-1]:  # Handle last line, prev. IndexError
            contents.append(insert_str)
            changed = True
        else:
            for index, line in enumerate(contents):
                if (
                    match_str in line and
                    insert_str not in contents[index + 1]
                ):
                    contents.insert(index + 1, insert_str)
                    changed = True
                    break
        xml_file.seek(0)
        xml_file.writelines(contents)

    if not changed:
        print(
            "WARNING: We couldn't find the match_str, "  # NOQA
            "skip inserting into {0}:\n".format(file_path)  # NOQA
        )
        print(insert_str)


def _get_package_root_folder(configurator):
    file_name = 'setup.py'
    root_folder = None
    os.chdir(configurator.target_directory)
    cur_dir = os.getcwd()
    while True:
        files = os.listdir(cur_dir)
        parent_dir = os.path.dirname(cur_dir)
        if file_name in files:
            root_folder = cur_dir
            break
        else:
            if cur_dir == parent_dir:
                break
            cur_dir = parent_dir
    return root_folder


def check_root_folder(configurator, question):
    """Check if we are in a package.

    Should be called in first question pre hook.

    """
    root_folder = _get_package_root_folder(configurator)
    if not root_folder:
        raise ValidationError(
            '\n\nNo setup.py found in path!\n'
            'Please run this subtemplate inside an existing package,\n'
            'in the package dir, where the actual code is!\n'
            "In the package collective.dx it's in collective.dx/collective/dx"
            '\n')


def dottedname_to_path(dottedname):
    path = '/'.join(dottedname.split('.'))
    return path


def base_prepare_renderer(configurator):
    """generic rendering before template specific rendering."""
    configurator.variables['package.root_folder'] = _get_package_root_folder(
        configurator,
    )
    if not configurator.variables['package.root_folder']:
        raise MrBobError('No setup.py found in path!\n')
    configurator.variables['package.dottedname'] = \
        configurator.variables['package.root_folder'].split('/')[-1]
    configurator.variables['package.namespace'] = \
        configurator.variables['package.dottedname'].split('.')[0]
    configurator.variables['package.name'] = \
        configurator.variables['package.dottedname'].split('.')[-1]
    # package.uppercasename = 'COLLECTIVE_FOO_SOMETHING'
    configurator.variables['package.uppercasename'] = \
        configurator.variables['package.dottedname'].replace('.', '_').upper()

    package_subpath = dottedname_to_path(
        configurator.variables['package.dottedname'],
    )
    configurator.variables['package_folder'] = \
        configurator.variables['package.root_folder'] + \
        u'/src/' + package_subpath
    configurator.target_directory = \
        configurator.variables['package.root_folder']
    return configurator


def subtemplate_warning(configurator, question):
    """Show a warning to the user before using subtemplates!"""
    print("""
    ### WARNING ###

    This is a subtemplate, it might override existing files without warnings!
    Please use a version control system like GIT with a clean state,
    to track changes, before using this subtemplate!

    """)


def subtemplate_warning_post_question(configurator, question, answer):
    if answer.lower() != 'y':
        print('Abort!')
        sys.exit(0)
    return answer
