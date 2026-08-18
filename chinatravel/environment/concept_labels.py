"""Legacy label mappings used only by offline sandbox migration and audits."""


LEGACY_ENGLISH_CONCEPT_VALUE_ALIASES = {
    "attraction": {
        "Art Museum": "Art museum",
        "Cultural Attractions": "Cultural Landscape",
        "Historical Site": "historical site",
        "Natural Scenery": "natural scenery",
        "Park": "park",
        "red tourism sites": "Red tourism sites",
        "university campus": "University campus",
    },
    "restaurant": {
        "Bread and Desserts": "Bakery and Desserts",
        "cafe": "coffee shop",
        "Fast food and simple meals": "Fast food and casual dining",
        "hot pot": "Hot pot",
    },
    "accommodation": {
        "Air Purifier": "Air purifier",
        "Bed and Breakfast": "homestay",
        "Bed and breakfast": "homestay",
        "Designer Hotel": "Designer hotel",
        "Family Theme Room": "Family-themed room",
        "Family-themed Room": "Family-themed room",
        "Great View from the Window": "Great view from the window",
        "Scenic Window View": "Great view from the window",
        "Instagrammable swimming pool": "Instagrammable pool",
        "Chess and Card Room": "Mahjong and Card Game Room",
        "Mahjong and Card Room": "Mahjong and Card Game Room",
        "Serviced Apartment": "Hotel Apartment",
        "small but beautiful": "small and beautiful",
        "SPA": "Spa",
        "Stunning night views": "Stunning Night Views",
        "Swimming pool": "Swimming Pool",
        "viral swimming pool": "Instagrammable pool",
    },
}

LEGACY_ENGLISH_CONCEPT_LITERAL_ALIASES = {
    alias: canonical
    for aliases in LEGACY_ENGLISH_CONCEPT_VALUE_ALIASES.values()
    for alias, canonical in aliases.items()
}
