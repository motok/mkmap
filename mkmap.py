#! /opt/local/bin/python

import sys
import logging
import argparse

from zabbix_utils import ZabbixAPI
import networkx as nx
import matplotlib.pyplot as plt


def get_args():
    ''' argparseによる引数の解析を行い、解析済のargsを返す。 '''

    parser = argparse.ArgumentParser(
        prog='mkmap',
        description='program for making a map on zabbix',
        epilog='copyright 2026 by moto kawasaki <moto@kawasaki3.org>')
    parser.add_argument(
        '-z',
        '--url',
        default='https://127.0.0.1/',
        help='the URL where Zabbix server locates. defaults to "%(default)s".')
    parser.add_argument(
        '-f',
        '--token-file',
        default='./token.txt',
        help='file name which contain the token to login to the Zabbix server. defaults to "%(default)s".')
    parser.add_argument(
        '-m',
        '--map',
        default='mkmap',
        help='The Zabbix map name where the map to be drawn. defaults to "%(default)s". Be cautioned this map being flushed even if it contains nodes/links, or created if not exists.')
    parser.add_argument(
        '-s',
        '--map-size',
        default='800x800',
        help='zabbix map size, width and height joined by "x". defaults to "%(default)s".')
    parser.add_argument(
        '-g',
        '--hostgroup',
        default='mkmap',
        help='The hostgroup name in which hosts to be mapped in the map listed. defaults to "%(default)s".')
    parser.add_argument(
        '-t',
        '--tag-prefix',
        default='mkmap',
        help='The tag name prefix which represent node/link attributes. defaults to "%(default)s". The value consists of remote node name and link label separated by semi-colomn, i.e. "<remote node>;<link label>".')
    parser.add_argument(
        '-o',
        '--output',
        default=None,
        help='The output file name such as "./mkmap.svg" or "./mkmap.png". will not write if not specified, and will overwrite if did.')
    parser.add_argument(
        '-k',
        '--no-validate-certs',
        action='store_true',
        help='disable validation of the SSL/TLS certs.')
    parser.add_argument(
        '-l',
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='WARNING',
        help='log level. defaults to "%(default)s".')

    args = parser.parse_args()

    if args.token_file:
        with open(args.token_file, 'r') as tf:
            args.token = tf.read().strip()
            
    return args

def setup_logging():

    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s [%(levelname)s] %(funcName)s: %(message)s',
        handlers = [ logging.StreamHandler(sys.stderr) ])

    return logging.getLogger(__name__)

def set_loglevel(loglevel):

    match loglevel:
        case 'DEBUG':
            logger.setLevel(logging.DEBUG)
        case 'INFO':
            logger.setLevel(logging.INFO)
        case 'WARNING':
            logger.setLevel(logging.WARNING)
        case 'ERROR':
            logger.setLevel(logging.ERROR)
        case 'CRITICAL':
            logger.setLevel(logging.CRITICAL)

def create_zapi(url, no_validate_certs, token):
    ''' Zabbix API を作成してログインしたものを返す。 '''

    logger.info('creating zabbix api (zapi)...')

    zapi = ZabbixAPI(url=url, validate_certs=(not no_validate_certs))
    zapi.login(token=token)
    return zapi

def get_hosts_in_hostgroup(zapi, hostgroup, tagprefix):
    ''' ホストグループに含まれるホストの一覧を取得する。 '''

    logger.info('getting hosts in hostgroup %s ...', hostgroup)

    hostgroups = zapi.hostgroup.get(filter={'name': hostgroup}, output=['groupid'])

    if len(hostgroups) != 1:
        logger.warn('wrong number (%n) hostgroup(s) found.', len(hostgroups))
        return None

    groupid = hostgroups[0]['groupid']
    hosts = zapi.host.get(groupids=groupid, selectTags='extend', output=['hostid', 'host', 'name', 'tags'])

    new_hosts = []
    tags = []

    for host in hosts:

        new_host = (host['host'], {'hostid': host['hostid'], 'name': host['name']})

        tags_host = [t for t in host['tags'] if t['tag'].startswith(':'.join([tagprefix, 'host']))]
        match len(tags_host):
            case 0:
                pass
            case 1:
                new_host[1]['iconid'] = tags_host[0]['value']
            case _:
                logger.warning('Too many %s:host tags exist for %s. At most 1 expected.', tagprefix, host['host'])
                return None

        tags_links = [t for t in host['tags'] if t['tag'].startswith(':'.join([tagprefix, 'link']))]
        links = []
        for t in tags_links:
            interface, remote_host = [x.strip() for x in t['value'].split(';')]
            links.append([interface, remote_host])
        new_host[1]['links'] = links

        new_hosts.append(new_host)

    return new_hosts

def graphize(hosts, mapsize, outputfile):
    ''' Zabbix API から得たホスト情報 host を使って、networkx のグラフ G を作る。 '''

    logger.info('creating networkx graph from Zabbix hosts data ...')

    G = nx.Graph()

    G.add_nodes_from(hosts)
    
    edges = []
    edge_labels = {}
    for host in hosts:

        hosthost = host[0]
        hostid   = host[1]['hostid']
        links    = host[1]['links']

        for link in links:
            remotehost = link[1]
            interface = link[0]
            edges.append((hosthost, remotehost, {'label': interface}))
            edge_labels = edge_labels | {(hosthost, remotehost): interface}
    
    G.add_edges_from(edges)

    # マップサイズの調整。余白を残して描画エリアの中心点を計算し、中心点から上下・左右に描いて良い範囲を決める。
    width = int(mapsize[0])
    height = int(mapsize[1])
    margin = min(100, min(width, height)/10)
    center_x = width / 2
    center_y = height / 2
    usable_width = width - 2 * margin
    usable_height = height - 2 * margin
    scale = min(usable_width, usable_height) / 2

    # グラフGのレイアウトを計算する。
    pos_float = nx.kamada_kawai_layout(G, center=(center_x, center_y), scale=scale) # requires scipy
    # Zabbixマップでは座標は整数でなければならないのでここで四捨五入する。
    pos = {node: (int(x + 0.5), int(y + 0.5)) for node, (x, y) in pos_float.items()}
 
    nx.draw_networkx_nodes(G, pos, node_color='bisque')
    nx.draw_networkx_edges(G, pos, width=0.5, edge_color='grey')
    nx.draw_networkx_labels(G, pos, font_size=8)
    
    #nx.draw_networkx_edge_labels(G, pos, label_pos=0.15, edge_labels=edge_labels, font_size=6)
    
    return G, pos

def flush_or_create_map(zapi, mapname, mapsize):
    ''' Zabbix map に指定された名前のマップがあればそのマップに含まれる
        ホストやリンク等をすべて削除して、マップのsysmapidを返す。
        なければ、指定された名前のマップを作成してそのsysmapidを返す。
        したがって、常に空のマップを返すことになる。
        将来余裕があれば、既存の場合にselements[]の中の情報をグラフに取り込んで
        そこへの修正をする形にしたいが...
    '''
 
    logger.info('flush or create Zabbix map ...')

    maps = zapi.map.get(filter={'name': mapname},
        selectSelements='extend', selectLinks='extend', selectShapes='extend', selectUrls='extend')

    if len(maps) == 1:
        logger.info('map %s exists.', mapname)
        mkmap = maps[0]
        mkmapid = mkmap['sysmapid']

        if len(mkmap['selements'])>0 or len(mkmap['links'])>0 or len(mkmap['shapes'])>0 or mkmap['backgroundid']!='0' or len(mkmap['urls'])>0 or mkmap['width']!=mapsize[0] or mkmap['height']!=mapsize[1]:
            logger.info('something remains in the map %s. flushing...', mkmap['name'])
            zapi.map.update(sysmapid=mkmapid, selements=[], links=[], shapes=[], backgroundid='0', sysmapurls=[], width=mapsize[0], height=mapsize[1])
        else:
            logger.info('nothing remains in the map %s. do nothing.', mkmap['name'])
    else:
        logger.info('map not exists. creating it...')
        mkmap = zapi.map.create({'name': mapname, 'width': mapsize[0], 'height': mapsize[1]})
        mkmapid = map['sysmapid']

    return mkmapid

def create_mapdata(mapid, G, pos):
    ''' グラフ G とそのレイアウト pos から、Zabbixマップ描画に必要なマップデータを作る。 '''

    logger.info('creating map data from G and pos...')

    mapdata = {}

    mapdata['sysmapid'] = mapid
    mapdata['name'] = 'mkmap'

    selements = []
    hosthostiddict = {}
    for hosthost, hostattr in G.nodes(data=True):
        hostid = hostattr['hostid']
        iconid = hostattr.get('iconid', 179)

        selement = {
            'selementid': hostid, 
            'elementtype': 0, 
            'elements': [{'hostid': hostid}], 
            #'host': hosthost,
            'iconid_off': iconid,
            'x': pos[hosthost][0],
            'y': pos[hosthost][1],
        }
        selements.append(selement)

        hosthostiddict[hosthost] = hostid	# edges処理で使う早見表

    mapdata['selements'] = selements

    links = []    
    for edgefrom, edgeto, edgeattr in G.edges(data=True):
        edgelabel = edgeattr['label']

        link = {
            'selementid1': hosthostiddict[edgefrom],
            'selementid2': hosthostiddict[edgeto],
            #'label': edgelabel,	# エッジの両端にラベルを描きたいがZabbixマップではできない。
        }
        links.append(link)

    mapdata['links'] = links

    return mapdata


### ここからmainの処理。
if __name__ == '__main__':

    # ロガーと引数の処理
    logger = setup_logging()
    args = get_args()
    set_loglevel(args.log_level)
    logger.info('args: url=%s token_file=%s map=%s hostgroup=%s no_validate_certs=%s log_level=%s', args.url, args.token_file, args.map, args.hostgroup, args.no_validate_certs, args.log_level)

    # Zabbix APIにログインする。
    zapi = create_zapi(args.url, args.no_validate_certs, args.token)

    # Zabbixから指定されたhostgroupのホストを読み出す。
    hosts = get_hosts_in_hostgroup(zapi, args.hostgroup, args.tag_prefix)

    # 読み出したホストをnetworkxのグラフGに登録する。
    # ホストに付随するタグからホストやリンクのattributeを読み取って、それもグラフGに登録する。
    G, pos = graphize(hosts, args.map_size.split('x'), args.output)

    # グラフを画像ファイルへ書き出す
    if args.output is not None:
        plt.axis('off')
        #plt.show()
        plt.savefig(args.output)
    
    # Zabbixマップがあればマップ上の構成要素をすべて削除し、なければマップを作成する。
    mapid = flush_or_create_map(zapi, args.map, args.map_size.split('x'))

    # グラフGに登録されたホストをZabbixマップに登録するためにselementsやsedgesを含むmapdataを作る。
    mapdata = create_mapdata(mapid, G, pos)

    # マップデータをZabbixに送ってZabbixマップを描画する。
    zapi.map.update(mapdata)

