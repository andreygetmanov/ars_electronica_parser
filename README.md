# Ars Electronica Archive parser

Parses data from [Ars Electronica Archive](https://archive.aec.at/prix/) to a json file.

The data contains info about artwork's name, authors, award, year of nomination, category, description (catalog text), credits, authors' biography, jury statement, lists of links to artwork's photos, videos and audio files, and also a link to the artwork itself. 

Just run `main.py` to use the parser. 
You can filter the required artworks by years, awards and nominations.
If the json already exists, the parser only collects the artworks missing in it, so an interrupted run can be continued and new years can be added.

Full Ars Electronica Archive (1987–2026) is available in the **data** folder:
* `ars_electronica_prizewinners.json` — the data from the current version of the archive. 
Records collected from the previous version of the archive have the `old_id` field (their key in the old data and in `ars_electronica_prizewinners_ru.json`). 
Artworks that are missing in the current archive are kept from the previous version with `"legacy": true` (their urls no longer work).
* `ars_electronica_prizewinners_ru.json` — the data with descriptions translated to Russian.

If you have any questions, feel free to write me in Telegram:
[@AGet_man_off](https://t.me/AGet_man_off).

I will be happy, if you star⭐ my repo.

*License: GNU General Public License v3.0*