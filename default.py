# coding: utf-8
# author: nixxo
import xbmc
from libs.main import ComedyCentral


def get_cur_listitem():
    """
    Gets the current selected listitem details
    Taken from script.skin.helper.service infodialog.py

    :returns:   listitem data
    :rtype:     dict
    """
    if xbmc.getCondVisibility("Window.IsActive(busydialog)"):
        xbmc.executebuiltin("Dialog.Close(busydialog)")
        xbmc.sleep(500)
    dbid = xbmc.getInfoLabel("ListItem.DBID")
    if not dbid or dbid == "-1":
        dbid = xbmc.getInfoLabel("ListItem.Property(DBID)")
        if dbid == "-1":
            dbid = ""
    dbtype = xbmc.getInfoLabel("ListItem.DBTYPE")
    if not dbtype:
        dbtype = xbmc.getInfoLabel("ListItem.Property(DBTYPE)")

    plot = xbmc.getInfoLabel("ListItem.Plot")
    if not plot:
        dbtype = xbmc.getInfoLabel("ListItem.Property(Plot)")

    return {
        'DBID': dbid,
        'DBTYPE': dbtype,
        'PLOT': plot,
    }


listitem = get_cur_listitem()
cc = ComedyCentral(listitem)
cc.main()
