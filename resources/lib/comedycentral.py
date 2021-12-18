# -*- coding: utf-8 -*-
import datetime
import re
import json
import urllib.request as urllib2

from simplecache import SimpleCache

from resources.lib import addonutils
from resources.lib.translate import translatedString as T


TIMEOUT = 15
QUALITY = addonutils.getSettingAsInt('Quality')
QUALITIES = [360, 540, 720, 1080, 9999]
DEVMODE = addonutils.getSettingAsBool('DevMode')
BASE_URL = 'https://www.cc.com'
BASE_MGID = 'mgid:arc:video:comedycentral.com:'
PAGES_CRUMB = ['topic', 'collections', 'shows']
LANG = addonutils.LANGUAGE
MAIN_MENU = [{
    'label': T('shows'),
    'params': {
        'url': BASE_URL + '/api/shows/1/40',
        'mode': 'SHOWS',
    },
}, {
    'label': T('full.episodes'),
    'params': {
        'url': BASE_URL + '/api/episodes/1/20',
        'mode': 'EPISODES',
        'name': T('full.episodes'),
    },
}, {
    'label': T('standup'),
    'params': {
        'url': BASE_URL + '/topic/stand-up',
        'mode': 'GENERIC',
        'name': T('standup'),
    },
}, {
    'label': T('digital.original'),
    'params': {
        'url': BASE_URL + '/topic/digital-originals',
        'mode': 'GENERIC',
        'name': T('digital.original'),
    },
}]


class CC(object):

    def __init__(self):
        self._log('__init__')
        self.cache = SimpleCache()

    def _log(self, msg, level=0):
        """
        Log message
        If DEVMODE is enabled, all debug messages are raised to INFO,
        so everithing from the plugin is visible without
        activating Debug Log in Kodi.

        :param      msg:    The message
        :type       msg:    str
        :param      level:  loglevel
        :type       level:  int
        """
        if DEVMODE:
            addonutils.log(msg, 1 if level == 0 else level)
        elif level >= 3:
            addonutils.log(msg, level)

    def _openURL(self, url, hours=24):
        """
        Get url content from the web or from the cache.

        :param      url:    The url
        :type       url:    str
        :param      hours:  cache retention time
        :type       hours:  int

        :returns:   url content
        :rtype:     str
        """
        self._log('_openURL, url = %s' % url, 1)
        try:
            cacheresponse = self.cache.get(
                '%s_openURL[%s]' % (addonutils.ID, url))
            if not cacheresponse:
                request = urllib2.Request(url)
                response = urllib2.urlopen(request, timeout=TIMEOUT).read()
                self.cache.set(
                    '%s_openURL[%s]' % (addonutils.ID, url),
                    response,
                    expiration=datetime.timedelta(hours=hours))
            return self.cache.get('%s_openURL[%s]' % (addonutils.ID, url))
        except Exception as e:
            self._log("_openURL Failed! " + str(e), 3)
            addonutils.notify(T('error.openurl'))
            addonutils.endScript()

    def _createURL(self, url, fix=False):
        """
        Check if url is full or only partial

        :param      url:  The url
        :type       url:  str
        :param      fix:  fix the url
        :type       fix:  bool

        :returns:   fixed url
        :rtype:     str
        """
        if fix:
            # sometimes cc.com f**ks-up the url
            url = url.replace('/episode/', '/episodes/')

        if url.startswith('http'):
            return url
        return BASE_URL + url

    def _createInfoArt(self, image=False, fanart=False):
        """
        Create infoart list from provided image url, if provided.

        :param      image:   image url
        :type       image:   str
        :param      fanart:  generate fanart from image url
        :type       fanart:  bool

        :returns:   infoart
        :rtype:     list
        """
        self._log('_createInfoArt, image = %s; fanart = %s' % (str(image), str(fanart)), 1)
        thumb = image + '&width=512&crop=false' if image else None
        return {
            'thumb': thumb,
            'poster': thumb,
            'fanart': (image or thumb) if fanart else addonutils.FANART,
            'icon': addonutils.ICON,
            'logo': addonutils.ICON
        }

    def _loadJsonData(self, url, hours=24):
        """
        Extract the JSON data from the provided url.
        Checks if the url contain html or json

        :param      url:    The url with the data to extract
        :type       url:    str
        :param      hours:  cache retention duration
        :type       hours:  int

        :returns:   Json data extarcted
        :rtype:     json
        """
        self._log('_loadJsonData, url = %s' % url, 1)
        response = self._openURL(url, hours=hours)
        if len(response) == 0:
            return
        response = response.decode('utf-8')

        try:
            # check if the file is json
            items = json.loads(response)
        except:
            # file is html
            try:
                src = re.search('__DATA__\\s*=\\s*(.+?);\\s*window\\.__PUSH_STATE__', response).group(1)
                items = json.loads(src)
            except Exception as e:
                addonutils.notify(T('error.no.json'))
                self._log('_loadJsonData, NO JSON DATA FOUND' + str(e), 3)
                addonutils.endScript()

        return items

    def _extractItemType(self, data, type, ext):
        """
        Search for element with the 'type' provided and return 'ext'
        Eg. return the "children" element of an element with 'type' "MainContent"

        :param      data:  The data
        :type       data:  json
        :param      type:  'type' key to search
        :type       type:  str
        :param      ext:   'ext' key to extract
        :type       ext:   str

        :returns:   extracted data
        :rtype:     json
        """
        self._log('_extractItemType, type = %s; ext = %s' % (type, ext), 1)
        items = [x.get(ext) for x in data if x.get('type') == type]
        return items[0] if len(items) > 0 and isinstance(items[0], list) else items

    def _extractItems(self, data):
        """
        extract items from the json data

        :param      data:  The data
        :type       data:  json

        :returns:   items extracted
        :rtype:     list
        """
        self._log('_extractItems')
        items = []
        for item in data or []:
            if item.get('type') == 'LineList':
                items.extend(item['props'].get('items') or [])
                items.extend([item['props'].get('loadMore')] or [])
            if item.get('type') == 'Fragment':
                items.extend(self._extractItems(item.get('children')) or [])
        self._log('_extractItems, items extracted = %d' % len(items), 1)
        return items

    def _getDuration(self, duration):
        """
        Parse the duration in format [hh:]mm:ss and return in seconds

        :param      duration:  The duration
        :type       duration:  int
        """
        try:
            hh, mm, ss = re.match(r'(?:(\d+):)?(\d+):(\d+)', duration).groups()
        except:
            hh, mm, ss = '0,0,0'.split(',')
        return int(hh or 0) * 3600 + int(mm or 0) * 60 + int(ss or 0)

    def _getDate(self, date):
        """
        Parses the date in the format MM/DD/YYYY and returns it in
        the format YYYY-MM-DD

        :param      date:  The date
        :type       date:  str
        """
        try:
            mm, dd, yy = re.match(r'(\d{2})/(\d{2})/(\d{4})', date).groups()
        except:
            mm, dd, yy = '01,01,2000'.split(',')
        return '%s-%s-%s' % (yy, mm, dd)

    def getMainMenu(self):
        """
        Returns the main menu

        :returns:   main menu
        :rtype:     json
        """
        self._log('getMainMenu', 1)
        return MAIN_MENU

    def showsList(self, url):
        """
        Generates a list of the TV Shows found at the provided url

        :param      url:  The url
        :type       url:  str

        :returns:   listitem items
        :rtype:     dict
        """
        self._log('showsList, url = %s' % url, 1)
        items = self._loadJsonData(url)
        if 'items' in items:
            items['items'].extend([items.get('loadMore')] or [])
            items = items['items']
        else:
            items = self._extractItemType(
                items.get('children') or [],
                'MainContainer',
                'children')
            items = self._extractItems(items)

        for item in items:
            if 'loadingTitle' in item:
                # NEXT PAGE
                yield {
                    'label': T('load.more'),
                    'params': {
                        'mode': 'SHOWS',
                        'url': self._createURL(item['url'])
                    },
                }
            else:
                label = item['meta']['header']['title']
                yield {
                    'label': label,
                    'params': {
                        'mode': 'GENERIC',
                        'url': self._createURL(item['url']),
                        'name': label,
                    },
                    'videoInfo': {
                        'mediatype': 'tvshow',
                        'title': label,
                        'tvshowtitle': label,
                    },
                    'arts': self._createInfoArt(item['media']['image']['url'], False),
                }

    def genericList(self, name, url):
        """
        Checks the url and chooses the appropriate method to parse the content.
        Based on the PAGES_CRUMB it yields data from the corresponding loadXXX.

        loadShows
        loadCollections (same as Topic)
        loadTopic

        :param      name:  title of the url provided
        :type       name:  str
        :param      url:   url to process
        :type       url:   str
        """
        self._log('genericList, name = %s, url = %s' % (name, url), 1)
        try:
            mtc = re.search(r'(/%s/)' % '/|/'.join(PAGES_CRUMB), url).group(1)
            name_of_method = "load%s" % mtc.strip('/').capitalize()
            method = getattr(self, name_of_method)
            self._log('genericList, using method = %s' % str(method))
            yield from method(name, url)
        except:
            addonutils.notify(T('error.openurl'))
            self._log('genericList, URL not supported: %s' % url, 3)
            addonutils.endScript()

    def loadShows(self, name, url, season=False):
        self._log('loadShows, name = %s, url = %s, season = %s' % (
            name, url, str(season)), 1)
        items = self._loadJsonData(url)
        if not season:
            items = self._extractItemType(
                items.get('children') or [], 'MainContainer', 'children')
            items = self._extractItemType(items, 'SeasonSelector', 'props')
            # check if no season selector is present
            # or season selector is empty
            if len(items) == 0 or (
                    len(items[0]['items']) == 1 and not items[0]['items'][0].get('url')):
                # and load directly the show
                yield from self.loadShows(name, url, True)
                return
        else:
            items = self._extractItemType(
                items.get('children') or [], 'MainContainer', 'children')
            items = self._extractItemType(items, 'LineList', 'props')
            items = self._extractItemType(items, 'video-guide', 'filters')

        items = items[0].get('items')
        # check if there is only one item
        if len(items) == 1:
            # and load it directly
            yield from self.loadItems(
                name, self._createURL(items[0].get('url') or url))
        else:
            for item in items:
                label = item['label']
                yield {
                    'label': label,
                    'params': {
                        'mode': 'EPISODES' if season else 'SEASON',
                        'url': self._createURL(item.get('url') or url),
                        'name': name,
                    },
                    'videoInfo': {
                        'mediatype': 'season' if re.search(r'season\s\d+', label, re.IGNORECASE) else 'video',
                        'title': label,
                        'tvshowtitle': name
                    },
                    'arts': self._createInfoArt(),
                }

    def loadCollections(self, name, url):
        """ Collections page are the same as topic pages """
        yield from self.loadTopic(name, url)
        pass

    def loadTopic(self, name, url):
        """
        Loads data from 'topic' pages.

        :param      name:  Title of the page
        :type       name:  str
        :param      url:   The url
        :type       url:   str
        """
        self._log('loadTopic, name = %s, url = %s' % (name, url))
        items = self._loadJsonData(url)
        items = self._extractItemType(
            items.get('children') or [],
            'MainContainer',
            'children')

        for item in self._extractItems(items) or []:
            if not item:
                continue
            if item.get('title') == 'Load More':
                label = T('load.more')
                yield {
                    'label': label,
                    'params': {
                        'mode': 'EPISODES',
                        'url': self._createURL(item['url']),
                        'name': name,
                    },
                    'arts': self._createInfoArt(),
                }

            # skip non necessary elements, like ADS and others
            if item.get('cardType') not in ['series', 'episode', 'promo']:
                continue

            # skip 'promo' items in Digital Original listing
            # as they are duplicates of something already in the list
            if name == T('digital.original') and item.get('cardType') == 'promo':
                continue

            if not item.get('url') or not item.get('title'):
                continue

            label = item['title']
            # playable is determined by the url not being in the parsable pages
            playable = not any(('/%s/' % x) in item['url'] for x in PAGES_CRUMB)
            infos = {
                'label': label,
                'params': {
                    'mode': 'PLAY' if playable else 'GENERIC',
                    'url': self._createURL(item['url'], fix=playable),
                    'name': label,
                },
                'videoInfo': {
                    'mediatype': 'video' if playable else 'tvshow',
                    'title': label,
                    'tvshowtitle': item['meta']['label'],
                    'duration': self._getDuration(item['media'].get('duration')),
                },
                'arts': self._createInfoArt(item['media']['image']['url']),
                'playable': playable,
            }
            if playable:
                self.cache.set(
                    '%s_videoInfo[%s]' % (addonutils.ID, infos['params']['url']), infos['videoInfo'],
                    expiration=datetime.timedelta(hours=2), json_data=True)
            yield infos

    def loadItems(self, name, url):
        """
        Generate a list of playable items from the provided url

        :param      name:  The name
        :type       name:  str
        :param      url:   The url
        :type       url:   str

        :returns:   items
        :rtype:     list
        """
        self._log('loadItems, name = %s, url = %s' % (name, url))
        items = self._loadJsonData(url, hours=1)

        for item in items.get('items') or []:
            if item.get('cardType') == 'ad':
                continue
            meta = item.get('meta')
            try:
                sub = meta.get('subHeader')
                if isinstance(meta['header']['title'], str):
                    label = meta['header']['title']
                else:
                    label = meta['header']['title'].get('text') or ''
                label = '%s - %s' % (label, sub) if sub else label
            except:
                label = 'NO TITLE'
            try:
                season, episode = re.search(
                    r'season\s*(\d+)\s*episode\s*(\d+)\s*',
                    meta.get('itemAriaLabel') or meta.get('ariaLabel'),
                    re.IGNORECASE).groups()
            except:
                season, episode = None, None

            tvshowtitle = meta.get('label') if name == 'None' else name
            infos = {
                'label': label,
                'params': {
                    'mode': 'PLAY',
                    'url': self._createURL(item['url']),
                    'name': sub or label,
                    'mgid': item.get('mgid') or item.get('id'),
                },
                'videoInfo': {
                    'mediatype': 'episode' if episode else 'video',
                    'title': sub or label,
                    'tvshowtitle': tvshowtitle,
                    'plot': meta.get('description'),
                    'season': season,
                    'episode': episode,
                    'duration': self._getDuration(item['media'].get('duration')),
                    'aired': self._getDate(meta.get('date')),
                },
                'arts': self._createInfoArt(item['media']['image']['url']),
                'playable': True,
            }
            self.cache.set(
                '%s_videoInfo[%s]' % (addonutils.ID, infos['params']['url']),
                infos['videoInfo'],
                expiration=datetime.timedelta(hours=2), json_data=True)
            yield infos

        if items.get('loadMore'):
            yield {
                'label': T('load.more'),
                'params': {
                    'mode': 'EPISODES',
                    # replace necessary to urlencode only ":"
                    'url': self._createURL(items['loadMore']['url'].replace(':', '%3A')),
                    'name': name,
                },
                'videoInfo': {
                    'tvshowtitle': name
                },
                'arts': self._createInfoArt(),
            }

    def getMediaUrl(self, name, url, mgid=None, select_quality=False):
        """
        Retrive media urls with yt-dlp for the provided url or mgid

        :param      name:      Title
        :type       name:      str
        :param      url:       The url
        :type       url:       str
        :param      mgid:      The mgid
        :type       mgid:      str

        :returns:   playable urls
        :rtype:     list
        """
        from resources.lib import yt_dlp

        self._log('getMediaUrl, url=%s, mgid=%s' % (url, str(mgid)))
        self._log('yt-dlp version: %s' % yt_dlp.version.__version__)
        if mgid and not mgid.startswith('mgid'):
            mgid = BASE_MGID + mgid

        ytInfo = self.cache.get(
            '%s_ytInfo[%s]' % (addonutils.ID, mgid or url))
        videoInfo = self.cache.get(
            '%s_videoInfo[%s]' % (addonutils.ID, url), json_data=True
            ) or {}

        if not ytInfo:
            try:
                ytInfo = yt_dlp.YoutubeDL().extract_info(mgid or url)
                self.cache.set(
                    '%s_ytInfo[%s]' % (addonutils.ID, mgid or url), ytInfo,
                    expiration=datetime.timedelta(hours=2))
            except:
                ytInfo = None

        if ytInfo is None:
            addonutils.notify(T('error.no.video'))
            self._log('getMediaUrl, ydl.extract_info=None', 3)
            addonutils.endScript(exit=False)
        if ytInfo.get('_type') != 'playlist':
            addonutils.notify(T('error.wrong.type'))
            self._log('getPlayItems, info type <%s> not supported' % ytInfo['_type'], 3)
            addonutils.endScript(exit=False)

        for video in ytInfo.get('entries') or []:
            vidIDX = video.get('playlist_index') or video.get('playlist_autonumber')
            label = '%s - Act %d' % (name, vidIDX)
            # if video is single do not add Act X to the title
            if video.get('n_entries') == 1:
                label = name
            subs = None
            try:
                if 'subtitles' in video:
                    subs = [x['url'] for x in video['subtitles'].get('en', '')
                            if 'url' in x and x['ext'] == 'vtt']
            except:
                pass

            infos = {
                'idx': vidIDX-1,
                'url': video.get('url'),
                'label': label,
                'videoInfo': videoInfo,
                'subs': subs,
                'arts': {
                    'thumb': video.get('thumbnail'),
                },
            }
            infos['videoInfo'].update({
                'title': label,
                'duration': video.get('duration'),
            })

            if select_quality:
                max_height = QUALITIES[QUALITY]
                for i in range(len(video.get('formats'))-1, 0, -1):
                    if video['formats'][i].get('height') <= max_height:
                        self._log('getPlaylistContent, quality_found = %s' % video['formats'][i].get('format_id'))
                        infos['url'] = video['formats'][i].get('url')
                        break
            yield infos
