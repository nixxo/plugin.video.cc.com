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

    def _format_option_string(option):
        ''' ('-o', '--option') -> -o, --format METAVAR'''

        opts = []

        if option._short_opts:
            opts.append(option._short_opts[0])
        if option._long_opts:
            opts.append(option._long_opts[0])
        if len(opts) > 1:
            opts.insert(1, ', ')

        if option.takes_value():
            opts.append(' %s' % option.metavar)

        return ''.join(opts)

    def _list_from_options_callback(option, opt_str, value, parser, append=True, delim=',', process=str.strip):
        # append can be True, False or -1 (prepend)
        current = getattr(parser.values, option.dest) if append else []
        value = list(filter(None, [process(value)] if delim is None else map(process, value.split(delim))))
        setattr(
            parser.values, option.dest,
            current + value if append is True else value + current)

    def _set_from_options_callback(
            option, opt_str, value, parser, delim=',', allowed_values=None, aliases={},
            process=lambda x: x.lower().strip()):
        current = getattr(parser.values, option.dest)
        values = [process(value)] if delim is None else list(map(process, value.split(delim)[::-1]))
        while values:
            actual_val = val = values.pop()
            if val == 'all':
                current.update(allowed_values)
            elif val == '-all':
                current = set()
            elif val in aliases:
                values.extend(aliases[val])
            else:
                if val[0] == '-':
                    val = val[1:]
                    current.discard(val)
                else:
                    current.update([val])
                if allowed_values is not None and val not in allowed_values:
                    raise optparse.OptionValueError(f'wrong {option.metavar} for {opt_str}: {actual_val}')

        setattr(parser.values, option.dest, current)

    def _dict_from_options_callback(
            option, opt_str, value, parser,
            allowed_keys=r'[\w-]+', delimiter=':', default_key=None, process=None, multiple_keys=True):

        out_dict = getattr(parser.values, option.dest)
        if multiple_keys:
            allowed_keys = r'(%s)(,(%s))*' % (allowed_keys, allowed_keys)
        mobj = re.match(r'(?i)(?P<keys>%s)%s(?P<val>.*)$' % (allowed_keys, delimiter), value)
        if mobj is not None:
            keys = [k.strip() for k in mobj.group('keys').lower().split(',')]
            val = mobj.group('val')
        elif default_key is not None:
            keys, val = [default_key], value
        else:
            raise optparse.OptionValueError(
                'wrong %s formatting; it should be %s, not "%s"' % (opt_str, option.metavar, value))
        try:
            val = process(val) if process else val
        except Exception as err:
            raise optparse.OptionValueError(
                'wrong %s formatting; %s' % (opt_str, err))
        for key in keys:
            out_dict[key] = val

    # No need to wrap help messages if we're on a wide console
    columns = compat_get_terminal_size().columns
    max_width = columns if columns else 80
    # 47% is chosen because that is how README.md is currently formatted
    # and moving help text even further to the right is undesirable.
    # This can be reduced in the future to get a prettier output
    max_help_position = int(0.47 * max_width)

    fmt = optparse.IndentedHelpFormatter(width=max_width, max_help_position=max_help_position)
    fmt.format_option_strings = _format_option_string

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
        '--no-abort-on-error',
        action='store_const', dest='ignoreerrors', const='only_download',
        help='Continue with next video on download errors; e.g. to skip unavailable videos in a playlist (default)')
    general.add_option(
        '--abort-on-error', '--no-ignore-errors',
        action='store_false', dest='ignoreerrors',
        help='Abort downloading of further videos if an error occurs (Alias: --no-ignore-errors)')
    general.add_option(
        '--dump-user-agent',
        action='store_true', dest='dump_user_agent', default=False,
        help='Display the current user-agent and exit')
    general.add_option(
        '--list-extractors',
        action='store_true', dest='list_extractors', default=False,
        help='List all supported extractors and exit')
    general.add_option(
        '--extractor-descriptions',
        action='store_true', dest='list_extractor_descriptions', default=False,
        help='Output descriptions of all supported extractors and exit')
    general.add_option(
        '--force-generic-extractor',
        action='store_true', dest='force_generic_extractor', default=False,
        help='Force extraction to use the generic extractor')
    general.add_option(
        '--default-search',
        dest='default_search', metavar='PREFIX',
        help='Use this prefix for unqualified URLs. For example "gvsearch2:" downloads two videos from google videos for the search term "large apple". Use the value "auto" to let yt-dlp guess ("auto_warning" to emit a warning when guessing). "error" just throws an error. The default value "fixup_error" repairs broken URLs, but emits an error if this is not possible instead of searching')
    general.add_option(
        '--ignore-config', '--no-config',
        action='store_true', dest='ignoreconfig',
        help=(
            'Disable loading any configuration files except the one provided by --config-location. '
            'When given inside a configuration file, no further configuration files are loaded. '
            'Additionally, (for backward compatibility) if this option is found inside the '
            'system configuration file, the user configuration is not loaded'))
    general.add_option(
        '--config-location',
        dest='config_location', metavar='PATH',
        help='Location of the main configuration file; either the path to the config or its containing directory')
    general.add_option(
        '--flat-playlist',
        action='store_const', dest='extract_flat', const='in_playlist', default=False,
        help='Do not extract the videos of a playlist, only list them')
    general.add_option(
        '--no-flat-playlist',
        action='store_false', dest='extract_flat',
        help='Extract the videos of a playlist')
    general.add_option(
        '--mark-watched',
        action='store_true', dest='mark_watched', default=False,
        help='Mark videos watched (even with --simulate). Currently only supported for YouTube')
    general.add_option(
        '--no-mark-watched',
        action='store_false', dest='mark_watched',
        help='Do not mark videos watched (default)')
    general.add_option(
        '--no-colors',
        action='store_true', dest='no_color', default=False,
        help='Do not emit color codes in output')
    general.add_option(
        '--compat-options',
        metavar='OPTS', dest='compat_opts', default=set(), type='str',
        action='callback', callback=_set_from_options_callback,
        callback_kwargs={
            'allowed_values': {
                'filename', 'format-sort', 'abort-on-error', 'format-spec', 'no-playlist-metafiles',
                'multistreams', 'no-live-chat', 'playlist-index', 'list-formats', 'no-direct-merge',
                'no-youtube-channel-redirect', 'no-youtube-unavailable-videos', 'no-attach-info-json',
                'embed-thumbnail-atomicparsley', 'seperate-video-versions', 'no-clean-infojson', 'no-keep-subs',
            }, 'aliases': {
                'youtube-dl': ['-multistreams', 'all'],
                'youtube-dlc': ['-no-youtube-channel-redirect', '-no-live-chat', 'all'],
            }
        }, help=(
            'Options that can help keep compatibility with youtube-dl or youtube-dlc '
            'configurations by reverting some of the changes made in yt-dlp. '
            'See "Differences in default behavior" for details'))

    network = optparse.OptionGroup(parser, 'Network Options')
    network.add_option(
        '--proxy', dest='proxy',
        default=None, metavar='URL',
        help=(
            'Use the specified HTTP/HTTPS/SOCKS proxy. To enable '
            'SOCKS proxy, specify a proper scheme. For example '
            'socks5://127.0.0.1:1080/. Pass in an empty string (--proxy "") '
            'for direct connection'))
    network.add_option(
        '--socket-timeout',
        dest='socket_timeout', type=float, default=None, metavar='SECONDS',
        help='Time to wait before giving up, in seconds')
    network.add_option(
        '--source-address',
        metavar='IP', dest='source_address', default=None,
        help='Client-side IP address to bind to',
    )
    network.add_option(
        '-4', '--force-ipv4',
        action='store_const', const='0.0.0.0', dest='source_address',
        help='Make all connections via IPv4',
    )
    network.add_option(
        '-6', '--force-ipv6',
        action='store_const', const='::', dest='source_address',
        help='Make all connections via IPv6',
    )

    geo = optparse.OptionGroup(parser, 'Geo-restriction')
    geo.add_option(
        '--geo-verification-proxy',
        dest='geo_verification_proxy', default=None, metavar='URL',
        help=(
            'Use this proxy to verify the IP address for some geo-restricted sites. '
            'The default proxy specified by --proxy (or none, if the option is not present) is used for the actual downloading'))
    geo.add_option(
        '--cn-verification-proxy',
        dest='cn_verification_proxy', default=None, metavar='URL',
        help=optparse.SUPPRESS_HELP)
    geo.add_option(
        '--geo-bypass',
        action='store_true', dest='geo_bypass', default=True,
        help='Bypass geographic restriction via faking X-Forwarded-For HTTP header')
    geo.add_option(
        '--no-geo-bypass',
        action='store_false', dest='geo_bypass', default=True,
        help='Do not bypass geographic restriction via faking X-Forwarded-For HTTP header')
    geo.add_option(
        '--geo-bypass-country', metavar='CODE',
        dest='geo_bypass_country', default=None,
        help='Force bypass geographic restriction with explicitly provided two-letter ISO 3166-2 country code')
    geo.add_option(
        '--geo-bypass-ip-block', metavar='IP_BLOCK',
        dest='geo_bypass_ip_block', default=None,
        help='Force bypass geographic restriction with explicitly provided IP block in CIDR notation')

    selection = optparse.OptionGroup(parser, 'Video Selection')
    selection.add_option(
        '--playlist-start',
        dest='playliststart', metavar='NUMBER', default=1, type=int,
        help='Playlist video to start at (default is %default)')
    selection.add_option(
        '--playlist-end',
        dest='playlistend', metavar='NUMBER', default=None, type=int,
        help='Playlist video to end at (default is last)')
    selection.add_option(
        '--playlist-items',
        dest='playlist_items', metavar='ITEM_SPEC', default=None,
        help='Playlist video items to download. Specify indices of the videos in the playlist separated by commas like: "--playlist-items 1,2,5,8" if you want to download videos indexed 1, 2, 5, 8 in the playlist. You can specify range: "--playlist-items 1-3,7,10-13", it will download the videos at index 1, 2, 3, 7, 10, 11, 12 and 13')
    selection.add_option(
        '--match-title',
        dest='matchtitle', metavar='REGEX',
        help=optparse.SUPPRESS_HELP)
    selection.add_option(
        '--reject-title',
        dest='rejecttitle', metavar='REGEX',
        help=optparse.SUPPRESS_HELP)
    selection.add_option(
        '--max-downloads',
        dest='max_downloads', metavar='NUMBER', type=int, default=None,
        help='Abort after downloading NUMBER files')
    selection.add_option(
        '--min-filesize',
        metavar='SIZE', dest='min_filesize', default=None,
        help='Do not download any videos smaller than SIZE (e.g. 50k or 44.6m)')
    selection.add_option(
        '--max-filesize',
        metavar='SIZE', dest='max_filesize', default=None,
        help='Do not download any videos larger than SIZE (e.g. 50k or 44.6m)')
    selection.add_option(
        '--date',
        metavar='DATE', dest='date', default=None,
        help=(
            'Download only videos uploaded in this date. '
            'The date can be "YYYYMMDD" or in the format '
            '"(now|today)[+-][0-9](day|week|month|year)(s)?"'))
    selection.add_option(
        '--datebefore',
        metavar='DATE', dest='datebefore', default=None,
        help=(
            'Download only videos uploaded on or before this date. '
            'The date formats accepted is the same as --date'))
    selection.add_option(
        '--dateafter',
        metavar='DATE', dest='dateafter', default=None,
        help=(
            'Download only videos uploaded on or after this date. '
            'The date formats accepted is the same as --date'))
    selection.add_option(
        '--min-views',
        metavar='COUNT', dest='min_views', default=None, type=int,
        help=optparse.SUPPRESS_HELP)
    selection.add_option(
        '--max-views',
        metavar='COUNT', dest='max_views', default=None, type=int,
        help=optparse.SUPPRESS_HELP)
    selection.add_option(
        '--match-filter',
        metavar='FILTER', dest='match_filter', default=None,
        help=(
            'Generic video filter. Any field (see "OUTPUT TEMPLATE") can be compared with a '
            'number or a string using the operators defined in "Filtering formats". '
            'You can also simply specify a field to match if the field is present '
            'and "!field" to check if the field is not present. In addition, '
            'Python style regular expression matching can be done using "~=", '
            'and multiple filters can be checked with "&". '
            'Use a "\\" to escape "&" or quotes if needed. Eg: --match-filter '
            '"!is_live & like_count>?100 & description~=\'(?i)\\bcats \\& dogs\\b\'" '
            'matches only videos that are not live, has a like count more than 100 '
            '(or the like field is not available), and also has a description '
            'that contains the phrase "cats & dogs" (ignoring case)'))
    selection.add_option(
        '--no-match-filter',
        metavar='FILTER', dest='match_filter', action='store_const', const=None,
        help='Do not use generic video filter (default)')
    selection.add_option(
        '--no-playlist',
        action='store_true', dest='noplaylist', default=False,
        help='Download only the video, if the URL refers to a video and a playlist')
    selection.add_option(
        '--yes-playlist',
        action='store_false', dest='noplaylist',
        help='Download the playlist, if the URL refers to a video and a playlist')
    selection.add_option(
        '--age-limit',
        metavar='YEARS', dest='age_limit', default=None, type=int,
        help='Download only videos suitable for the given age')
    selection.add_option(
        '--download-archive', metavar='FILE',
        dest='download_archive',
        help='Download only videos not listed in the archive file. Record the IDs of all downloaded videos in it')
    selection.add_option(
        '--break-on-existing',
        action='store_true', dest='break_on_existing', default=False,
        help='Stop the download process when encountering a file that is in the archive')
    selection.add_option(
        '--break-on-reject',
        action='store_true', dest='break_on_reject', default=False,
        help='Stop the download process when encountering a file that has been filtered out')
    selection.add_option(
        '--skip-playlist-after-errors', metavar='N',
        dest='skip_playlist_after_errors', default=None, type=int,
        help='Number of allowed failures until the rest of the playlist is skipped')
    selection.add_option(
        '--no-download-archive',
        dest='download_archive', action="store_const", const=None,
        help='Do not use archive file (default)')
    selection.add_option(
        '--include-ads',
        dest='include_ads', action='store_true',
        help=optparse.SUPPRESS_HELP)
    selection.add_option(
        '--no-include-ads',
        dest='include_ads', action='store_false',
        help=optparse.SUPPRESS_HELP)

    authentication = optparse.OptionGroup(parser, 'Authentication Options')
    authentication.add_option(
        '-u', '--username',
        dest='username', metavar='USERNAME',
        help='Login with this account ID')
    authentication.add_option(
        '-p', '--password',
        dest='password', metavar='PASSWORD',
        help='Account password. If this option is left out, yt-dlp will ask interactively')
    authentication.add_option(
        '-2', '--twofactor',
        dest='twofactor', metavar='TWOFACTOR',
        help='Two-factor authentication code')
    authentication.add_option(
        '-n', '--netrc',
        action='store_true', dest='usenetrc', default=False,
        help='Use .netrc authentication data')
    authentication.add_option(
        '--netrc-location',
        dest='netrc_location', metavar='PATH',
        help='Location of .netrc authentication data; either the path or its containing directory. Defaults to ~/.netrc')
    authentication.add_option(
        '--video-password',
        dest='videopassword', metavar='PASSWORD',
        help='Video password (vimeo, youku)')
    authentication.add_option(
        '--ap-mso',
        dest='ap_mso', metavar='MSO',
        help='Adobe Pass multiple-system operator (TV provider) identifier, use --ap-list-mso for a list of available MSOs')
    authentication.add_option(
        '--ap-username',
        dest='ap_username', metavar='USERNAME',
        help='Multiple-system operator account login')
    authentication.add_option(
        '--ap-password',
        dest='ap_password', metavar='PASSWORD',
        help='Multiple-system operator account password. If this option is left out, yt-dlp will ask interactively')
    authentication.add_option(
        '--ap-list-mso',
        action='store_true', dest='ap_list_mso', default=False,
        help='List all supported multiple-system operators')

    video_format = optparse.OptionGroup(parser, 'Video Format Options')
    video_format.add_option(
        '-f', '--format',
        action='store', dest='format', metavar='FORMAT', default=None,
        help='Video format code, see "FORMAT SELECTION" for more details')
    video_format.add_option(
        '-S', '--format-sort', metavar='SORTORDER',
        dest='format_sort', default=[], type='str', action='callback',
        callback=_list_from_options_callback, callback_kwargs={'append': -1},
        help='Sort the formats by the fields given, see "Sorting Formats" for more details')
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
        '--video-multistreams',
        action='store_true', dest='allow_multiple_video_streams', default=None,
        help='Allow multiple video streams to be merged into a single file')
    video_format.add_option(
        '--no-video-multistreams',
        action='store_false', dest='allow_multiple_video_streams',
        help='Only one video stream is downloaded for each output file (default)')
    video_format.add_option(
        '--audio-multistreams',
        action='store_true', dest='allow_multiple_audio_streams', default=None,
        help='Allow multiple audio streams to be merged into a single file')
    video_format.add_option(
        '--no-audio-multistreams',
        action='store_false', dest='allow_multiple_audio_streams',
        help='Only one audio stream is downloaded for each output file (default)')
    video_format.add_option(
        '--all-formats',
        action='store_const', dest='format', const='all',
        help=optparse.SUPPRESS_HELP)
    video_format.add_option(
        '--prefer-free-formats',
        action='store_true', dest='prefer_free_formats', default=False,
        help=(
            'Prefer video formats with free containers over non-free ones of same quality. '
            'Use with "-S ext" to strictly prefer free containers irrespective of quality'))
    video_format.add_option(
        '--no-prefer-free-formats',
        action='store_false', dest='prefer_free_formats', default=False,
        help="Don't give any special preference to free containers (default)")
    video_format.add_option(
        '--check-formats',
        action='store_true', dest='check_formats', default=None,
        help='Check that the formats selected are actually downloadable')
    video_format.add_option(
        '--no-check-formats',
        action='store_false', dest='check_formats',
        help='Do not check that the formats selected are actually downloadable')
    video_format.add_option(
        '-F', '--list-formats',
        action='store_true', dest='listformats',
        help='List available formats of each video. Simulate unless --no-simulate is used')
    video_format.add_option(
        '--list-formats-as-table',
        action='store_true', dest='listformats_table', default=True,
        help=optparse.SUPPRESS_HELP)
    video_format.add_option(
        '--list-formats-old', '--no-list-formats-as-table',
        action='store_false', dest='listformats_table',
        help=optparse.SUPPRESS_HELP)
    video_format.add_option(
        '--merge-output-format',
        action='store', dest='merge_output_format', metavar='FORMAT', default=None,
        help=(
            'If a merge is required (e.g. bestvideo+bestaudio), '
            'output to given container format. One of mkv, mp4, ogg, webm, flv. '
            'Ignored if no merge is required'))
    video_format.add_option(
        '--allow-unplayable-formats',
        action='store_true', dest='allow_unplayable_formats', default=False,
        help=optparse.SUPPRESS_HELP)
    video_format.add_option(
        '--no-allow-unplayable-formats',
        action='store_false', dest='allow_unplayable_formats',
        help=optparse.SUPPRESS_HELP)

    subtitles = optparse.OptionGroup(parser, 'Subtitle Options')
    subtitles.add_option(
        '--write-subs', '--write-srt',
        action='store_true', dest='writesubtitles', default=False,
        help='Write subtitle file')
    subtitles.add_option(
        '--no-write-subs', '--no-write-srt',
        action='store_false', dest='writesubtitles',
        help='Do not write subtitle file (default)')
    subtitles.add_option(
        '--write-auto-subs', '--write-automatic-subs',
        action='store_true', dest='writeautomaticsub', default=False,
        help='Write automatically generated subtitle file (Alias: --write-automatic-subs)')
    subtitles.add_option(
        '--no-write-auto-subs', '--no-write-automatic-subs',
        action='store_false', dest='writeautomaticsub', default=False,
        help='Do not write auto-generated subtitles (default) (Alias: --no-write-automatic-subs)')
    subtitles.add_option(
        '--all-subs',
        action='store_true', dest='allsubtitles', default=False,
        help=optparse.SUPPRESS_HELP)
    subtitles.add_option(
        '--list-subs',
        action='store_true', dest='listsubtitles', default=False,
        help='List available subtitles of each video. Simulate unless --no-simulate is used')
    subtitles.add_option(
        '--sub-format',
        action='store', dest='subtitlesformat', metavar='FORMAT', default='best',
        help='Subtitle format, accepts formats preference, for example: "srt" or "ass/srt/best"')
    subtitles.add_option(
        '--sub-langs', '--srt-langs',
        action='callback', dest='subtitleslangs', metavar='LANGS', type='str',
        default=[], callback=_list_from_options_callback,
        help=(
            'Languages of the subtitles to download (can be regex) or "all" separated by commas. (Eg: --sub-langs en.*,ja) '
            'You can prefix the language code with a "-" to exempt it from the requested languages. (Eg: --sub-langs all,-live_chat) '
            'Use --list-subs for a list of available language tags'))

    workarounds = optparse.OptionGroup(parser, 'Workarounds')
    workarounds.add_option(
        '--encoding',
        dest='encoding', metavar='ENCODING',
        help='Force the specified encoding (experimental)')
    workarounds.add_option(
        '--no-check-certificates',
        action='store_true', dest='no_check_certificate', default=False,
        help='Suppress HTTPS certificate validation')
    workarounds.add_option(
        '--prefer-insecure', '--prefer-unsecure',
        action='store_true', dest='prefer_insecure',
        help='Use an unencrypted connection to retrieve information about the video (Currently supported only for YouTube)')
    workarounds.add_option(
        '--user-agent',
        metavar='UA', dest='user_agent',
        help='Specify a custom user agent')
    workarounds.add_option(
        '--referer',
        metavar='URL', dest='referer', default=None,
        help='Specify a custom referer, use if the video access is restricted to one domain',
    )
    workarounds.add_option(
        '--add-header',
        metavar='FIELD:VALUE', dest='headers', default={}, type='str',
        action='callback', callback=_dict_from_options_callback,
        callback_kwargs={'multiple_keys': False},
        help='Specify a custom HTTP header and its value, separated by a colon ":". You can use this option multiple times',
    )
    workarounds.add_option(
        '--bidi-workaround',
        dest='bidi_workaround', action='store_true',
        help='Work around terminals that lack bidirectional text support. Requires bidiv or fribidi executable in PATH')
    workarounds.add_option(
        '--sleep-requests', metavar='SECONDS',
        dest='sleep_interval_requests', type=float,
        help='Number of seconds to sleep between requests during data extraction')
    workarounds.add_option(
        '--sleep-interval', '--min-sleep-interval', metavar='SECONDS',
        dest='sleep_interval', type=float,
        help=(
            'Number of seconds to sleep before each download. '
            'This is the minimum time to sleep when used along with --max-sleep-interval '
            '(Alias: --min-sleep-interval)'))
    workarounds.add_option(
        '--max-sleep-interval', metavar='SECONDS',
        dest='max_sleep_interval', type=float,
        help='Maximum number of seconds to sleep. Can only be used along with --min-sleep-interval')
    workarounds.add_option(
        '--sleep-subtitles', metavar='SECONDS',
        dest='sleep_interval_subtitles', default=0, type=int,
        help='Number of seconds to sleep before each subtitle download')

    verbosity = optparse.OptionGroup(parser, 'Verbosity and Simulation Options')
    verbosity.add_option(
        '-q', '--quiet',
        action='store_true', dest='quiet', default=False,
        help='Activate quiet mode. If used with --verbose, print the log to stderr')
    verbosity.add_option(
        '--no-warnings',
        dest='no_warnings', action='store_true', default=False,
        help='Ignore warnings')
    verbosity.add_option(
        '-s', '--simulate',
        action='store_true', dest='simulate', default=None,
        help='Do not download the video and do not write anything to disk')
    verbosity.add_option(
        '--no-simulate',
        action='store_false', dest='simulate',
        help='Download the video even if printing/listing options are used')
    verbosity.add_option(
        '--ignore-no-formats-error',
        action='store_true', dest='ignore_no_formats_error', default=False,
        help=(
            'Ignore "No video formats" error. Usefull for extracting metadata '
            'even if the videos are not actually available for download (experimental)'))
    verbosity.add_option(
        '--no-ignore-no-formats-error',
        action='store_false', dest='ignore_no_formats_error',
        help='Throw error when no downloadable video formats are found (default)')
    verbosity.add_option(
        '--skip-download', '--no-download',
        action='store_true', dest='skip_download', default=False,
        help='Do not download the video but write all related files (Alias: --no-download)')
    verbosity.add_option(
        '-O', '--print',
        metavar='TEMPLATE', action='append', dest='forceprint',
        help=(
            'Quiet, but print the given fields for each video. Simulate unless --no-simulate is used. '
            'Either a field name or same syntax as the output template can be used'))
    verbosity.add_option(
        '-g', '--get-url',
        action='store_true', dest='geturl', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '-e', '--get-title',
        action='store_true', dest='gettitle', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '--get-id',
        action='store_true', dest='getid', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '--get-thumbnail',
        action='store_true', dest='getthumbnail', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '--get-description',
        action='store_true', dest='getdescription', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '--get-duration',
        action='store_true', dest='getduration', default=False,
        help=optparse.SUPPRESS_HELP)
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
        '--force-write-archive', '--force-write-download-archive', '--force-download-archive',
        action='store_true', dest='force_write_download_archive', default=False,
        help=(
            'Force download archive entries to be written as far as no errors occur, '
            'even if -s or another simulation option is used (Alias: --force-download-archive)'))
    verbosity.add_option(
        '--newline',
        action='store_true', dest='progress_with_newline', default=False,
        help='Output progress bar as new lines')
    verbosity.add_option(
        '--no-progress',
        action='store_true', dest='noprogress', default=None,
        help='Do not print progress bar')
    verbosity.add_option(
        '--progress',
        action='store_false', dest='noprogress',
        help='Show progress bar, even if in quiet mode')
    verbosity.add_option(
        '--console-title',
        action='store_true', dest='consoletitle', default=False,
        help='Display progress in console titlebar')
    verbosity.add_option(
        '--progress-template',
        metavar='[TYPES:]TEMPLATE', dest='progress_template', default={}, type='str',
        action='callback', callback=_dict_from_options_callback,
        callback_kwargs={
            'allowed_keys': '(download|postprocess)(-title)?',
            'default_key': 'download'
        }, help=(
            'Template for progress outputs, optionally prefixed with one of "download:" (default), '
            '"download-title:" (the console title), "postprocess:",  or "postprocess-title:". '
            'The video\'s fields are accessible under the "info" key and '
            'the progress attributes are accessible under "progress" key. Eg: '
            # TODO: Document the fields inside "progress"
            '--console-title --progress-template "download-title:%(info.id)s-%(progress.eta)s"'))
    verbosity.add_option(
        '-v', '--verbose',
        action='store_true', dest='verbose', default=False,
        help='Print various debugging information')
    verbosity.add_option(
        '--dump-pages', '--dump-intermediate-pages',
        action='store_true', dest='dump_intermediate_pages', default=False,
        help='Print downloaded pages encoded using base64 to debug problems (very verbose)')
    verbosity.add_option(
        '--write-pages',
        action='store_true', dest='write_pages', default=False,
        help='Write downloaded intermediary pages to files in the current directory to debug problems')
    verbosity.add_option(
        '--youtube-print-sig-code',
        action='store_true', dest='youtube_print_sig_code', default=False,
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '--print-traffic', '--dump-headers',
        dest='debug_printtraffic', action='store_true', default=False,
        help='Display sent and read HTTP traffic')
    verbosity.add_option(
        '-C', '--call-home',
        dest='call_home', action='store_true', default=False,
        # help='[Broken] Contact the yt-dlp server for debugging')
        help=optparse.SUPPRESS_HELP)
    verbosity.add_option(
        '--no-call-home',
        dest='call_home', action='store_false',
        # help='Do not contact the yt-dlp server for debugging (default)')
        help=optparse.SUPPRESS_HELP)

    filesystem = optparse.OptionGroup(parser, 'Filesystem Options')
    filesystem.add_option(
        '-a', '--batch-file',
        dest='batchfile', metavar='FILE',
        help="File containing URLs to download ('-' for stdin), one URL per line. "
             "Lines starting with '#', ';' or ']' are considered as comments and ignored")
    filesystem.add_option(
        '-P', '--paths',
        metavar='[TYPES:]PATH', dest='paths', default={}, type='str',
        action='callback', callback=_dict_from_options_callback,
        callback_kwargs={
            'allowed_keys': 'home|temp|%s' % '|'.join(OUTTMPL_TYPES.keys()),
            'default_key': 'home'
        }, help=(
            'The paths where the files should be downloaded. '
            'Specify the type of file and the path separated by a colon ":". '
            'All the same types as --output are supported. '
            'Additionally, you can also provide "home" (default) and "temp" paths. '
            'All intermediary files are first downloaded to the temp path and '
            'then the final files are moved over to the home path after download is finished. '
            'This option is ignored if --output is an absolute path'))
    filesystem.add_option(
        '-o', '--output',
        metavar='[TYPES:]TEMPLATE', dest='outtmpl', default={}, type='str',
        action='callback', callback=_dict_from_options_callback,
        callback_kwargs={
            'allowed_keys': '|'.join(OUTTMPL_TYPES.keys()),
            'default_key': 'default'
        }, help='Output filename template; see "OUTPUT TEMPLATE" for details')
    filesystem.add_option(
        '--output-na-placeholder',
        dest='outtmpl_na_placeholder', metavar='TEXT', default='NA',
        help=('Placeholder value for unavailable meta fields in output filename template (default: "%default")'))
    filesystem.add_option(
        '--autonumber-size',
        dest='autonumber_size', metavar='NUMBER', type=int,
        help=optparse.SUPPRESS_HELP)
    filesystem.add_option(
        '--autonumber-start',
        dest='autonumber_start', metavar='NUMBER', default=1, type=int,
        help=optparse.SUPPRESS_HELP)
    filesystem.add_option(
        '--restrict-filenames',
        action='store_true', dest='restrictfilenames', default=False,
        help='Restrict filenames to only ASCII characters, and avoid "&" and spaces in filenames')
    filesystem.add_option(
        '--no-restrict-filenames',
        action='store_false', dest='restrictfilenames',
        help='Allow Unicode characters, "&" and spaces in filenames (default)')
    filesystem.add_option(
        '--windows-filenames',
        action='store_true', dest='windowsfilenames', default=False,
        help='Force filenames to be windows compatible')
    filesystem.add_option(
        '--no-windows-filenames',
        action='store_false', dest='windowsfilenames',
        help='Make filenames windows compatible only if using windows (default)')
    filesystem.add_option(
        '--trim-filenames', '--trim-file-names', metavar='LENGTH',
        dest='trim_file_name', default=0, type=int,
        help='Limit the filename length (excluding extension) to the specified number of characters')
    filesystem.add_option(
        '-w', '--no-overwrites',
        action='store_false', dest='overwrites', default=None,
        help='Do not overwrite any files')
    filesystem.add_option(
        '--force-overwrites', '--yes-overwrites',
        action='store_true', dest='overwrites',
        help='Overwrite all video and metadata files. This option includes --no-continue')
    filesystem.add_option(
        '--no-force-overwrites',
        action='store_const', dest='overwrites', const=None,
        help='Do not overwrite the video, but overwrite related files (default)')
    filesystem.add_option(
        '-c', '--continue',
        action='store_true', dest='continue_dl', default=True,
        help='Resume partially downloaded files/fragments (default)')
    filesystem.add_option(
        '--no-continue',
        action='store_false', dest='continue_dl',
        help=(
            'Do not resume partially downloaded fragments. '
            'If the file is not fragmented, restart download of the entire file'))
    filesystem.add_option(
        '--part',
        action='store_false', dest='nopart', default=False,
        help='Use .part files instead of writing directly into output file (default)')
    filesystem.add_option(
        '--no-part',
        action='store_true', dest='nopart',
        help='Do not use .part files - write directly into output file')
    filesystem.add_option(
        '--mtime',
        action='store_true', dest='updatetime', default=True,
        help='Use the Last-modified header to set the file modification time (default)')
    filesystem.add_option(
        '--no-mtime',
        action='store_false', dest='updatetime',
        help='Do not use the Last-modified header to set the file modification time')
    filesystem.add_option(
        '--write-description',
        action='store_true', dest='writedescription', default=False,
        help='Write video description to a .description file')
    filesystem.add_option(
        '--no-write-description',
        action='store_false', dest='writedescription',
        help='Do not write video description (default)')
    filesystem.add_option(
        '--write-info-json',
        action='store_true', dest='writeinfojson', default=False,
        help='Write video metadata to a .info.json file (this may contain personal information)')
    filesystem.add_option(
        '--no-write-info-json',
        action='store_false', dest='writeinfojson',
        help='Do not write video metadata (default)')
    filesystem.add_option(
        '--write-annotations',
        action='store_true', dest='writeannotations', default=False,
        help=optparse.SUPPRESS_HELP)
    filesystem.add_option(
        '--no-write-annotations',
        action='store_false', dest='writeannotations',
        help=optparse.SUPPRESS_HELP)
    filesystem.add_option(
        '--write-playlist-metafiles',
        action='store_true', dest='allow_playlist_files', default=None,
        help=(
            'Write playlist metadata in addition to the video metadata '
            'when using --write-info-json, --write-description etc. (default)'))
    filesystem.add_option(
        '--no-write-playlist-metafiles',
        action='store_false', dest='allow_playlist_files',
        help='Do not write playlist metadata when using --write-info-json, --write-description etc.')
    filesystem.add_option(
        '--clean-infojson',
        action='store_true', dest='clean_infojson', default=None,
        help=(
            'Remove some private fields such as filenames from the infojson. '
            'Note that it could still contain some personal information (default)'))
    filesystem.add_option(
        '--no-clean-infojson',
        action='store_false', dest='clean_infojson',
        help='Write all fields to the infojson')
    filesystem.add_option(
        '--write-comments', '--get-comments',
        action='store_true', dest='getcomments', default=False,
        help=(
            'Retrieve video comments to be placed in the infojson. '
            'The comments are fetched even without this option if the extraction is known to be quick (Alias: --get-comments)'))
    filesystem.add_option(
        '--no-write-comments', '--no-get-comments',
        action='store_false', dest='getcomments',
        help='Do not retrieve video comments unless the extraction is known to be quick (Alias: --no-get-comments)')
    filesystem.add_option(
        '--load-info-json', '--load-info',
        dest='load_info_filename', metavar='FILE',
        help='JSON file containing the video information (created with the "--write-info-json" option)')
    filesystem.add_option(
        '--cookies',
        dest='cookiefile', metavar='FILE',
        help='File to read cookies from and dump cookie jar in')
    filesystem.add_option(
        '--no-cookies',
        action='store_const', const=None, dest='cookiefile', metavar='FILE',
        help='Do not read/dump cookies from/to file (default)')
    filesystem.add_option(
        '--no-cookies-from-browser',
        action='store_const', const=None, dest='cookiesfrombrowser',
        help='Do not load cookies from browser (default)')
    filesystem.add_option(
        '--cache-dir', dest='cachedir', default=None, metavar='DIR',
        help='Location in the filesystem where youtube-dl can store some downloaded information (such as client ids and signatures) permanently. By default $XDG_CACHE_HOME/yt-dlp or ~/.cache/yt-dlp')
    filesystem.add_option(
        '--no-cache-dir', action='store_false', dest='cachedir',
        help='Disable filesystem caching')
    filesystem.add_option(
        '--rm-cache-dir',
        action='store_true', dest='rm_cachedir',
        help='Delete all filesystem cache files')

    thumbnail = optparse.OptionGroup(parser, 'Thumbnail Options')
    thumbnail.add_option(
        '--write-thumbnail',
        action='store_true', dest='writethumbnail', default=False,
        help='Write thumbnail image to disk')
    thumbnail.add_option(
        '--no-write-thumbnail',
        action='store_false', dest='writethumbnail',
        help='Do not write thumbnail image to disk (default)')
    thumbnail.add_option(
        '--write-all-thumbnails',
        action='store_true', dest='write_all_thumbnails', default=False,
        help='Write all thumbnail image formats to disk')
    thumbnail.add_option(
        '--list-thumbnails',
        action='store_true', dest='list_thumbnails', default=False,
        help='List available thumbnails of each video. Simulate unless --no-simulate is used')

    link = optparse.OptionGroup(parser, 'Internet Shortcut Options')
    link.add_option(
        '--write-link',
        action='store_true', dest='writelink', default=False,
        help='Write an internet shortcut file, depending on the current platform (.url, .webloc or .desktop). The URL may be cached by the OS')
    link.add_option(
        '--write-url-link',
        action='store_true', dest='writeurllink', default=False,
        help='Write a .url Windows internet shortcut. The OS caches the URL based on the file path')
    link.add_option(
        '--write-webloc-link',
        action='store_true', dest='writewebloclink', default=False,
        help='Write a .webloc macOS internet shortcut')
    link.add_option(
        '--write-desktop-link',
        action='store_true', dest='writedesktoplink', default=False,
        help='Write a .desktop Linux internet shortcut')

    extractor = optparse.OptionGroup(parser, 'Extractor Options')
    extractor.add_option(
        '--extractor-retries',
        dest='extractor_retries', metavar='RETRIES', default=3,
        help='Number of retries for known extractor errors (default is %default), or "infinite"')
    extractor.add_option(
        '--allow-dynamic-mpd', '--no-ignore-dynamic-mpd',
        action='store_true', dest='dynamic_mpd', default=True,
        help='Process dynamic DASH manifests (default) (Alias: --no-ignore-dynamic-mpd)')
    extractor.add_option(
        '--ignore-dynamic-mpd', '--no-allow-dynamic-mpd',
        action='store_false', dest='dynamic_mpd',
        help='Do not process dynamic DASH manifests (Alias: --no-allow-dynamic-mpd)')
    extractor.add_option(
        '--hls-split-discontinuity',
        dest='hls_split_discontinuity', action='store_true', default=False,
        help='Split HLS playlists to different formats at discontinuities such as ad breaks'
    )
    extractor.add_option(
        '--no-hls-split-discontinuity',
        dest='hls_split_discontinuity', action='store_false',
        help='Do not split HLS playlists to different formats at discontinuities such as ad breaks (default)')
    _extractor_arg_parser = lambda key, vals='': (key.strip().lower().replace('-', '_'), [val.strip() for val in vals.split(',')])
    extractor.add_option(
        '--extractor-args',
        metavar='KEY:ARGS', dest='extractor_args', default={}, type='str',
        action='callback', callback=_dict_from_options_callback,
        callback_kwargs={
            'multiple_keys': False,
            'process': lambda val: dict(
                _extractor_arg_parser(*arg.split('=', 1)) for arg in val.split(';'))
        }, help=(
            'Pass these arguments to the extractor. See "EXTRACTOR ARGUMENTS" for details. '
            'You can use this option multiple times to give arguments for different extractors'))
    extractor.add_option(
        '--youtube-include-dash-manifest', '--no-youtube-skip-dash-manifest',
        action='store_true', dest='youtube_include_dash_manifest', default=True,
        help=optparse.SUPPRESS_HELP)
    extractor.add_option(
        '--youtube-skip-dash-manifest', '--no-youtube-include-dash-manifest',
        action='store_false', dest='youtube_include_dash_manifest',
        help=optparse.SUPPRESS_HELP)
    extractor.add_option(
        '--youtube-include-hls-manifest', '--no-youtube-skip-hls-manifest',
        action='store_true', dest='youtube_include_hls_manifest', default=True,
        help=optparse.SUPPRESS_HELP)
    extractor.add_option(
        '--youtube-skip-hls-manifest', '--no-youtube-include-hls-manifest',
        action='store_false', dest='youtube_include_hls_manifest',
        help=optparse.SUPPRESS_HELP)

    parser.add_option_group(general)
    parser.add_option_group(network)
    parser.add_option_group(geo)
    parser.add_option_group(selection)
    parser.add_option_group(filesystem)
    parser.add_option_group(thumbnail)
    parser.add_option_group(link)
    parser.add_option_group(verbosity)
    parser.add_option_group(workarounds)
    parser.add_option_group(video_format)
    parser.add_option_group(subtitles)
    parser.add_option_group(authentication)
    parser.add_option_group(extractor)

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
            if opts.config_location is not None:
                location = compat_expanduser(opts.config_location)
                if os.path.isdir(location):
                    location = os.path.join(location, 'yt-dlp.conf')
                if not os.path.exists(location):
                    parser.error('config-location %s does not exist.' % location)
                config = _readOptions(location, default=None)
                if config:
                    configs['custom'], paths['config'] = config, location

            if opts.ignoreconfig:
                return
            if parser.parse_args(configs['custom'])[0].ignoreconfig:
                return
            if read_options('portable', get_executable_path()):
                return
            opts, _ = parser.parse_args(configs['portable'] + configs['custom'] + configs['command-line'])
            if read_options('home', expand_path(opts.paths.get('home', '')).strip()):
                return
            if read_options('system', '/etc'):
                return
            if read_options('user', None, user=True):
                configs['system'], paths['system'] = [], None

        get_configs()
        argv = configs['system'] + configs['user'] + configs['home'] + configs['portable'] + configs['custom'] + configs['command-line']
        opts, args = parser.parse_args(argv)
        if opts.verbose:
            for label in ('Command-line', 'Custom', 'Portable', 'Home', 'User', 'System'):
                key = label.lower()
                if paths.get(key):
                    write_string(f'[debug] {label} config file: {paths[key]}\n')
                if paths.get(key) is not None:
                    write_string(f'[debug] {label} config: {_hide_login_info(configs[key])!r}\n')

    return parser, opts, args
