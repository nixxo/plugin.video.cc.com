from __future__ import unicode_literals

import os.path
import optparse
import re
import sys

from .compat import (
    compat_expanduser,
    compat_get_terminal_size,
    compat_getenv,
    compat_kwargs,
    compat_shlex_split,
)
from .utils import (
    expand_path,
    get_executable_path,
    OUTTMPL_TYPES,
    preferredencoding,
    write_string,
)
from .version import __version__


def _hide_login_info(opts):
    PRIVATE_OPTS = set(['-p', '--password', '-u', '--username', '--video-password', '--ap-password', '--ap-username'])
    eqre = re.compile('^(?P<key>' + ('|'.join(re.escape(po) for po in PRIVATE_OPTS)) + ')=.+$')

    def _scrub_eq(o):
        m = eqre.match(o)
        if m:
            return m.group('key') + '=PRIVATE'
        else:
            return o

    opts = list(map(_scrub_eq, opts))
    for idx, opt in enumerate(opts):
        if opt in PRIVATE_OPTS and idx + 1 < len(opts):
            opts[idx + 1] = 'PRIVATE'
    return opts


def parseOpts(overrideArguments=None):
    def _readOptions(filename_bytes, default=[]):
        try:
            optionf = open(filename_bytes)
        except IOError:
            return default  # silently skip if file is not present
        try:
            # FIXME: https://github.com/ytdl-org/youtube-dl/commit/dfe5fa49aed02cf36ba9f743b11b0903554b5e56
            contents = optionf.read()
            if sys.version_info < (3,):
                contents = contents.decode(preferredencoding())
            res = compat_shlex_split(contents, comments=True)
        finally:
            optionf.close()
        return res

    def _readUserConf(package_name, default=[]):
        # .config
        xdg_config_home = compat_getenv('XDG_CONFIG_HOME') or compat_expanduser('~/.config')
        userConfFile = os.path.join(xdg_config_home, package_name, 'config')
        if not os.path.isfile(userConfFile):
            userConfFile = os.path.join(xdg_config_home, '%s.conf' % package_name)
        userConf = _readOptions(userConfFile, default=None)
        if userConf is not None:
            return userConf, userConfFile

        # appdata
        appdata_dir = compat_getenv('appdata')
        if appdata_dir:
            userConfFile = os.path.join(appdata_dir, package_name, 'config')
            userConf = _readOptions(userConfFile, default=None)
            if userConf is None:
                userConfFile += '.txt'
                userConf = _readOptions(userConfFile, default=None)
        if userConf is not None:
            return userConf, userConfFile

        # home
        userConfFile = os.path.join(compat_expanduser('~'), '%s.conf' % package_name)
        userConf = _readOptions(userConfFile, default=None)
        if userConf is None:
            userConfFile += '.txt'
            userConf = _readOptions(userConfFile, default=None)
        if userConf is not None:
            return userConf, userConfFile

        return default, None

    # No need to wrap help messages if we're on a wide console
    columns = compat_get_terminal_size().columns
    max_width = columns if columns else 80
    # 47% is chosen because that is how README.md is currently formatted
    # and moving help text even further to the right is undesirable.
    # This can be reduced in the future to get a prettier output
    max_help_position = int(0.47 * max_width)

    fmt = optparse.IndentedHelpFormatter(width=max_width, max_help_position=max_help_position)

    kw = {
        'version': __version__,
        'formatter': fmt,
        'usage': '%prog [OPTIONS] URL [URL...]',
        'conflict_handler': 'resolve',
    }

    parser = optparse.OptionParser(**compat_kwargs(kw))

    general = optparse.OptionGroup(parser, 'General Options')
    general.add_option(
        '-h', '--help',
        action='help',
        help='Print this help text and exit')
    general.add_option(
        '--version',
        action='version',
        help='Print program version and exit')
    general.add_option(
        '-U', '--update',
        action='store_true', dest='update_self',
        help='Update this program to latest version. Make sure that you have sufficient permissions (run with sudo if needed)')
    general.add_option(
        '-i', '--ignore-errors',
        action='store_true', dest='ignoreerrors',
        help='Ignore download and postprocessing errors. The download will be considered successfull even if the postprocessing fails')
    general.add_option(
        '--list-extractors',
        action='store_true', dest='list_extractors', default=False,
        help='List all supported extractors and exit')
    general.add_option(
        '--extractor-descriptions',
        action='store_true', dest='list_extractor_descriptions', default=False,
        help='Output descriptions of all supported extractors and exit')

    video_format = optparse.OptionGroup(parser, 'Video Format Options')
    video_format.add_option(
        '-f', '--format',
        action='store', dest='format', metavar='FORMAT', default=None,
        help='Video format code, see "FORMAT SELECTION" for more details')
    video_format.add_option(
        '--format-sort-force', '--S-force',
        action='store_true', dest='format_sort_force', metavar='FORMAT', default=False,
        help=(
            'Force user specified sort order to have precedence over all fields, '
            'see "Sorting Formats" for more details'))
    video_format.add_option(
        '--no-format-sort-force',
        action='store_false', dest='format_sort_force', metavar='FORMAT', default=False,
        help=(
            'Some fields have precedence over the user specified sort order (default), '
            'see "Sorting Formats" for more details'))
    video_format.add_option(
        '--all-formats',
        action='store_const', dest='format', const='all',
        help=optparse.SUPPRESS_HELP)
    video_format.add_option(
        '-F', '--list-formats',
        action='store_true', dest='listformats',
        help='List available formats of each video. Simulate unless --no-simulate is used')

    verbosity = optparse.OptionGroup(parser, 'Verbosity and Simulation Options')
    verbosity.add_option(
        '-q', '--quiet',
        action='store_true', dest='quiet', default=False,
        help='Activate quiet mode. If used with --verbose, print the log to stderr')
    verbosity.add_option(
        '--skip-download', '--no-download',
        action='store_true', dest='skip_download', default=False,
        help='Do not download the video but write all related files (Alias: --no-download)')
    verbosity.add_option(
        '--get-filename',
        action='store_true', dest='getfilename', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '--get-format',
        action='store_true', dest='getformat', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '-j', '--dump-json',
        action='store_true', dest='dumpjson', default=False,
        help='Quiet, but print JSON information for each video. Simulate unless --no-simulate is used. See "OUTPUT TEMPLATE" for a description of available keys')
    verbosity.add_option(
        '-J', '--dump-single-json',
        action='store_true', dest='dump_single_json', default=False,
        help=(
            'Quiet, but print JSON information for each url or infojson passed. Simulate unless --no-simulate is used. '
            'If the URL refers to a playlist, the whole playlist information is dumped in a single line'))
    verbosity.add_option(
        '--print-json',
        action='store_true', dest='print_json', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '-v', '--verbose',
        action='store_true', dest='verbose', default=False,
        help='Print various debugging information')

    parser.add_option_group(general)
    parser.add_option_group(verbosity)
    parser.add_option_group(video_format)

    if overrideArguments is not None:
        opts, args = parser.parse_args(overrideArguments)
        if opts.verbose:
            write_string('[debug] Override config: ' + repr(overrideArguments) + '\n')
    else:
        def compat_conf(conf):
            if sys.version_info < (3,):
                return [a.decode(preferredencoding(), 'replace') for a in conf]
            return conf

        configs = {
            'command-line': compat_conf(sys.argv[1:]),
            'custom': [], 'home': [], 'portable': [], 'user': [], 'system': []}
        paths = {'command-line': False}

        def read_options(name, path, user=False):
            ''' loads config files and returns ignoreconfig '''
            # Multiple package names can be given here
            # Eg: ('yt-dlp', 'youtube-dlc', 'youtube-dl') will look for
            # the configuration file of any of these three packages
            for package in ('yt-dlp',):
                if user:
                    config, current_path = _readUserConf(package, default=None)
                else:
                    current_path = os.path.join(path, '%s.conf' % package)
                    config = _readOptions(current_path, default=None)
                if config is not None:
                    configs[name], paths[name] = config, current_path
                    return parser.parse_args(config)[0].ignoreconfig
            return False

        def get_configs():
            opts, _ = parser.parse_args(configs['command-line'])

            if read_options('portable', get_executable_path()):
                return
            opts, _ = parser.parse_args(configs['portable'] + configs['custom'] + configs['command-line'])
            if read_options('system', '/etc'):
                return
            if read_options('user', None, user=True):
                configs['system'], paths['system'] = [], None

        get_configs()
        argv = configs['system'] + configs['user'] + configs['home'] + configs['portable'] + configs['custom'] + configs['command-line']
        opts, args = parser.parse_args(argv)

    return parser, opts, args
