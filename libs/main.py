# -*- coding: utf-8 -*-
from libs.comedycentral import CC
from libs import addonutils
import xbmc


class ComedyCentral(object):
    LISTITEM = {}

    def __init__(self, listitem=None):
        self.LISTITEM = listitem
        self.cc = CC(listitem)

    def addItems(self, items):
        episodes = False
        tvshows = True
        seasons = True
        for item in items or []:
            episodes = any([item.get('playable'), episodes])
            if item.get('videoInfo'):
                tvshows = all([item['videoInfo'].get('mediatype') == 'tvshow', tvshows])
                seasons = all([item['videoInfo'].get('mediatype') == 'season', seasons])
            else:
                tvshows, seasons = False, False
            addonutils.addListItem(
                label=item.get('label'),
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
                generic = self.cc.genericList(params['name'], params['url'])
                self.addItems(generic)

            elif params['mode'] == 'SEASON':
                show = self.cc.loadShows(params['name'], params['url'], True)
                self.addItems(show)

            elif params['mode'] == 'EPISODES':
                episodes = self.cc.loadItems(params['name'], params['url'])
                self.addItems(episodes)
                addonutils.setContent('episodes')

            elif params['mode'] == 'PLAY':
                if self.cc.PTVL_RUNNING:
                    return addonutils.notify(addonutils.LANGUAGE(30007))
                playItems = self.cc.getMediaUrl(
                    params['name'], params['url'],
                    params.get('mgid'), self.LISTITEM)
                plst = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                plst.clear()
                xbmc.sleep(200)

                for item in playItems:
                    vidIDX = item['idx']
                    liz = addonutils.createListItem(
                        label=item['label'], path=item['url'],
                        videoInfo=item['videoInfos'], subs=item['subs'],
                        isFolder=False)
                    if vidIDX == 0:
                        addonutils.setResolvedUrl(item=liz, exit=False)
                    plst.add(item['url'], liz, vidIDX)
                plst.unshuffle()

        else:
            menu = self.cc.getMainMenu()
            for item in menu or []:
                addonutils.addListItem(
                    item['label'],
                    item['params'],
                    isFolder=True)

        self.cc = None
        addonutils.endScript(exit=False)
