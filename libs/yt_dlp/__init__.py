#!/usr/bin/env python3
# coding: utf-8

f'You are using an unsupported version of Python. Only Python versions 3.6 and above are supported by yt-dlp'  # noqa: F541

__license__ = 'Public Domain'

import codecs
import io
import os
import random
import re
import sys

from .options import (
    parseOpts,
)
from .compat import (
    compat_getpass,
    workaround_optparse_bug9161,
)
from .utils import (
    DateRange,
    decodeOption,
    DownloadError,
    error_to_compat_str,
    ExistingVideoReached,
    expand_path,
    match_filter_func,
    MaxDownloadsReached,
    preferredencoding,
    read_batch_urls,
    RejectedVideoReached,
    render_table,
    SameFileError,
    setproctitle,
    std_headers,
    write_string,
)
from .extractor import gen_extractors, list_extractors
from .extractor.common import InfoExtractor

from .YoutubeDL import YoutubeDL


def _real_main(argv=None):
    # Compatibility fixes for Windows
    if sys.platform == 'win32':
        # https://github.com/ytdl-org/youtube-dl/issues/820
        codecs.register(lambda name: codecs.lookup('utf-8') if name == 'cp65001' else None)

    workaround_optparse_bug9161()

    setproctitle('yt-dlp')

    parser, opts, args = parseOpts(argv)
    warnings = []

    # Set user agent
    if opts.user_agent is not None:
        std_headers['User-Agent'] = opts.user_agent

    # Set referer
    if opts.referer is not None:
        std_headers['Referer'] = opts.referer

    # Custom HTTP headers
    std_headers.update(opts.headers)

    # Dump user agent
    if opts.dump_user_agent:
        write_string(std_headers['User-Agent'] + '\n', out=sys.stdout)
        sys.exit(0)

    # Batch file verification
    batch_urls = []
    if opts.batchfile is not None:
        try:
            if opts.batchfile == '-':
                batchfd = sys.stdin
            else:
                batchfd = io.open(
                    expand_path(opts.batchfile),
                    'r', encoding='utf-8', errors='ignore')
            batch_urls = read_batch_urls(batchfd)
            if opts.verbose:
                write_string('[debug] Batch file urls: ' + repr(batch_urls) + '\n')
        except IOError:
            sys.exit('ERROR: batch file %s could not be read' % opts.batchfile)
    all_urls = batch_urls + [url.strip() for url in args]  # batch_urls are already striped in read_batch_urls
    _enc = preferredencoding()
    all_urls = [url.decode(_enc, 'ignore') if isinstance(url, bytes) else url for url in all_urls]

    if opts.list_extractors:
        for ie in list_extractors(opts.age_limit):
            write_string(ie.IE_NAME + (' (CURRENTLY BROKEN)' if not ie.working() else '') + '\n', out=sys.stdout)
            matchedUrls = [url for url in all_urls if ie.suitable(url)]
            for mu in matchedUrls:
                write_string('  ' + mu + '\n', out=sys.stdout)
        sys.exit(0)
    if opts.list_extractor_descriptions:
        for ie in list_extractors(opts.age_limit):
            if not ie.working():
                continue
            desc = getattr(ie, 'IE_DESC', ie.IE_NAME)
            if desc is False:
                continue
            if hasattr(ie, 'SEARCH_KEY'):
                _SEARCHES = ('cute kittens', 'slithering pythons', 'falling cat', 'angry poodle', 'purple fish', 'running tortoise', 'sleeping bunny', 'burping cow')
                _COUNTS = ('', '5', '10', 'all')
                desc += ' (Example: "%s%s:%s" )' % (ie.SEARCH_KEY, random.choice(_COUNTS), random.choice(_SEARCHES))
            write_string(desc + '\n', out=sys.stdout)
        sys.exit(0)

    # Conflicting, missing and erroneous options
    if opts.usenetrc and (opts.username is not None or opts.password is not None):
        parser.error('using .netrc conflicts with giving username/password')
    if opts.password is not None and opts.username is None:
        parser.error('account username missing\n')
    if opts.ap_password is not None and opts.ap_username is None:
        parser.error('TV Provider account username missing\n')
    if opts.autonumber_size is not None:
        if opts.autonumber_size <= 0:
            parser.error('auto number size must be positive')
    if opts.autonumber_start is not None:
        if opts.autonumber_start < 0:
            parser.error('auto number start must be positive or 0')
    if opts.username is not None and opts.password is None:
        opts.password = compat_getpass('Type account password and press [Return]: ')
    if opts.ap_username is not None and opts.ap_password is None:
        opts.ap_password = compat_getpass('Type TV provider account password and press [Return]: ')
    if opts.sleep_interval is not None:
        if opts.sleep_interval < 0:
            parser.error('sleep interval must be positive or 0')
    if opts.max_sleep_interval is not None:
        if opts.max_sleep_interval < 0:
            parser.error('max sleep interval must be positive or 0')
        if opts.sleep_interval is None:
            parser.error('min sleep interval must be specified, use --min-sleep-interval')
        if opts.max_sleep_interval < opts.sleep_interval:
            parser.error('max sleep interval must be greater than or equal to min sleep interval')
    else:
        opts.max_sleep_interval = opts.sleep_interval
    if opts.sleep_interval_subtitles is not None:
        if opts.sleep_interval_subtitles < 0:
            parser.error('subtitles sleep interval must be positive or 0')
    if opts.sleep_interval_requests is not None:
        if opts.sleep_interval_requests < 0:
            parser.error('requests sleep interval must be positive or 0')
    if opts.overwrites:  # --yes-overwrites implies --no-continue
        opts.continue_dl = False

    def parse_retries(retries, name=''):
        if retries in ('inf', 'infinite'):
            parsed_retries = float('inf')
        else:
            try:
                parsed_retries = int(retries)
            except (TypeError, ValueError):
                parser.error('invalid %sretry count specified' % name)
        return parsed_retries

    if opts.playliststart <= 0:
        raise ValueError('Playlist start must be positive')
    if opts.playlistend not in (-1, None) and opts.playlistend < opts.playliststart:
        raise ValueError('Playlist end must be greater than playlist start')

    if opts.date is not None:
        date = DateRange.day(opts.date)
    else:
        date = DateRange(opts.dateafter, opts.datebefore)

    compat_opts = opts.compat_opts

    def _unused_compat_opt(name):
        if name not in compat_opts:
            return False
        compat_opts.discard(name)
        compat_opts.update(['*%s' % name])
        return True

    def set_default_compat(compat_name, opt_name, default=True, remove_compat=True):
        attr = getattr(opts, opt_name)
        if compat_name in compat_opts:
            if attr is None:
                setattr(opts, opt_name, not default)
                return True
            else:
                if remove_compat:
                    _unused_compat_opt(compat_name)
                return False
        elif attr is None:
            setattr(opts, opt_name, default)
        return None

    set_default_compat('abort-on-error', 'ignoreerrors', 'only_download')
    set_default_compat('no-playlist-metafiles', 'allow_playlist_files')
    set_default_compat('no-clean-infojson', 'clean_infojson')
    if 'format-sort' in compat_opts:
        opts.format_sort.extend(InfoExtractor.FormatSort.ytdl_default)
    _video_multistreams_set = set_default_compat('multistreams', 'allow_multiple_video_streams', False, remove_compat=False)
    _audio_multistreams_set = set_default_compat('multistreams', 'allow_multiple_audio_streams', False, remove_compat=False)
    if _video_multistreams_set is False and _audio_multistreams_set is False:
        _unused_compat_opt('multistreams')
    outtmpl_default = opts.outtmpl.get('default')
    if 'filename' in compat_opts:
        if outtmpl_default is None:
            outtmpl_default = '%(title)s-%(id)s.%(ext)s'
            opts.outtmpl.update({'default': outtmpl_default})
        else:
            _unused_compat_opt('filename')

    def validate_outtmpl(tmpl, msg):
        err = YoutubeDL.validate_outtmpl(tmpl)
        if err:
            parser.error('invalid %s %r: %s' % (msg, tmpl, error_to_compat_str(err)))

    for k, tmpl in opts.outtmpl.items():
        validate_outtmpl(tmpl, f'{k} output template')
    opts.forceprint = opts.forceprint or []
    for tmpl in opts.forceprint or []:
        validate_outtmpl(tmpl, 'print template')
    for k, tmpl in opts.progress_template.items():
        k = f'{k[:-6]} console title' if '-title' in k else f'{k} progress'
        validate_outtmpl(tmpl, f'{k} template')

    if outtmpl_default is not None and not os.path.splitext(outtmpl_default)[1] and opts.extractaudio:
        parser.error('Cannot download a video and extract audio into the same'
                     ' file! Use "{0}.%(ext)s" instead of "{0}" as the output'
                     ' template'.format(outtmpl_default))

    for f in opts.format_sort:
        if re.match(InfoExtractor.FormatSort.regex, f) is None:
            parser.error('invalid format sort string "%s" specified' % f)

    any_getting = opts.forceprint or opts.geturl or opts.gettitle or opts.getid or opts.getthumbnail or opts.getdescription or opts.getfilename or opts.getformat or opts.getduration or opts.dumpjson or opts.dump_single_json
    any_printing = opts.print_json
    download_archive_fn = expand_path(opts.download_archive) if opts.download_archive is not None else opts.download_archive

    # If JSON is not printed anywhere, but comments are requested, save it to file
    printing_json = opts.dumpjson or opts.print_json or opts.dump_single_json
    if opts.getcomments and not printing_json:
        opts.writeinfojson = True

    def report_conflict(arg1, arg2):
        warnings.append('%s is ignored since %s was given' % (arg2, arg1))

    if opts.allow_unplayable_formats:
        if opts.extractaudio:
            report_conflict('--allow-unplayable-formats', '--extract-audio')
            opts.extractaudio = False
        if opts.remuxvideo:
            report_conflict('--allow-unplayable-formats', '--remux-video')
            opts.remuxvideo = False
        if opts.recodevideo:
            report_conflict('--allow-unplayable-formats', '--recode-video')
            opts.recodevideo = False
        if opts.addmetadata:
            report_conflict('--allow-unplayable-formats', '--add-metadata')
            opts.addmetadata = False
        if opts.embedsubtitles:
            report_conflict('--allow-unplayable-formats', '--embed-subs')
            opts.embedsubtitles = False
        if opts.embedthumbnail:
            report_conflict('--allow-unplayable-formats', '--embed-thumbnail')
            opts.embedthumbnail = False
        if opts.xattrs:
            report_conflict('--allow-unplayable-formats', '--xattrs')
            opts.xattrs = False
        if opts.fixup and opts.fixup.lower() not in ('never', 'ignore'):
            report_conflict('--allow-unplayable-formats', '--fixup')
        opts.fixup = 'never'
        if opts.remove_chapters:
            report_conflict('--allow-unplayable-formats', '--remove-chapters')
            opts.remove_chapters = []
        opts.sponskrub = False
    
    # --all-sub automatically sets --write-sub if --write-auto-sub is not given
    # this was the old behaviour if only --all-sub was given.
    if opts.allsubtitles and not opts.writeautomaticsub:
        opts.writesubtitles = True

    def report_args_compat(arg, name):
        warnings.append('%s given without specifying name. The arguments will be given to all %s' % (arg, name))

    final_ext = None

    match_filter = (
        None if opts.match_filter is None
        else match_filter_func(opts.match_filter))

    ydl_opts = {
        'usenetrc': opts.usenetrc,
        'netrc_location': opts.netrc_location,
        'username': opts.username,
        'password': opts.password,
        'twofactor': opts.twofactor,
        'videopassword': opts.videopassword,
        'ap_mso': opts.ap_mso,
        'ap_username': opts.ap_username,
        'ap_password': opts.ap_password,
        'quiet': (opts.quiet or any_getting or any_printing),
        'no_warnings': opts.no_warnings,
        'forceurl': opts.geturl,
        'forcetitle': opts.gettitle,
        'forceid': opts.getid,
        'forcethumbnail': opts.getthumbnail,
        'forcedescription': opts.getdescription,
        'forceduration': opts.getduration,
        'forcefilename': opts.getfilename,
        'forceformat': opts.getformat,
        'forceprint': opts.forceprint,
        'forcejson': opts.dumpjson or opts.print_json,
        'dump_single_json': opts.dump_single_json,
        'force_write_download_archive': opts.force_write_download_archive,
        'simulate': (any_getting or None) if opts.simulate is None else opts.simulate,
        'skip_download': opts.skip_download,
        'format': opts.format,
        'allow_unplayable_formats': opts.allow_unplayable_formats,
        'ignore_no_formats_error': opts.ignore_no_formats_error,
        'format_sort': opts.format_sort,
        'format_sort_force': opts.format_sort_force,
        'allow_multiple_video_streams': opts.allow_multiple_video_streams,
        'allow_multiple_audio_streams': opts.allow_multiple_audio_streams,
        'check_formats': opts.check_formats,
        'listformats': opts.listformats,
        'listformats_table': opts.listformats_table,
        'outtmpl': opts.outtmpl,
        'outtmpl_na_placeholder': opts.outtmpl_na_placeholder,
        'paths': opts.paths,
        'autonumber_size': opts.autonumber_size,
        'autonumber_start': opts.autonumber_start,
        'restrictfilenames': opts.restrictfilenames,
        'windowsfilenames': opts.windowsfilenames,
        'ignoreerrors': opts.ignoreerrors,
        'force_generic_extractor': opts.force_generic_extractor,
        'overwrites': opts.overwrites,
        'extractor_retries': opts.extractor_retries,
        'noprogress': opts.quiet if opts.noprogress is None else opts.noprogress,
        'progress_with_newline': opts.progress_with_newline,
        'progress_template': opts.progress_template,
        'playliststart': opts.playliststart,
        'playlistend': opts.playlistend,
        'noplaylist': opts.noplaylist,
        'logtostderr': outtmpl_default == '-',
        'consoletitle': opts.consoletitle,
        'nopart': opts.nopart,
        'updatetime': opts.updatetime,
        'writedescription': opts.writedescription,
        'writeannotations': opts.writeannotations,
        'writeinfojson': opts.writeinfojson,
        'allow_playlist_files': opts.allow_playlist_files,
        'clean_infojson': opts.clean_infojson,
        'getcomments': opts.getcomments,
        'writethumbnail': opts.writethumbnail,
        'write_all_thumbnails': opts.write_all_thumbnails,
        'writelink': opts.writelink,
        'writesubtitles': opts.writesubtitles,
        'writeautomaticsub': opts.writeautomaticsub,
        'allsubtitles': opts.allsubtitles,
        'listsubtitles': opts.listsubtitles,
        'subtitlesformat': opts.subtitlesformat,
        'subtitleslangs': opts.subtitleslangs,
        'matchtitle': decodeOption(opts.matchtitle),
        'rejecttitle': decodeOption(opts.rejecttitle),
        'max_downloads': opts.max_downloads,
        'prefer_free_formats': opts.prefer_free_formats,
        'trim_file_name': opts.trim_file_name,
        'verbose': opts.verbose,
        'dump_intermediate_pages': opts.dump_intermediate_pages,
        'write_pages': opts.write_pages,
        'min_filesize': opts.min_filesize,
        'max_filesize': opts.max_filesize,
        'min_views': opts.min_views,
        'max_views': opts.max_views,
        'daterange': date,
        'cachedir': opts.cachedir,
        'youtube_print_sig_code': opts.youtube_print_sig_code,
        'age_limit': opts.age_limit,
        'download_archive': download_archive_fn,
        'break_on_existing': opts.break_on_existing,
        'break_on_reject': opts.break_on_reject,
        'skip_playlist_after_errors': opts.skip_playlist_after_errors,
        'cookiefile': opts.cookiefile,
        'cookiesfrombrowser': opts.cookiesfrombrowser,
        'nocheckcertificate': opts.no_check_certificate,
        'prefer_insecure': opts.prefer_insecure,
        'proxy': opts.proxy,
        'socket_timeout': opts.socket_timeout,
        'bidi_workaround': opts.bidi_workaround,
        'debug_printtraffic': opts.debug_printtraffic,
        'include_ads': opts.include_ads,
        'default_search': opts.default_search,
        'dynamic_mpd': opts.dynamic_mpd,
        'extractor_args': opts.extractor_args,
        'youtube_include_dash_manifest': opts.youtube_include_dash_manifest,
        'youtube_include_hls_manifest': opts.youtube_include_hls_manifest,
        'encoding': opts.encoding,
        'extract_flat': opts.extract_flat,
        'mark_watched': opts.mark_watched,
        'merge_output_format': opts.merge_output_format,
        'final_ext': final_ext,
        'source_address': opts.source_address,
        'call_home': opts.call_home,
        'sleep_interval_requests': opts.sleep_interval_requests,
        'sleep_interval': opts.sleep_interval,
        'max_sleep_interval': opts.max_sleep_interval,
        'sleep_interval_subtitles': opts.sleep_interval_subtitles,
        'list_thumbnails': opts.list_thumbnails,
        'playlist_items': opts.playlist_items,
        'match_filter': match_filter,
        'no_color': opts.no_color,
        'hls_split_discontinuity': opts.hls_split_discontinuity,
        'cn_verification_proxy': opts.cn_verification_proxy,
        'geo_verification_proxy': opts.geo_verification_proxy,
        'geo_bypass': opts.geo_bypass,
        'geo_bypass_country': opts.geo_bypass_country,
        'geo_bypass_ip_block': opts.geo_bypass_ip_block,
        'warnings': warnings,
        'compat_opts': compat_opts,
    }

    with YoutubeDL(ydl_opts) as ydl:
        actual_use = len(all_urls) or opts.load_info_filename

        # Remove cache dir
        if opts.rm_cachedir:
            ydl.cache.remove()

        # Maybe do nothing
        if not actual_use:
            if opts.update_self or opts.rm_cachedir:
                sys.exit()

            ydl.warn_if_short_id(sys.argv[1:] if argv is None else argv)
            parser.error(
                'You must provide at least one URL.\n'
                'Type yt-dlp --help to see a list of all options.')

        try:
            if opts.load_info_filename is not None:
                retcode = ydl.download_with_info_file(expand_path(opts.load_info_filename))
            else:
                retcode = ydl.download(all_urls)
        except (MaxDownloadsReached, ExistingVideoReached, RejectedVideoReached):
            ydl.to_screen('Aborting remaining downloads')
            retcode = 101

    sys.exit(retcode)


def main(argv=None):
    try:
        _real_main(argv)
    except DownloadError:
        sys.exit(1)
    except SameFileError:
        sys.exit('ERROR: fixed output name but more than one file to download')
    except KeyboardInterrupt:
        sys.exit('\nERROR: Interrupted by user')
    except BrokenPipeError:
        # https://docs.python.org/3/library/signal.html#note-on-sigpipe
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(r'\nERROR: {err}')


__all__ = ['main', 'YoutubeDL', 'gen_extractors', 'list_extractors']
