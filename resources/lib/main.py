# -*- coding: utf-8 -*-
from resources.lib import addonutils
from resources.lib.comedycentral import CC
import xbmc


class ComedyCentral(object):

    def __init__(self):
        self.cc = CC()
        self._ISA = addonutils.getSettingAsBool('UseInputStream')
        self._FISA = addonutils.getSettingAsBool('ForceInputstream')

    def addItems(self, items):
        episodes = True
        tvshows = True
        seasons = True
        for item in items or []:
            episodes = all([item.get('playable'), episodes])
            if item.get('videoInfo'):
                tvshows = all([item['videoInfo'].get('mediatype') == 'tvshow', tvshows])
                seasons = all([item['videoInfo'].get('mediatype') == 'season', seasons])
            else:
                tvshows, seasons = False, False
            addonutils.addListItem(
                label=item.get('label'),
                label2=item.get('label2'),
                params=item.get('params'),
                arts=item.get('arts'),
                videoInfo=item.get('videoInfo'),
                isFolder=False if item.get('playable') else True,
            )
        if tvshows:
            addonutils.setContent('tvshows')
        elif seasons:
            addonutils.setContent('seasons')
        elif episodes:
            addonutils.setContent('episodes')

    def main(self):
        params = addonutils.getParams()
        if 'mode' in params:
            if params['mode'] == 'SHOWS':
                shows = self.cc.showsList(params['url'])
                self.addItems(shows)
                addonutils.setContent('tvshows')

            elif params['mode'] == 'GENERIC':
                generic = self.cc.genericList(params.get('name'), params['url'])
                self.addItems(generic)

            elif params['mode'] == 'SEASON':
                show = self.cc.loadShows(params.get('name'), params['url'], True)
                self.addItems(show)

            elif params['mode'] == 'EPISODES':
                episodes = self.cc.loadItems(params.get('name'), params['url'])
                self.addItems(episodes)
                addonutils.setContent('episodes')

            elif params['mode'] == 'PLAY':
                select_quality = not self._ISA or (self._ISA and self._FISA)
                playItems = self.cc.getMediaUrl(
                    params['name'], params['url'],
                    params.get('mgid'), select_quality)
                plst = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                plst.clear()
                xbmc.sleep(200)

                for item in playItems:
                    vidIDX = item['idx']
                    liz = addonutils.createListItem(
                        label=item['label'], path=item['url'],
                        videoInfo=item['videoInfo'], subs=item.get('subs'),
                        arts=item.get('arts'), isFolder=False)
                    if self._ISA:
                        import inputstreamhelper
                        is_helper = inputstreamhelper.Helper('hls')
                        if is_helper.check_inputstream():
                            liz.setContentLookup(False)
                            liz.setMimeType('application/vnd.apple.mpegurl')
                            liz.setProperty('inputstream', is_helper.inputstream_addon)
                            liz.setProperty('inputstream.adaptive.manifest_type', 'hls')
                    if vidIDX == 0:
                        addonutils.setResolvedUrl(item=liz, exit=False)
                    plst.add(item['url'], liz, vidIDX)
                plst.unshuffle()

        else:
            menu = self.cc.getMainMenu()
            self.addItems(menu)

        self.cc = None
        addonutils.endScript(exit=False)
