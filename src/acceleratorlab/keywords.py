"""Multi-language keywords for AcceleratorLab detection"""

ACCELERATORLAB_KEYWORDS = {
    "en": [
        "accelerator lab",
        "accelerator labs",
        "innovation-acclab",
        "acclab",
        "acceleratorlab",
        "united nations accelerator lab",
        "undp accelerator lab",
        "AccLabGM",
        "Head of Exploration",
        "Head of Experimentation",
        "Head of Solutions Mapping"
    ],
    "fr": [
        "laboratoire d'acceleration",
        "laboratoires d'acceleration",
        "laboratoire d'accélération",
        "laboratoires d'accélération",
        "laboratoire d'innovation",
        "laboratoires d'innovation",
        "accélérateur",
        "accélérateurs",
        "accelerateur lab",
        "accelerator lab",
        "Laboratoires d'Accélération",
        "laboratoire d'accélération des Nations unies",
        "Laboratoire d'accélération du PNUD",
        "Responsable de l'exploration",
        "Responsable de l'expérimentation",
        "Responsable de la cartographie des solutions"
    ],
    "es": [
        "laboratorios de aceleracion",
        "laboratorio de aceleracion",
        "laboratorio de innovación",
        "laboratorios de innovación",
        "labpnudarg",
        "lab pnud",
        "aceleracion del pnud",
        "acelerador",
        "aceleradores",
        "laboratorio de aceleración",
        "laboratorios de aceleración",
        "laboratorio de aceleración de las Naciones Unidas",
        "Laboratorio de Aceleración del PNUD",
        "Jefe de Exploración",
        "Responsable de Exploración",
        "Responsable de Experimentación",
        "Responsable de mapeo de soluciones"
    ],
    "pt": [
        "laboratorios aceleradores",
        "laboratorio acelerador",
        "laboratorio de inovação",
        "laboratorios de inovação",
        "acclab",
        "laboratório de aceleração",
        "acelerador",
        "aceleradores",
        "Laboratório de Aceleração",
        "laboratório de aceleração das Nações Unidas",
        "Laboratório de Aceleração do PNUD",
        "Responsável pela Exploração",
        "Responsável pela Experimentação",
        "Responsável pelo Mapeamento de Soluções"
    ],
    "uk": [
        "Лабораторії інноваційного розвитку",
        "Лабораторія інноваційного розвитку",
        "лабораторія акселерації",
        "лабораторія акселераторів",
        "керівник з досліджень",
        "керівник з експериментів",
        "керівник з картографії рішень"
    ],
    "az": ["akselerator laboratoriyası"],
    "tr": ["Hızlandırma laboratuvarı"],
    "sr": ["laboratorija za ubrzani razvoj"],
    "uz": ["akselerator laboratoriyasi"],
    "ru": ["Акселератор Лаборатория", "лаборатория акселератора", "лаборатория инноваций", "лаборатория акселерации ООН", "лаборатория акселерации ПРООН", "Руководитель по исследованиям", "Руководитель по экспериментам", "Руководитель по картированию решений"],
    "ar": ["مختبر المسرع", "مختبرات المسرع", "مختبر الابتكار", "مختبرات الابتكار"]
}

# Flatten all keywords for easy searching
ALL_KEYWORDS_FLAT = []
for lang_keywords in ACCELERATORLAB_KEYWORDS.values():
    ALL_KEYWORDS_FLAT.extend([kw.lower() for kw in lang_keywords])
