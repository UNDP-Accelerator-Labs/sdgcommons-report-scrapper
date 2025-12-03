"""Multi-language keywords for AcceleratorLab detection"""

ACCELERATORLAB_KEYWORDS = {
    "en": [
        "accelerator lab",
        "innovation-acclab",
        "acclab",
        "acceleratorlab",
        "AccLabGM",
        "Head of Exploration",
        "Head of Experimentation",
        "Head of Solutions Mapping"
    ],
    "fr": [
        "laboratoire d'acceleration",
        "accelerateur lab",
        "laboratoire d'accelerateur",
        "laboratoires d'acceleration",
        "laboratoires d'accelerateur",
        "accelerator lab",
        "Laboratoires d'Accélération",
        "Laboratoires d'Accélération"
    ],
    "es": [
        "laboratorios de aceleracion",
        "laboratorio de aceleracion",
        "LabPNUDArg",
        "Aceleración del PNUD"
    ],
    "pt": [
        "laboratorios aceleradores",
        "laboratorio acelerador",
        "acclab",
        "Laboratório de Aceleração"
    ],
    "uk": [
        "Лабораторії інноваційного розвитку",
        "Лабораторія інноваційного розвитку"
    ],
    "az": ["akselerator laboratoriyası"],
    "tr": ["Hızlandırma laboratuvarı"],
    "sr": ["laboratorija za ubrzani razvoj"],
    "uz": ["akselerator laboratoriyasi"],
    "ru": ["Акселератор Лаборатория"]
}

# Flatten all keywords for easy searching
ALL_KEYWORDS_FLAT = []
for lang_keywords in ACCELERATORLAB_KEYWORDS.values():
    ALL_KEYWORDS_FLAT.extend([kw.lower() for kw in lang_keywords])
