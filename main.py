from scripts.parser import Parser

"""
To parse the full archive (all years, categories and awards) just run parse_data() with default parameters.

Years can be given as list:
    years=[1987, 1995, 2000, 2010]
or as range:
    years=range(1987, 1995)

Award and category can be given as str:
    award='Golden Nica'
or as list (if multiple):
    category=['Interactive Art', 'Artificial Intelligence & Life Art']

Saving path can be given as str:
    path_to_save='data/IA_AI_prizewinners.json'

Awards:
    All
    Submissions with Award
    Golden Nica
    Award of Distinction
    Honorary Mention
    Grant
    Special Prize
    Nomination

Categories:
    All
    Computer Graphics
    Computer Animation
    Interactive Art
    Music & Sound
    Hybrid Art
    Netbased Art
    Digital Communities
    the next idea
    Media Art.Research Award
    u19
    Visionary Pioneers
    Klasse! Lernen
    Artificial Intelligence & Life Art
    Digital Humanity

Enjoy!
"""
if __name__ == '__main__':
    parser = Parser()
    parser.parse_data()
