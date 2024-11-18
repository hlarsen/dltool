#!/usr/bin/env python3
#
# This script will take "fix DATs" (DATs made up of missing ROMs) and attempt to download the files from Myrient.
#

import argparse
import datetime
import os
import math
import re
import requests
import signal
import textwrap
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from progressbar import ProgressBar, Bar, ETA, FileTransferSpeed, Percentage, DataSize
from typing import TypedDict

RomMeta = TypedDict('RomMeta', {'name': str, 'file': str, 'url': str})

# Constants
CATALOG_URLS = {
    'https://www.no-intro.org': 'No-Intro',
    'https://redump.org/': 'Redump'
}
CHUNK_SIZE = 8192
DAT_NAME_FIXES = [
    'FixDat_',
    ' (Retool)',
]
MYRIENT_URL = 'https://myrient.erista.me/files/'
REQ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
}


# Print output function
def logger(message, color=None, rewrite=False):
    colors = {'red': '\033[91m', 'green': '\033[92m', 'yellow': '\033[93m', 'cyan': '\033[96m'}
    if rewrite:
        print('\033[1A', end='\x1b[2K')
    if color:
        print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {colors[color]}{message}\033[00m')
    else:
        print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {message}')


# Input request function
def ask_for_input(message, color=None):
    colors = {'red': '\033[91m', 'green': '\033[92m', 'yellow': '\033[93m', 'cyan': '\033[96m'}
    if color:
        val = input(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {colors[color]}{message}\033[00m')
    else:
        val = input(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {message}')
    return val


# Scale file size
def scale_1024(val):
    prefixes = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    if val <= 0:
        power = 0
    else:
        power = min(int(math.log(val, 2) / 10), len(prefixes) - 1)
    scaled = float(val) / (2 ** (10 * power))
    unit = prefixes[power]
    return scaled, unit


# Exit handler function
def exit_handler(signum, frame):
    logger('Exiting script!', 'red')
    exit()


# Download function
def download(output_path: str, file_to_dl: RomMeta, file_index: int, total_download_count: int):
    resume_dl = False
    proceed_dl = True

    local_path = os.path.join(output_path, file_to_dl["file"])

    file_to_dl_resp = requests.get(file_to_dl['url'], headers=REQ_HEADERS, stream=True)
    remote_file_size = int(file_to_dl_resp.headers.get('content-length'))

    if os.path.isfile(local_path):
        local_file_size = int(os.path.getsize(local_path))
        if local_file_size != remote_file_size:
            resume_dl = True
        else:
            proceed_dl = False

    else:
        raise "Could not get local path"

    if proceed_dl:
        file = open(local_path, 'ab')

        size, unit = scale_1024(remote_file_size)
        pbar = ProgressBar(
            widgets=['\033[96m', Percentage(), ' | ', DataSize(), f' / {round(size, 1)} {unit}', ' ', Bar(marker='#'),
                     ' ', ETA(), ' | ', FileTransferSpeed(), '\033[00m'], max_value=remote_file_size,
            redirect_stdout=True, max_error=False)
        pbar.start()

        if resume_dl:
            logger(
                f'Resuming    {str(file_index).zfill(len(str(total_download_count)))}/{total_download_count}: {file_to_dl["name"]}',
                'cyan')
            pbar += local_file_size
            headers = REQ_HEADERS
            headers.update({'Range': f'bytes={local_file_size}-'})
            file_to_dl_resp = requests.get(file_to_dl['url'], headers=headers, stream=True)
            for data in file_to_dl_resp.iter_content(chunk_size=CHUNK_SIZE):
                file.write(data)
                pbar += len(data)
        else:
            logger(
                f'Downloading {str(file_index).zfill(len(str(total_download_count)))}/{total_download_count}: {file_to_dl["name"]}',
                'cyan')
            for data in file_to_dl_resp.iter_content(chunk_size=CHUNK_SIZE):
                file.write(data)
                pbar += len(data)

        file.close()
        pbar.finish()
        print('\033[1A', end='\x1b[2K')
        logger(
            f'Downloaded  {str(file_index).zfill(len(str(total_download_count)))}/{total_download_count}: {file_to_dl["name"]}',
            'green', True)
    else:
        logger(
            f'Already DLd {str(file_index).zfill(len(str(total_download_count)))}/{total_download_count}: {file_to_dl["name"]}',
            'green')


signal.signal(signal.SIGINT, exit_handler)

# Generate argument parser
parser = argparse.ArgumentParser(
    add_help=False,
    formatter_class=argparse.RawTextHelpFormatter,
    description=textwrap.dedent('''\
        \033[92mTool to automatically download ROMs of a DAT-file via Myrient.
        
        Generate a DAT-file with the tool of your choice to include ROMs that you
        want from a No-Intro/Redump/etc catalog, then use this tool to download
        the matching files from Myrient.\033[00m
    '''))

# Add required arguments
required_args = parser.add_argument_group('\033[91mRequired arguments\033[00m')
required_args.add_argument('-i', dest='input_files', metavar='*.dat',
                           help='Input DAT-file(s) containing wanted ROMs',
                           required=True, nargs="+")
required_args.add_argument('-o', dest='output_dir', metavar='/data/roms',
                           help='Output path for ROM files to be downloaded',
                           required=True)

# Add optional arguments
optional_args = parser.add_argument_group('\033[96mOptional arguments\033[00m')
optional_args.add_argument('-c', dest='manual_catalog', action='store_true',
                           help='Choose catalog manually, even if automatically found')
optional_args.add_argument('-s', dest='manual_system', action='store_true',
                           help='Choose system collection manually, even if automatically found')
optional_args.add_argument('-l', dest='list_only', action='store_true',
                           help='List only ROMs that are not found in server (if any)')
optional_args.add_argument('-h', '--help', dest='help', action='help', help='Show this help message')
args = parser.parse_args()

# Handle glob input for DAT files
dat_files_to_process = sorted(set(os.path.abspath(file) for file in args.input_files))

# Validate input files
for dat_file_to_process in dat_files_to_process:
    if not os.path.isfile(dat_file_to_process):
        print(f'Input DAT-file invalid: #{dat_file_to_process}', 'red')
        exit()

    if not os.path.exists(args.output_dir) or not os.path.isdir(args.output_dir):
        print('Output ROM path is not a valid directory!', 'red')
        exit()

# Process input files
for dat_file_to_process in dat_files_to_process:
    # Open input DAT-file
    logger(f'Opening input DAT-file {dat_file_to_process}...', 'green')
    dat_xml = ET.parse(dat_file_to_process)
    dat_root = dat_xml.getroot()

    # Loop through ROMs in input DAT-file
    dat_name = None
    catalog = None
    wanted_roms = []
    for dat_child in dat_root:
        # DAT file header
        if dat_child.tag == 'header':
            # replace garbage in the DAT file name so our output dirs
            # this allows us to automatically look up the correct download folder even with modified DAT names
            dat_name = dat_child.find('name').text
            for fix in DAT_NAME_FIXES:
                dat_name = dat_name.replace(fix, '')

            catalog_url = dat_child.find('url').text
            if catalog_url in CATALOG_URLS:
                catalog = CATALOG_URLS[catalog_url]
                logger(f'Processing {catalog}: {dat_name}...', 'green')
            else:
                logger(f'Processing {dat_name}...', 'green')
        # DAT file game entry
        elif dat_child.tag == 'game':
            filename = dat_child.attrib['name']
            filename = re.sub(r'\.[(a-zA-Z0-9)]{1,3}\Z', '', filename)
            if filename not in wanted_roms:
                wanted_roms.append(filename)
        else:
            # Some other entry in the DAT file
            continue

    if dat_name is None:
        raise f"No DAT Name found for file {dat_file_to_process}"

    # Get HTTP base and select wanted catalog
    catalog_url = None
    resp = requests.get(MYRIENT_URL, headers=REQ_HEADERS).text
    resp = BeautifulSoup(resp, 'html.parser')
    main_dir = resp.find('table', id='list').tbody.find_all('tr')
    for current_dir in main_dir[1:]:
        cell = current_dir.find('td')
        if catalog in cell.a['title']:
            catalog_url = cell.a['href']

    if not catalog_url or args.manual_catalog:
        logger('Catalog for DAT not automatically found, please select from the following:', 'yellow')
        dir_nbr = 1

        catalog_temp = {}
        for current_dir in main_dir[1:]:
            cell = current_dir.find('td')
            logger(f'{str(dir_nbr).ljust(2)}: {cell.a["title"]}', 'yellow')
            catalog_temp[dir_nbr] = {'name': cell.a['title'], 'url': cell.a['href']}
            dir_nbr += 1

        while True:
            sel = ask_for_input('Input selected catalog number: ', 'cyan')
            try:
                sel = int(sel)

                if sel > 0 and sel < dir_nbr:
                    # catalog = catalog_temp[sel]['name']
                    catalog_url = catalog_temp[sel]['url']
                    break
                else:
                    logger('Input number out of range!', 'red')
            except:
                logger('Invalid number!', 'red')

    # Get directories, auto-select if possible or present a (hopefully filtered) list
    collection_url = None
    found_collections = []
    resp = requests.get(f'{MYRIENT_URL}{catalog_url}', headers=REQ_HEADERS).text
    resp = BeautifulSoup(resp, 'html.parser')
    content_dir = resp.find('table', id='list').tbody.find_all('tr')
    for current_dir in content_dir[1:]:
        cell = current_dir.find('td')
        if cell.a['title'] == dat_name:
            found_collections = [({'name': cell.a['title'], 'url': cell.a['href']})]
            break
        elif dat_name in cell.a['title']:
            found_collections.append({'name': cell.a['title'], 'url': cell.a['href']})

    collection = None
    if len(found_collections) == 1:
        collection = found_collections[0]['name']
        collection_url = found_collections[0]['url']

    # Handle collection not found or if the user passed in a specific system
    if not collection or args.manual_system:
        logger('Collection for DAT not automatically found, please select from the following:', 'yellow')
        dir_nbr = 1
        collection_temp = {}
        if len(found_collections) > 1 and not args.manual_system:
            for found_collection in found_collections:
                logger(f'{str(dir_nbr).ljust(2)}: {found_collection["name"]}', 'yellow')
                dir_nbr += 1
        else:
            for current_dir in content_dir[1:]:
                cell = current_dir.find('td')
                logger(f'{str(dir_nbr).ljust(2)}: {cell.a["title"]}', 'yellow')
                collection_temp[dir_nbr] = {'name': cell.a['title'], 'url': cell.a['href']}
                dir_nbr += 1

        while True:
            sel = ask_for_input('Input selected collection number: ', 'cyan')
            try:
                sel = int(sel)
                if 0 < sel < dir_nbr:
                    if len(found_collections) > 1 and not args.manual_system:
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
    available_roms = {}
    for rom in collection_dir[1:]:
        cell = rom.find('a')
        filename = cell['title']
        rom_name = re.sub(r'\.[(a-zA-Z0-9)]{1,3}\Z', '', filename)
        url = f'{MYRIENT_URL}{catalog_url}{collection_url}{cell["href"]}'
        available_roms[rom_name] = {'name': rom_name, 'file': filename, 'url': url}

    # Compare wanted ROMs and contents of the collection, parsing out only wanted files
    wanted_files = []
    missing_roms = []
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
    if not args.list_only:
        dl_counter = 0
        for wanted_file in wanted_files:
            dl_counter += 1
            download(args.output_dir, wanted_file, dl_counter, len(wanted_files))

    # Output missing ROMs, if any
    if missing_roms:
        logger(f'Following {len(missing_roms)} ROMs in DAT not automatically found from server, grab these manually:',
               'red')
        for missing_rom in missing_roms:
            logger(missing_rom, 'yellow')
    else:
        logger('All ROMs in DAT found from server!', 'green')
