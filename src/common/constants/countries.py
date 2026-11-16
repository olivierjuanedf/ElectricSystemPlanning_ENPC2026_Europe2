from validators import country


def set_country_trigram(country: str) -> str:
    return f'{country[:3].lower()}'


def is_country_trigram(my_str) -> bool:
    return isinstance(my_str, str) and len(my_str) == 3 and my_str.islower()


# TODO: get list of countries from global constant...
TRIGRAMS_TO_COUNTRIES = \
    {set_country_trigram(country): country
     for country in ["benelux", "france", "germany", "iberian-peninsula", "italy", "poland", "scandinavia"]
                         }
COUNTRIES_INITIALS = {"benelux": "b", "france": "f", "germany": "g", "iberian-peninsula": "ip", "italy": "it",
                      "poland": "p", "scandinavia": "s"}