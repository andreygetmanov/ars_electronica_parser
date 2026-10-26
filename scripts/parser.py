import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Union

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

ROOT_LINK = 'https://archive.aec.at'

# Category codes used by the archive filters (https://archive.aec.at/prix/)
CATEGORIES = {
    'All': -1,
    'Computer Graphics': 'CG',
    'Computer Animation': 'CA',
    'Interactive Art': 'IA',
    'Music & Sound': 'DM',
    'Hybrid Art': 'HA',
    'Netbased Art': 'N',
    'Digital Communities': 'DC',
    'the next idea': 'NI',
    'Media Art.Research Award': 'MA',
    'u19': 'U19',
    'Visionary Pioneers': 'VP',
    'Klasse! Lernen': 'KL',
    'Artificial Intelligence & Life Art': 'AI',
    'Digital Humanity': 'DH',
    'AI in Art Award': 'AIA',
    'AI for Social Impact Initiative': 'SI',
}

# Award codes used by the archive filters
AWARDS = {
    'All': -2,  # all submissions with a prize
    'Golden Nica': 100,
    'Grand Prize': 108,
    'Award of Distinction': 101,
    'Honorary Mention': 102,
    'Grant': 105,
    'Special Prize': 106,
    'Nomination': 107,
    'Young Creatives Prize': 150,
}

# The archive shows category titles in German for some years
CATEGORY_TRANSLATIONS = {
    'Computergraphik': 'Computer Graphics',
    'Computeranimation': 'Computer Animation',
    'Computermusik': 'Computer Music',
    'Interaktive Kunst': 'Interactive Art',
    'Computeranimation / Visual Effects': 'Computer Animation / Visual Effects',
    'Computeranimation / Film / VFX': 'Computer Animation / Film / VFX',
    'Digitale Musik': 'Digital Musics',
    'Digital Musics & Sound Art': 'Digital Musics & Sound Art',
}

# Award groups in the winners listing that are not artworks
SKIP_AWARD_GROUPS = {'Jury Statements'}

# Types of the media in the artwork page slider and the fields they are saved to
MEDIA_FIELDS = {
    'photos': 'img_list',
    'film': 'video_list',
    'sound': 'audio_list',
}


class Parser:
    """
    A class that parses data from the Ars Electronica Archive (https://archive.aec.at/prix/).

    Attributes
    ----------
    workers : int
        The number of artwork pages downloaded in parallel.
    delay : float
        The pause (in seconds) after each request of a worker.
    """

    def __init__(self, workers: int = 4, delay: float = 0.2):
        self.workers = workers
        self.delay = delay
        self._local = threading.local()

    def parse_data(self,
                   award: Union[list, str] = 'All',
                   category: Union[list, str] = 'All',
                   years: Optional[Union[list, range]] = None,
                   path_to_save: str = 'data/ars_electronica_prizewinners.json',
                   update: bool = True):
        """
        Retrieves the data of prize-winning artworks and saves it to json.

        Parameters
        ----------
        award : Union[list, str]
            The name/list of names of award for which the data should be retrieved ('All' for all).
        category: Union[list, str]
            The name/list of names of category for which the data should be retrieved ('All' for all).
        years : Union[list, range], optional
            The list/range of years for which the data should be retrieved (all available years if None).
        path_to_save : str
            The path where the json with data will be saved.
        update : bool
            If True and the json already exists, only the artworks missing in it are parsed.
        """
        if years is None:
            years = self.get_years()
        print(f'Collecting works of {category} category with {award} award from {min(years)} to {max(years)}')
        listing = self.get_ids(category, award, years)
        print(f'Collected {len(listing)} artworks')

        artworks = self._load(path_to_save) if update else {}
        to_parse = [artwork_id for artwork_id in listing if artwork_id not in artworks]
        print(f'{len(listing) - len(to_parse)} artworks are already saved, {len(to_parse)} to parse')

        failed = []
        with ThreadPoolExecutor(self.workers) as executor:
            futures = {executor.submit(self.get_data, artwork_id, listing[artwork_id]): artwork_id
                       for artwork_id in to_parse}
            for i, future in enumerate(tqdm(as_completed(futures), total=len(futures)), 1):
                artwork_id = futures[future]
                try:
                    artworks[artwork_id] = future.result()
                except Exception as e:
                    print(f'Failed to parse artwork {artwork_id}: {e!r}')
                    failed.append(artwork_id)
                if i % 200 == 0:
                    # intermediate saves allow to continue an interrupted run
                    self._save(self._sorted(artworks), path_to_save)

        print('Parsing finished. Saving the data to json...')
        artworks = self._drop_empty_duplicates(artworks)
        self._save(self._sorted(artworks), path_to_save)
        print(f'Completed! Saved {len(artworks)} artworks to {path_to_save}')
        if failed:
            print(f'{len(failed)} artworks failed, run the parser again to retry: {failed}')

    def get_years(self) -> list:
        """
        Retrieves the list of years available in the archive.
        """
        params = {'view': 'winners', 'category': -1, 'award': -2, 'searchstring': '', 'start': 0, 'length': 1}
        response = self._get(f'{ROOT_LINK}/prix/data/', params)
        year_counts = response.json()['aaYearCounts']
        return sorted(int(year) for year, count in year_counts if count)

    def get_ids(self, category: Union[list, str], award: Union[list, str], years: Union[list, range]) -> dict:
        """
        Retrieves the ids of prize-winning artworks for the given categories, awards and years.

        Parameters
        ----------
        award : Union[list, str]
            The name/list of names of award for which the data should be retrieved ('All' for all).
        category: Union[list, str]
            The name/list of names of category for which the data should be retrieved ('All' for all).
        years : Union[list, range]
            The list/range of years for which the data should be retrieved.

        Returns
        -------
        id_dict : dict
            A dictionary {artwork id: {'award': ..., 'category_code': ..., 'year': ...}}.
        """
        if isinstance(category, str):
            category = [category]
        if isinstance(award, str):
            award = [award]
        id_dict = {}
        for cat in category:
            for aw in award:
                for year in tqdm(years, desc=f'{cat} / {aw}'):
                    params = {'view': 'winners', 'category': CATEGORIES[cat], 'award': AWARDS[aw],
                              'searchstring': '', 'year': year}
                    content = self._soup(self._get(f'{ROOT_LINK}/prix/data/year/', params))
                    for group in content.find_all('div', class_='winners_award'):
                        if group.get_text(strip=True) in SKIP_AWARD_GROUPS:
                            continue
                        for link in group.find_next_sibling('div').find_all('a', class_='boxlink'):
                            match = re.fullmatch(r'/prix/(\d+)/', link['href'])
                            if not match:
                                continue
                            award_span = link.find('span', class_='award')
                            id_dict[match.group(1)] = {
                                'award': award_span.get_text(strip=True) if award_span else group.get_text(strip=True),
                                'category_code': link.get('category'),
                                'year': str(year),
                            }
        return id_dict

    def get_data(self, artwork_id: str, listing_info: Optional[dict] = None) -> dict:
        """
        Retrieves the artwork data from its page, parses it and returns as a dict.

        Parameters
        ----------
        artwork_id : str
            The id of the artwork in the archive.
        listing_info : dict, optional
            The info about the artwork collected from the winners listing (award, category code, year).

        Returns
        -------
        artwork_data : dict
            A dictionary containing the parsed artwork data with the following keys:
                - `name` : str
                    The name of the artwork.
                - `authors` : str
                    The authors of the artwork.
                - `award` : str
                    The award received by the artwork.
                - `year` : str
                    The year the award was received.
                - `category` : str
                    The category of the artwork (as it was named in that year).
                - `category_code` : str
                    The code of the category in the archive filters.
                - `description` : str
                    The description (catalog text) of the artwork.
                - `credits` : str
                    The credits of the artwork.
                - `biography` : str
                    The biography of the authors.
                - `jury_statement` : str
                    The jury statement about the artwork.
                - 'img_list' : list
                    The list containing the URLs to the artwork images.
                - 'video_list' : list
                    The list containing the URLs to the artwork videos.
                - 'audio_list' : list
                    The list containing the URLs to the artwork audio files.
                - 'url' : str
                    The URL to the artwork.
        """
        listing_info = listing_info or {}
        url = f'{ROOT_LINK}/prix/{artwork_id}/'
        content = self._soup(self._get(url)).find('main')

        header = content.find('h3', class_='bar-color')
        award_and_year = header.find('span').get_text(strip=True)
        header.find('span').extract()
        category = header.get_text(strip=True)
        category = CATEGORY_TRANSLATIONS.get(category, category)
        year = listing_info.get('year') or award_and_year.split()[-1]
        # the page shows awards in both languages ("Goldene Nica - Golden Nica 2009")
        award = listing_info.get('award') or award_and_year.rsplit(' ', 1)[0].split(' - ')[-1]

        name = header.find_next('h1').get_text(strip=True)
        authors_div = content.find('div', class_='mb-1')
        authors = self._clean(authors_div.get_text()) if authors_div else ''

        media_lists = {field: [] for field in MEDIA_FIELDS.values()}
        for item in content.select('#assets_slider .carousel-item'):
            media = item.find(['img', 'source', 'video', 'audio'], src=True)
            if not media:
                continue
            if item.get('type') not in MEDIA_FIELDS:
                print(f'Artwork {artwork_id} has media of unknown type {item.get("type")}')
                continue
            media_lists[MEDIA_FIELDS[item['type']]].append(ROOT_LINK + media['src'])

        tabs = {}
        for button in content.select('.nav-tabs button[data-bs-target]'):
            pane = content.find('div', id=button['data-bs-target'].lstrip('#'))
            if pane:
                tabs[button.get_text(strip=True).lower()] = self._text(pane)

        artwork_data = {
            'name': name,
            'authors': authors,
            'award': award,
            'year': year,
            'category': category,
            'category_code': listing_info.get('category_code'),
            'description': tabs.get('catalog text', ''),
            'credits': tabs.get('credits', ''),
            'biography': tabs.get('biography', ''),
            'jury_statement': tabs.get('jury statement', ''),
            **media_lists,
            'url': url,
        }
        return artwork_data

    def _session(self) -> requests.Session:
        # One session per thread, with retries on connection problems and server errors
        if not hasattr(self._local, 'session'):
            session = requests.Session()
            retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
            session.mount('https://', HTTPAdapter(max_retries=retry))
            session.headers.update({'Accept-Language': 'en-US',
                                    'User-Agent': 'ars-electronica-parser (+https://github.com/andreygetmanov)'})
            self._local.session = session
        return self._local.session

    def _get(self, url: str, params: dict = None) -> requests.Response:
        response = self._session().get(url, params=params, timeout=60)
        response.raise_for_status()
        time.sleep(self.delay)
        return response

    @staticmethod
    def _soup(response: requests.Response) -> BeautifulSoup:
        return BeautifulSoup(response.text, 'html.parser')

    @staticmethod
    def _text(element) -> str:
        # Keeps line breaks (<br>, <p>) of the original text
        for br in element.find_all('br'):
            br.replace_with('\n')
        for block in element.find_all(['p', 'div', 'li', 'h1', 'h2', 'h3', 'h4']):
            block.insert_after('\n')
        text = element.get_text().replace('\xa0', ' ').replace('\r', '')
        lines = [' '.join(line.split()) for line in text.split('\n')]
        text = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
        # empty texts are sometimes rendered as "None"
        return '' if text == 'None' else text

    @staticmethod
    def _clean(text: str) -> str:
        text = ' '.join(text.split())
        return ', '.join([name.strip() for name in text.split(',')])

    @staticmethod
    def _drop_empty_duplicates(artworks: dict) -> dict:
        # The archive contains some artworks twice: once with the content and once as an empty stub
        def key(artwork):
            return artwork['year'], re.sub(r'\W', '', artwork['name'].lower())

        def is_empty(artwork):
            return not (artwork['description'] or artwork['img_list'] or artwork['video_list']
                        or artwork['audio_list'])

        with_content = {key(artwork) for artwork in artworks.values() if not is_empty(artwork)}
        duplicates = [k for k, artwork in artworks.items() if is_empty(artwork) and key(artwork) in with_content]
        if duplicates:
            print(f'Dropped {len(duplicates)} empty duplicates: {duplicates}')
        return {k: artwork for k, artwork in artworks.items() if k not in duplicates}

    @staticmethod
    def _sorted(artworks: dict) -> dict:
        return dict(sorted(artworks.items(), key=lambda item: (item[1]['year'], item[0].zfill(10))))

    @staticmethod
    def _load(path: str) -> dict:
        if not os.path.exists(path):
            return {}
        with open(path, encoding='utf-8') as infile:
            artworks = json.load(infile)
        # skip the data collected from the old version of the archive (other ids and urls),
        # except the artworks that are missing in the current archive and kept as legacy
        return {k: v for k, v in artworks.items()
                if v.get('legacy') or v.get('url', '').startswith(f'{ROOT_LINK}/prix/{k}/')}

    @staticmethod
    def _save(artworks: dict, path_to_save: str):
        if not path_to_save.endswith('.json'):
            path_to_save += '.json'
        with open(path_to_save, 'w', encoding='utf-8') as outfile:
            json.dump(artworks, outfile, indent=4, ensure_ascii=False)
