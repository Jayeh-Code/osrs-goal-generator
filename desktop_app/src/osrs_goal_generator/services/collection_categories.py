"""Desktop presentation categories; never infer account completion from names.

Boss names reuse the bundled boss catalog. Additional mappings follow the
Collection Log plugin's page groups, with Slayer retained as an app category:
https://github.com/evansloan/collection-log/blob/master/src/main/java/com/evansloan/collectionlog/CollectionLogPage.java
Unknown/new pages deliberately remain Uncategorized.
"""
from ..boss_rates import all_boss_names

CATEGORIES = ("Bosses", "Raids", "Clues", "Minigames", "Slayer", "Other", "Uncategorized")


def _key(name: str) -> str:
    return " ".join(name.replace("\u2019", "'").split()).casefold()


_GROUPS = {
    "Bosses": (*all_boss_names(), "Callisto and Artio", "Venenatis and Spindel",
               "Vet'ion and Calvar'ion", "The Fight Caves", "The Inferno",
               "Royal Titans", "Fortis Colosseum", "Dagannoth Kings", "The Nightmare"),
    "Raids": ("Chambers of Xeric", "Chambers of Xeric: Challenge Mode",
              "Theatre of Blood", "Theatre of Blood: Hard Mode",
              "Tombs of Amascut", "Tombs of Amascut: Expert Mode"),
    "Clues": ("Beginner Treasure Trails", "Easy Treasure Trails", "Medium Treasure Trails",
              "Hard Treasure Trails", "Elite Treasure Trails", "Master Treasure Trails",
              "Hard Treasure Trails (Rare)", "Elite Treasure Trails (Rare)",
              "Master Treasure Trails (Rare)", "Shared Treasure Trail Rewards"),
    "Minigames": ("Barbarian Assault", "Brimhaven Agility Arena", "Castle Wars",
                  "Fishing Trawler", "Giants' Foundry", "Gnome Restaurant",
                  "Guardians of the Rift", "Hallowed Sepulchre", "Last Man Standing",
                  "Magic Training Arena", "Mage Training Arena", "Mahogany Homes",
                  "Pest Control", "Rogues' Den", "Shades of Mort'ton", "Soul Wars",
                  "Temple Trekking", "Tithe Farm", "Trouble Brewing", "Volcanic Mine"),
    "Slayer": ("Slayer",),
    "Other": ("Aerial Fishing", "All Pets", "Skilling Pets", "Miscellaneous",
              "Champion's Challenge", "Chompy Bird Hunting", "Creature Creation",
              "Cyclopes", "Elder Chaos Druids", "Fossil Island Notes", "Glough's Experiments",
              "Monkey Backpacks", "Motherlode Mine", "My Notes", "Random Events",
              "Revenants", "Rooftop Agility", "Shayzien Armour", "Shooting Stars", "TzHaar"),
}
# More specific groups override broad boss-catalog entries, notably raids.
PAGE_CATEGORIES = {_key(name): category for category, names in _GROUPS.items() for name in names}


def collection_page_category(name: str) -> str:
    return PAGE_CATEGORIES.get(_key(name), "Uncategorized")
