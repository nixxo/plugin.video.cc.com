# -*- coding: utf-8 -*-
import datetime
import re
import json
import urllib.request as urllib2
import xbmcgui

from simplecache import SimpleCache

from libs import addonutils


class CC(object):
    TIMEOUT = 15
    QUALITY = addonutils.getSettingAsInt('Quality')
    QUALITIES = [360, 540, 720, 1080, 9999]
    DEBUG = addonutils.getSettingAsBool('Debug')
    LOGLEVEL = addonutils.getSettingAsInt('LogLevel')
    PTVL_RUNNING = xbmcgui.Window(10000).getProperty('PseudoTVRunning') == 'True'
    ICON = addonutils.ADDON.getAddonInfo('icon')
    FANART = addonutils.ADDON.getAddonInfo('fanart')
    BASE_URL = 'https://www.cc.com'
    MAIN_MENU = [{
        'label': addonutils.LANGUAGE(31000),
        'params': {
            'url': BASE_URL + '/shows',
            'mode': 'SHOWS',
        },
    }, {
        'label': addonutils.LANGUAGE(31001),
        'params': {
            'url': BASE_URL + '/topic/stand-up',
            'mode': 'GENERIC',
            'name': addonutils.LANGUAGE(31001),
        },
    }, {
        'label': addonutils.LANGUAGE(31002),
        'params': {
            'url': BASE_URL + '/topic/digital-originals',
            'mode': 'GENERIC',
            'name': addonutils.LANGUAGE(31002),
        },
    },
    ]
    PAGES_CRUMB = ['topic', 'collections', 'shows']
    BASE_MGID = 'mgid:arc:video:comedycentral.com:'

    def __init__(self):
        self.log('__init__')
        self.cache = SimpleCache()

    def log(self, msg, level=0):
        if level >= self.LOGLEVEL:
            addonutils.log(msg, level)

    def openURL(self, url):
        self.log('openURL, url = %s' % url, 1)
        try:
            cacheresponse = self.cache.get(
                '%s.openURL, url = %s' % (addonutils.ID, url))
            if not cacheresponse:
                request = urllib2.Request(url)              
                response = urllib2.urlopen(request, timeout=self.TIMEOUT).read()
                self.cache.set(
                    '%s.openURL, url = %s' % (addonutils.ID, url),
                    response,
                    expiration=datetime.timedelta(days=1))
            return self.cache.get('%s.openURL, url = %s' % (addonutils.ID, url))
        except Exception as e:
            self.log("openURL Failed! " + str(e), 3)
            addonutils.notify(addonutils.LANGUAGE(30003))
            addonutils.endScript()

    def createURL(self, url, fix=False):
        if fix:
            # sometimes cc.com f**ks-up the url
            url = url.replace('/episode/', '/episodes/')

        if url.startswith('http'):
            return url
        return self.BASE_URL + url

    def createInfoArt(self, image=False, fanart=False):
        self.log('createInfoArt, image = %s; fanart = %s' % (str(image), str(fanart)), 1)
        thumb = image + '&width=512&crop=false' if image else None
        return {
            'thumb': thumb,
            'poster': thumb,
            'fanart': (image or thumb) if fanart else self.FANART,
            'icon': self.ICON,
            'logo': self.ICON
        }

    def loadJsonData(self, url):
        self.log('loadJsonData, url = %s' % url, 1)
        response = self.openURL(url)
        if len(response) == 0:
            return
        response = response.decode('utf-8')

        try:
            # try if the file is json
            items = json.loads(response)
        except:
            # file is html
            try:
                src = re.search('window\\.__DATA__\\s*=\\s*(.+?);\\s*window\\.__PUSH_STATE__', response).group(1)
                items = json.loads(src)
            except Exception as e:
                addonutils.notify(addonutils.LANGUAGE(30004))
                self.log('loadJsonData, NO JSON DATA FOUND' + str(e), 3)
                addonutils.endScript()

        return items

    def extractItemType(self, data, type, ext):
        self.log('extractItemType, type = %s; ext = %s' % (type, ext), 1)
        items = [x.get(ext) for x in data if x.get('type') == type]
        return items[0] if len(items) > 0 and isinstance(items[0], list) else items

    def extractItems(self, data):
        '''extract items from the page json'''
        self.log('extractItems')
        items = []
        for item in data or []:
            if item.get('type') == 'LineList':
                items.extend(item['props'].get('items') or [])
                items.extend([item['props'].get('loadMore')] or [])
            if item.get('type') == 'Fragment':
                items.extend(self.extractItems(item.get('children')) or [])
        self.log('extractItems, items extracted = %d' % len(items), 1)
        return items

    def getMainMenu(self):
        self.log('getMainMenu', 1)
        return self.MAIN_MENU

    def showsList(self, url):
        self.log('showsList, url = %s' % url, 1)
        items = self.loadJsonData(url)
        if 'items' in items:
            items['items'].extend([items.get('loadMore')] or [])
            items = items['items']
        else:
            items = self.extractItemType(
                items.get('children') or [],
                'MainContainer',
                'children')
            items = self.extractItems(items)

        for item in items:
            if 'loadingTitle' in item:
                yield {
                    'label': item['title'],
                    'params': {
                        'mode': 'SHOWS',
                        'url': self.createURL(item['url'])
                    },
                }
            else:
                label = item['meta']['header']['title']
                yield {
                    'label': label,
                    'params': {
                        'mode': 'GENERIC',
                        'url': self.createURL(item['url']),
                        'name': label,
                    },
                    'videoInfo': {
                        'mediatype': 'tvshow',
                        'title': label,
                        'tvshowtitle': label,
                    },
                    'arts': self.createInfoArt(item['media']['image']['url'], False),
                }

    def genericList(self, name, url):
        self.log('genericList, name = %s, url = %s' % (name, url), 1)
        try:
            mtc = re.search(r'(/%s/)' % '/|/'.join(self.PAGES_CRUMB), url).group(1)
            name_of_method = "load%s" % mtc.strip('/').capitalize()
            method = getattr(self, name_of_method)
            self.log('genericList, using method = %s' % str(method))
            yield from method(name, url)
        except:
            addonutils.notify(addonutils.LANGUAGE(30005))
            self.log('genericList, URL not supported: %s' % url, 3)
            addonutils.endScript()

    def loadShows(self, name, url, season=False):
        self.log('loadShows, name = %s, url = %s, season = %s' % (
            name, url, str(season)), 1)
        items = self.loadJsonData(url)
        if not season:
            items = self.extractItemType(
                items.get('children') or [], 'MainContainer', 'children')
            items = self.extractItemType(items, 'SeasonSelector', 'props')
            # check if no season selector is present
            # or season selector is empty
            if len(items) == 0 or (
                    len(items[0]['items']) == 1 and not items[0]['items'][0].get('url')):
                # and load directly the show
                yield from self.loadShows(name, url, True)
                return
        else:
            items = self.extractItemType(
                items.get('children') or [], 'MainContainer', 'children')
            items = self.extractItemType(items, 'LineList', 'props')
            items = self.extractItemType(items, 'video-guide', 'filters')
        
        items = items[0]['items']
        # check if there is only one item
        if len(items) == 1:
            # and load it directly
            yield from self.loadItems(
                name, self.createURL(items[0].get('url') or url))
        else:
            for item in items:
                label = item['label']
                yield {
                    'label': label,
                    'params': {
                        'mode': 'EPISODES' if season else 'SEASON',
                        'url': self.createURL(item.get('url') or url),
                        'name': name,
                    },
                    'videoInfo': {
                        'mediatype': 'season' if re.search(r'season\s\d+', label, re.IGNORECASE) else 'video',
                        'title': label,
                        'tvshowtitle': name
                    },
                    'arts': self.createInfoArt(),
                }

    def loadItems(self, name, url):
        self.log('loadItems, name = %s, url = %s' % (name, url))
        items = self.loadJsonData(url)
        
        for item in items.get('items') or []:
            if item.get('cardType') == 'ad':
                continue
            try:
                sub = item['meta'].get('subHeader')
                if isinstance(item['meta']['header']['title'], str):
                    label = item['meta']['header']['title']
                else:
                    label = item['meta']['header']['title'].get('text') or ''
                label = '%s - %s' % (label, sub) if sub else label
            except:
                label = 'NO TITLE'
            try:
                season, episode = re.search(
                    r'season\s*(\d+)\s*episode\s*(\d+)\s*',
                    item['meta']['itemAriaLabel'],
                    re.IGNORECASE).groups()
            except:
                season, episode = None, None

            yield {
                'label': label,
                'params': {
                    'mode': 'PLAY',
                    'url': self.createURL(item['url']),
                    'name': label,
                    'mgid': item.get('mgid') or item.get('id'),
                },
                'videoInfo': {
                    'mediatype': 'episode' if episode else 'video',
                    'title': sub or label,
                    'tvshowtitle': name,
                    'plot': item['meta']['description'],
                    'season': season,
                    'episode': episode,
                },
                'arts': self.createInfoArt(item['media']['image']['url']),
                'playable': True,
            }

        if items.get('loadMore'):
            yield {
                'label': addonutils.LANGUAGE(31005),
                'params': {
                    'mode': 'EPISODES',
                    # replace necessary to urlencode only ":"
                    'url': self.createURL(
                        items['loadMore']['url'].replace(':', '%3A')),
                    'name': name,
                },
                'videoInfo': {
                    'tvshowtitle': name
                },
                'arts': self.createInfoArt(),
            }

    def loadCollections(self, name, url):
        yield from self.loadTopic(name, url)
        pass

    def loadTopic(self, name, url):
        self.log('loadTopic, name = %s, url = %s' % (name, url))
        items = self.loadJsonData(url)
        items = self.extractItemType(
            items.get('children') or [],
            'MainContainer',
            'children')
        items = self.extractItems(items)

        for item in items:
            if not item:
                continue
            if item.get('title') == 'Load More':
                label = addonutils.LANGUAGE(31005)
                yield {
                    'label': label,
                    'params': {
                        'mode': 'EPISODES',
                        'url': self.createURL(item['url']),
                        'name': name,
                    },
                    'videoInfo': {
                        'tvshowtitle': name
                    },
                    'arts': self.createInfoArt(),
                }

            if item.get('cardType') not in ['series', 'episode', 'promo']:
                continue
            label = item['title']
            playable = not any(('/%s/' % x) in item['url'] for x in self.PAGES_CRUMB)
            yield {
                'label': label,
                'params': {
                    'mode': 'PLAY' if playable else 'GENERIC',
                    'url': self.createURL(item['url'], fix=playable),
                    'name': label,
                },
                'videoInfo': {
                    'mediatype': 'video' if playable else 'tvshow',
                    'title': label,
                    'tvshowtitle': item['meta']['label'],
                },
                'arts': self.createInfoArt(item['media']['image']['url']),
                'playable': playable,
            }

    def getMediaUrl(self, name, url, mgid=None):
        from libs import yt_dlp

        self.log('getMediaUrl, url=%s, mgid=%s' % (url, str(mgid)))
        self.log('yt-dlp version: %s' % yt_dlp.version.__version__)
        if mgid and not mgid.startswith('mgid'):
            mgid = self.BASE_MGID + mgid
        ydl = yt_dlp.YoutubeDL({
            'skip_download': True,
            'quiet': True
        })
        info = ydl.extract_info(mgid or url)
        if info is None:
            addonutils.notify(addonutils.LANGUAGE(30007))
            self.log('getPlayItems, ydl.extract_info=None', 3)
            addonutils.endScript(exit=False)
        if info.get('_type') != 'playlist':
            addonutils.notify('_type not supported. See log.')
            self.log('getPlayItems, info type <%s> not supported' % info['_type'], 3)
            addonutils.endScript(exit=False)
        info = info.get('entries') or []
        for video in info:
            vidIDX = video.get('playlist_index') or video.get('playlist_autonumber')
            label = '%s - Act %d' % (name, vidIDX)
            if len(info) == 1:
                label = name
            subs = None
            try:
                if 'subtitles' in video:
                    subs = [x['url'] for x in video['subtitles'].get('en', '') if 'url' in x and x['ext'] == 'vtt']
            except:
                pass

            max_height = self.QUALITIES[self.QUALITY]
            for i in range(len(video.get('formats'))-1, 0, -1):
                if video['formats'][i].get('height') <= max_height:
                    self.log('getPlaylistContent, quality_found = %s' % video['formats'][i].get('format_id'))
                    yield {
                        'idx': vidIDX-1,
                        'url': video['formats'][i].get('url'),
                        'label': label,
                        'videoInfos': {
                            'mediatype': 'video',
                            'title': label,
                        },
                        'subs': subs,
                    }
                    break
