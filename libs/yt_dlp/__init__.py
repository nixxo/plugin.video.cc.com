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
    workaround_optparse_bug9161,
)
from .utils import (
    DownloadError,
    error_to_compat_str,
    ExistingVideoReached,
    MaxDownloadsReached,
    preferredencoding,
    RejectedVideoReached,
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

    # Batch file verification
    batch_urls = []
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

    def parse_retries(retries, name=''):
        if retries in ('inf', 'infinite'):
            parsed_retries = float('inf')
        else:
            try:
                parsed_retries = int(retries)
            except (TypeError, ValueError):
                parser.error('invalid %sretry count specified' % name)
        return parsed_retries

    def validate_outtmpl(tmpl, msg):
        err = YoutubeDL.validate_outtmpl(tmpl)
        if err:
            parser.error('invalid %s %r: %s' % (msg, tmpl, error_to_compat_str(err)))

    any_getting = opts.getfilename or opts.getformat or opts.dumpjson or opts.dump_single_json
    any_printing = opts.print_json

    # If JSON is not printed anywhere, but comments are requested, save it to file
    printing_json = opts.dumpjson or opts.print_json or opts.dump_single_json

    def report_conflict(arg1, arg2):
        warnings.append('%s is ignored since %s was given' % (arg2, arg1))
    
    def report_args_compat(arg, name):
        warnings.append('%s given without specifying name. The arguments will be given to all %s' % (arg, name))

    final_ext = None

    ydl_opts = {
        'quiet': (opts.quiet or any_getting or any_printing),
        'forcefilename': opts.getfilename,
        'forceformat': opts.getformat,
        'forcejson': opts.dumpjson or opts.print_json,
        'dump_single_json': opts.dump_single_json,
        'skip_download': opts.skip_download,
        'format': opts.format,
        'listformats': opts.listformats,
        'ignoreerrors': opts.ignoreerrors,
        'logtostderr': True,
        'verbose': opts.verbose,
        'final_ext': final_ext,
        'warnings': warnings,
    }

    with YoutubeDL(ydl_opts) as ydl:
        actual_use = len(all_urls) or opts.load_info_filename

        # Maybe do nothing
        if not actual_use:
            ydl.warn_if_short_id(sys.argv[1:] if argv is None else argv)
            parser.error(
                'You must provide at least one URL.\n'
                'Type yt-dlp --help to see a list of all options.')

        try:
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
