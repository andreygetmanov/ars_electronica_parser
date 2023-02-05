import json

import requests
from typing import Union
from bs4 import BeautifulSoup
from tqdm import tqdm

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
    'Media Art.Research Award': 'LBI',
    'u19': 'U19',
    'Visionary Pioneers': 'VP',
    'Klasse! Lernen': 'KL',
    'Artificial Intelligence & Life Art': 'AI',
    'Digital Humanity': 'DH'
}

AWARDS = {
    'All': -1,
    'Submissions with Award': -2,
    'Golden Nica': 1,
    'Award of Distinction': 2,  # Auszeichnung
    'Honorary Mention': 3,  # Anerkennung
    'Grant': 5,  # Stipendium
    'Special Prize': 4,  # Sonderpreise
    'Nomination': 20  # Nominierung
}


class Parser:
    """
    A class that parses data from the ArsElectronica Archive.

    Attributes
    ----------
    headers : dict
        A dictionary containing the headers for the HTTP request.
    data : dict
        A dictionary containing the data for the HTTP request.
    params : dict
        A dictionary containing the parameters for the HTTP request.
    """

    def __init__(self):
        self.headers = {'Accept-Language': 'en-US'}
        self.data = {'languageform_select': 'en'}
        self.params = {'lang': 'en'}

    def parse_data(self,
                   award: Union[list, str] = 'All',
                   category: Union[list, str] = 'All',
                   years: Union[list, range] = range(1987, 2023),
                   path_to_save: str = 'data/ars_electronica_prizewinners.json'):
        """
        Retrieves the data of artworks in Interactive Art category for the given years and saves it to json.

        Parameters
        ----------
        award : Union[list, str]
            The name/list of names of award for which the data should be retrieved (-1 for all).
        category: Union[list, str]
            The name/list of names of category for which the data should be retrieved (-1 for all).
        years : Union[list, range]
            The list/range of years for which the data should be retrieved.
        path_to_save : str
            The path where the json with data will be saved
        """
        print(f'Collecting works of {category} category with {award} award from {years[0]} to {years[-1]}')
        artwork_ids = self.get_ids(category, award, years)
        print(f'Collected {len(artwork_ids)} artworks')
        artworks = {}
        print('Data parsing has started')
        for artwork_id in tqdm(artwork_ids):
            url = f'https://archive.aec.at/prix/showmode/{artwork_id}/'
            data = self.get_data(url)
            artworks[artwork_id] = data
        print('Parsing finished. Saving the data to json...')
        self._save(artworks, path_to_save)
        print(f'Completed! Saved to {path_to_save}')

    def get_ids(self, category: Union[list, str], award: Union[list, str], years: Union[list, range]):
        """
        Retrieves the ids of artworks in Interactive Art category for the given years.

        Parameters
        ----------
        award : Union[list, str]
            The name/list of names of award for which the data should be retrieved (-1 for all).
        category: Union[list, str]
            The name/list of names of category for which the data should be retrieved (-1 for all).
        years : Union[list, range]
            The list/range of years for which the data should be retrieved.

        Returns
        -------
        id_list : list
            A list containing ids of artworks for the given years:
        """
        if isinstance(category, str):
            category = [category]
        if isinstance(award, str):
            award = [award]
        id_list = []
        for cat in category:
            for aw in award:
                for year in years:
                    cat_id = CATEGORIES[cat]
                    aw_id = AWARDS[aw]
                    url = f'https://archive.aec.at/winners/?category={cat_id}&award={aw_id}&searchstring=&years=&artist_letters=&year={year}'
                    ids_data = {'languageform_select': 'en',
                                'button_winners': True}
                    ids_params = {'setlang': 'en'}
                    content = self._get_raw_html(url, self.headers, ids_data, ids_params)
                    elements = content.find_all('div', {'class': 'winner_title'})
                    ids = [el['id'].replace('winner_title_', '') for el in elements if self._contains_id(el['id'])]
                    id_list += ids
        return id_list

    def get_data(self, url: str):
        """
        Retrieves the artwork data from the given URL, parses it and returns as a dict.

        Parameters
        ----------
        url : str
            The URL of the page to be parsed.

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
                    The category of the artwork.
                - `description` : str
                    The description of the artwork.
                - 'url' : str
                    The URL to the artwork.
        """
        content = self._get_raw_html(url, self.headers, self.data, self.params)
        name = content.find_all("div", class_="row")[2].text.strip()
        authors = self._clean(
            content.find_all("div", class_="row")[3].find("div", class_='col-md-12').find("div").get_text())
        award_and_year = content.find('h3', class_='bar-color').find('img').find('span').get_text()
        award = ' '.join(award_and_year.split()[:-1])
        year = award_and_year.split()[-1]
        category = content.find('h3', {'class': 'bar-color'}).get_text().replace(award_and_year, '').strip()
        try:
            description = content.find_all("div", class_="tab-pane fade", id="tab-1")[0].get_text().strip().replace(
                '\xa0\xa0', '\n').replace('\xa0', '')
        except IndexError:
            print(f'Artwork {name} ({year}) has no description')
            description = ''

        artwork_data = {
            'name': name,
            'authors': authors,
            'award': award,
            'year': year,
            'category': category,
            'description': description,
            'url': url
        }
        return artwork_data

    @staticmethod
    def _get_raw_html(url: str, headers: dict = None, data: dict = None, params: dict = None):
        # Gets the raw html content of the given URL.
        response = requests.get(url, headers=headers, data=data, params=params)
        html_content = response.text
        return BeautifulSoup(html_content, 'html.parser')

    @staticmethod
    def _clean(text: str) -> str:
        text = text.replace("\n", "")
        text = text.replace("\t", "")
        return ', '.join([name.strip() for name in text.split(',')])

    @staticmethod
    def _contains_id(winner_title: str):
        # Checks if the title refers to a real artwork
        if len('winner_title_') == len(winner_title):
            return False
        return True

    @staticmethod
    def _save(artworks: dict, path_to_save: str):
        if '.json' not in path_to_save:
            path_to_save += '.json'
        with open(path_to_save, "w") as outfile:
            json.dump(artworks, outfile, indent=4)
