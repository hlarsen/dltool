#!/usr/bin/env python3
#
# This script will take "fix DATs" (DATs made up of missing ROMs) and attempt to download them from Myrient.
#

import os
import re
import math
import signal
import argparse
import datetime
import platform
import requests
import textwrap
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from progressbar import ProgressBar, Bar, ETA, FileTransferSpeed, Percentage, DataSize

# Constants
CATALOG_URLS = {
    'https://www.no-intro.org': 'No-Intro',
    'https://redump.org/': 'Redump'
}
CHUNK_SIZE = 8192
DAT_NAME_FIXES = [
    'fixDat_'
    ' (Retool)',
]
MYRIENT_URL = 'https://myrient.erista.me/files/'
REQ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
}


# Print output function
def logger(str, color=None, rewrite=False):
    colors = {'red': '\033[91m', 'green': '\033[92m', 'yellow': '\033[93m', 'cyan': '\033[96m'}
    if rewrite:
        print('\033[1A', end='\x1b[2K')
    if color:
        print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {colors[color]}{str}\033[00m')
    else:
        print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {str}')


# Input request function
def inputter(str, color=None):
    colors = {'red': '\033[91m', 'green': '\033[92m', 'yellow': '\033[93m', 'cyan': '\033[96m'}
    if color:
        val = input(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {colors[color]}{str}\033[00m')
    else:
        val = input(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {str}')
    return val


# Scale file size
def scale1024(val):
    prefixes = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    if val <= 0:
        power = 0
    else:
        power = min(int(math.log(val, 2) / 10), len(prefixes) - 1)
    scaled = float(val) / (2 ** (10 * power))
    unit = prefixes[power]
    return scaled, unit


# Exit handler function
def exithandler(signum, frame):
    logger('Exiting script!', 'red')
    exit()


signal.signal(signal.SIGINT, exithandler)

# Generate argument parser
parser = argparse.ArgumentParser(
    add_help=False,
    formatter_class=argparse.RawTextHelpFormatter,
    description=textwrap.dedent('''\
        \033[92mTool to automatically download ROMs of a DAT-file from Myrient.
        
        Generate a DAT-file with the tool of your choice to include ROMs that you
        want from a No-Intro/Redump/etc catalog, then use this tool to download
        the matching files from Myrient.\033[00m
    '''))

# Add required arguments
requiredargs = parser.add_argument_group('\033[91mRequired arguments\033[00m')
requiredargs.add_argument('-i', dest='inp', metavar='nointro.dat', help='Input DAT-file containing wanted ROMs',
                          required=True)
requiredargs.add_argument('-o', dest='out', metavar='/data/roms', help='Output path for ROM files to be downloaded',
                          required=True)
# Add optional arguments
optionalargs = parser.add_argument_group('\033[96mOptional arguments\033[00m')
optionalargs.add_argument('-c', dest='catalog', action='store_true',
                          help='Choose catalog manually, even if automatically found')
optionalargs.add_argument('-s', dest='system', action='store_true',
                          help='Choose system collection manually, even if automatically found')
optionalargs.add_argument('-l', dest='list', action='store_true',
                          help='List only ROMs that are not found in server (if any)')
optionalargs.add_argument('-h', '--help', dest='help', action='help', help='Show this help message')
args = parser.parse_args()

# Init variables
catalog = None
collection = None
wanted_roms = []
wanted_files = []
missing_roms = []
collection_dir = []
available_roms = {}
found_collections = []

# Validate arguments
if not os.path.isfile(args.inp):
    logger('Invalid input DAT-file!', 'red')
    exit()
if not os.path.isdir(args.out):
    logger('Invalid output ROM path!', 'red')
    exit()
if platform.system() == 'Linux' and args.out[-1] == '/':
    args.out = args.out[:-1]
elif platform.system() == 'Windows' and args.out[-1] == '\\':
    args.out = args.out[:-1]

# Open input DAT-file
logger('Opening input DAT-file...', 'green')
dat_xml = ET.parse(args.inp)
dat_root = dat_xml.getroot()

# Loop through ROMs in input DAT-file
for dat_child in dat_root:
    # Print out system information
    if dat_child.tag == 'header':
        system = dat_child.find('name').text
        for fix in DAT_NAME_FIXES:
            system = system.replace(fix, '')
        catalog_url = dat_child.find('url').text
        if catalog_url in CATALOG_URLS:
            catalog = CATALOG_URLS[catalog_url]
            logger(f'Processing {catalog}: {system}...', 'green')
        else:
            logger(f'Processing {system}...', 'green')
    # Add found ROMs to wanted list
    elif dat_child.tag == 'game':
        filename = dat_child.attrib['name']
        filename = re.sub(r'\.[(a-zA-Z0-9)]{1,3}\Z', '', filename)
        if filename not in wanted_roms:
            wanted_roms.append(filename)

# Get HTTP base and select wanted catalog
catalog_url = None
resp = requests.get(MYRIENT_URL, headers=REQ_HEADERS).text
resp = BeautifulSoup(resp, 'html.parser')
main_dir = resp.find('table', id='list').tbody.find_all('tr')
for current_dir in main_dir[1:]:
    cell = current_dir.find('td')
    if catalog in cell.a['title']:
        catalog_url = cell.a['href']

if not catalog_url or args.catalog:
    logger('Catalog for DAT not automatically found, please select from the following:', 'yellow')
    dir_nbr = 1
    catalog_temp = {}
    for current_dir in main_dir[1:]:
        cell = current_dir.find('td')
        logger(f'{str(dir_nbr).ljust(2)}: {cell.a["title"]}', 'yellow')
        catalog_temp[dir_nbr] = {'name': cell.a['title'], 'url': cell.a['href']}
        dir_nbr += 1
    while True:
        sel = inputter('Input selected catalog number: ', 'cyan')
        try:
            sel = int(sel)
            if sel > 0 and sel < dir_nbr:
                catalog = catalog_temp[sel]['name']
                catalog_url = catalog_temp[sel]['url']
                break
            else:
                logger('Input number out of range!', 'red')
        except:
            logger('Invalid number!', 'red')

# Get catalog directory and select wanted collection
collection_url = None
resp = requests.get(f'{MYRIENT_URL}{catalog_url}', headers=REQ_HEADERS).text
resp = BeautifulSoup(resp, 'html.parser')
content_dir = resp.find('table', id='list').tbody.find_all('tr')
for current_dir in content_dir[1:]:
    cell = current_dir.find('td')
    if cell.a['title'].startswith(system):
        found_collections.append({'name': cell.a['title'], 'url': cell.a['href']})
if len(found_collections) == 1:
    collection = found_collections[0]['name']
    collection_url = found_collections[0]['url']
if not collection or args.system:
    logger('Collection for DAT not automatically found, please select from the following:', 'yellow')
    dir_nbr = 1
    if len(found_collections) > 1 and not args.system:
        for found_collection in found_collections:
            logger(f'{str(dir_nbr).ljust(2)}: {found_collection["name"]}', 'yellow')
            dir_nbr += 1
    else:
        collection_temp = {}
        for current_dir in content_dir[1:]:
            cell = current_dir.find('td')
            logger(f'{str(dir_nbr).ljust(2)}: {cell.a["title"]}', 'yellow')
            collection_temp[dir_nbr] = {'name': cell.a['title'], 'url': cell.a['href']}
            dir_nbr += 1
    while True:
        sel = inputter('Input selected collection number: ', 'cyan')
        try:
            sel = int(sel)
            if 0 < sel < dir_nbr:
                if len(found_collections) > 1 and not args.system:
                    collection = found_collections[sel - 1]['name']
                    collection_url = found_collections[sel - 1]['url']
                else:
                    collection = collection_temp[sel]['name']
                    collection_url = collection_temp[sel]['url']
                break
            else:
                logger('Input number out of range!', 'red')
        except:
            logger('Invalid number!', 'red')

# Get collection directory contents and list contents to available ROMs
resp = requests.get(f'{MYRIENT_URL}{catalog_url}{collection_url}', headers=REQ_HEADERS).text
resp = BeautifulSoup(resp, 'html.parser')
collection_dir = resp.find('table', id='list').tbody.find_all('tr')
for rom in collection_dir[1:]:
    cell = rom.find('a')
    filename = cell['title']
    rom_name = re.sub(r'\.[(a-zA-Z0-9)]{1,3}\Z', '', filename)
    url = f'{MYRIENT_URL}{catalog_url}{collection_url}{cell["href"]}'
    available_roms[rom_name] = {'name': rom_name, 'file': filename, 'url': url}

# Compare wanted ROMs and contents of the collection, parsing out only wanted files
for wanted_rom in wanted_roms:
    if wanted_rom in available_roms:
        wanted_files.append(available_roms[wanted_rom])
    else:
        missing_roms.append(wanted_rom)

# Print out information about wanted/found/missing ROMs
logger(f'Amount of wanted ROMs in DAT-file   : {len(wanted_roms)}', 'green')
logger(f'Amount of found ROMs at server      : {len(wanted_files)}', 'green')
if missing_roms:
    logger(f'Amount of missing ROMs at server    : {len(missing_roms)}', 'yellow')

# Download wanted files
if not args.list:
    dl_counter = 0
    for wanted_file in wanted_files:
        dl_counter += 1
        resume_dl = False
        proceed_dl = True

        if platform.system() == 'Linux':
            local_path = f'{args.out}/{wanted_file["file"]}'
        elif platform.system() == 'Windows':
            local_path = f'{args.out}\{wanted_file["file"]}'

        resp = requests.get(wanted_file['url'], headers=REQ_HEADERS, stream=True)
        remote_file_size = int(resp.headers.get('content-length'))

        if os.path.isfile(local_path):
            local_file_size = int(os.path.getsize(local_path))
            if local_file_size != remote_file_size:
                resume_dl = True
            else:
                proceed_dl = False

        if proceed_dl:
            file = open(local_path, 'ab')

            size, unit = scale1024(remote_file_size)
            pbar = ProgressBar(widgets=['\033[96m', Percentage(), ' | ', DataSize(), f' / {round(size, 1)} {unit}', ' ',
                                        Bar(marker='#'), ' ', ETA(), ' | ', FileTransferSpeed(), '\033[00m'],
                               max_value=remote_file_size, redirect_stdout=True, max_error=False)
            pbar.start()

            if resume_dl:
                logger(
                    f'Resuming    {str(dl_counter).zfill(len(str(len(wanted_files))))}/{len(wanted_files)}: {wanted_file["name"]}',
                    'cyan')
                pbar += local_file_size
                headers = REQ_HEADERS
                headers.update({'Range': f'bytes={local_file_size}-'})
                resp = requests.get(wanted_file['url'], headers=headers, stream=True)
                for data in resp.iter_content(chunk_size=CHUNK_SIZE):
                    file.write(data)
                    pbar += len(data)
            else:
                logger(
                    f'Downloading {str(dl_counter).zfill(len(str(len(wanted_files))))}/{len(wanted_files)}: {wanted_file["name"]}',
                    'cyan')
                for data in resp.iter_content(chunk_size=CHUNK_SIZE):
                    file.write(data)
                    pbar += len(data)

            file.close()
            pbar.finish()
            print('\033[1A', end='\x1b[2K')
            logger(
                f'Downloaded  {str(dl_counter).zfill(len(str(len(wanted_files))))}/{len(wanted_files)}: {wanted_file["name"]}',
                'green', True)
        else:
            logger(
                f'Already DLd {str(dl_counter).zfill(len(str(len(wanted_files))))}/{len(wanted_files)}: {wanted_file["name"]}',
                'green')
    logger('Downloading complete!', 'green', False)

# Output missing ROMs, if any
if missing_roms:
    logger(f'Following {len(missing_roms)} ROMs in DAT not automatically found from server, grab these manually:',
           'red')
    for missing_rom in missing_roms:
        logger(missing_rom, 'yellow')
else:
    logger('All ROMs in DAT found from server!', 'green')
