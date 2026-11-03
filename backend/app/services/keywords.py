"""Google Maps search terms for food & beverage in Japan, grouped for the Scout picker.

Japanese terms match what owners type into their Google Business listing, so they recall far
better than English ones; the English column is for the UI only. Each selected term is searched in
every cell, so cost scales linearly with the number of terms.
"""

# (group key, label, [(term, english, hint)])
GROUPS = [
    ("drink", "Izakaya & drinking", [
        ("居酒屋", "Izakaya", "pub-restaurant"),
        ("大衆酒場", "Taishu sakaba", "cheap local tavern"),
        ("立ち飲み", "Tachinomi", "standing bar"),
        ("角打ち", "Kakuuchi", "liquor-shop bar"),
        ("焼き鳥", "Yakitori", "grilled skewers"),
        ("串カツ", "Kushikatsu", "fried skewers, Osaka"),
        ("おでん", "Oden", "simmered hotpot bar"),
        ("炉端焼き", "Robatayaki", "hearth grill"),
        ("日本酒バー", "Sake bar", "nihonshu specialist"),
        ("ビアホール", "Beer hall", "draught beer"),
    ]),
    ("bar", "Bars & night", [
        ("バー", "Bar", "cocktail / shot bar"),
        ("スナック", "Snack bar", "mama-san bar"),
        ("ワインバー", "Wine bar", ""),
        ("ダイニングバー", "Dining bar", "food-led bar"),
        ("クラフトビール", "Craft beer", "taproom"),
        ("ホルモン", "Horumon", "offal grill, late"),
        ("カラオケ", "Karaoke", "food & drink sales"),
    ]),
    ("noodle", "Noodles", [
        ("ラーメン", "Ramen", ""),
        ("つけ麺", "Tsukemen", "dipping noodles"),
        ("うどん", "Udon", ""),
        ("そば", "Soba", ""),
        ("中華そば", "Chuka soba", "classic shoyu ramen"),
        ("担々麺", "Tantanmen", ""),
    ]),
    ("washoku", "Washoku", [
        ("和食", "Washoku", "Japanese restaurant, umbrella"),
        ("寿司", "Sushi", ""),
        ("回転寿司", "Kaiten sushi", "conveyor, chains"),
        ("天ぷら", "Tempura", ""),
        ("とんかつ", "Tonkatsu", ""),
        ("割烹", "Kappo", "counter fine dining"),
        ("懐石", "Kaiseki", "course dining"),
        ("うなぎ", "Unagi", "eel"),
        ("定食", "Teishoku", "set-meal diner"),
        ("海鮮", "Kaisen", "seafood"),
        ("ふぐ", "Fugu", "blowfish"),
        ("しゃぶしゃぶ", "Shabu-shabu", ""),
        ("すき焼き", "Sukiyaki", ""),
    ]),
    ("grill", "Meat & konamon", [
        ("焼肉", "Yakiniku", "table BBQ"),
        ("ステーキ", "Steak", ""),
        ("鉄板焼き", "Teppanyaki", ""),
        ("お好み焼き", "Okonomiyaki", "Osaka staple"),
        ("たこ焼き", "Takoyaki", "street stall, cash-heavy"),
        ("もんじゃ焼き", "Monjayaki", ""),
        ("ジンギスカン", "Jingisukan", "lamb grill"),
        ("もつ鍋", "Motsunabe", "offal hotpot"),
    ]),
    ("cafe", "Cafe & sweets", [
        ("カフェ", "Cafe", ""),
        ("喫茶店", "Kissaten", "retro coffee house"),
        ("コーヒー", "Coffee", "specialty roasters"),
        ("パン屋", "Bakery", ""),
        ("ケーキ", "Cake shop", "patisserie"),
        ("和菓子", "Wagashi", "Japanese sweets"),
        ("甘味処", "Kanmidokoro", "tea & sweets"),
        ("抹茶", "Matcha", "matcha cafes & tea stands"),
        ("かき氷", "Kakigori", "shaved ice"),
        ("クレープ", "Crepe", "takeaway stand"),
    ]),
    ("world", "World cuisine", [
        ("中華料理", "Chinese", ""),
        ("餃子", "Gyoza", ""),
        ("韓国料理", "Korean", ""),
        ("イタリアン", "Italian", ""),
        ("フレンチ", "French", ""),
        ("ビストロ", "Bistro", ""),
        ("スペイン料理", "Spanish", "bar / bal"),
        ("インド料理", "Indian", ""),
        ("タイ料理", "Thai", ""),
        ("ベトナム料理", "Vietnamese", ""),
        ("洋食", "Yoshoku", "Japanese-Western diner"),
        ("ハンバーガー", "Burger", ""),
        ("ピザ", "Pizza", ""),
    ]),
    ("quick", "Quick & takeaway", [
        ("カレー", "Curry", ""),
        ("牛丼", "Gyudon", "beef bowl, chains"),
        ("丼", "Donburi", "rice bowls"),
        ("弁当", "Bento", "takeaway boxes"),
        ("おにぎり", "Onigiri", ""),
        ("唐揚げ", "Karaage", "fried chicken"),
        ("食堂", "Shokudo", "local canteen"),
        ("レストラン", "Restaurant", "catch-all"),
    ]),
]

# Quick packs: one click selects the set
PACKS = [
    ("core", "Core categories", "One umbrella term per category; each pulls in its sub-genres "
     "(e.g. 居酒屋 → yakitori, standing bars, kushikatsu; 和食 → soba, tempura, kappo)",
     ["レストラン", "居酒屋", "バー", "スナック", "カフェ", "ラーメン", "和食", "焼肉", "寿司", "抹茶", "パン屋"]),
    ("nightlife", "Nightlife core", "Evening drinking venues: high card-terminal intent",
     ["居酒屋", "大衆酒場", "立ち飲み", "焼き鳥", "串カツ", "バー", "スナック", "ホルモン"]),
    ("osaka", "Osaka staples", "Konamon and kushikatsu counters, often cash-only",
     ["お好み焼き", "たこ焼き", "串カツ", "鉄板焼き", "立ち飲み", "ホルモン"]),
    ("lunch", "Lunch traffic", "Fast-turnover daytime spots",
     ["ラーメン", "うどん", "そば", "定食", "カレー", "丼", "食堂", "弁当"]),
    ("cafe", "Cafe & bakery", "Morning and afternoon trade",
     ["カフェ", "喫茶店", "コーヒー", "パン屋", "ケーキ", "和菓子", "甘味処"]),
    ("dining", "Sit-down dining", "Higher ticket, reservation-led",
     ["寿司", "焼肉", "割烹", "天ぷら", "イタリアン", "フレンチ", "中華料理", "しゃぶしゃぶ"]),
    ("sweep", "Full F&B sweep", "Broad catch-all with the fewest calls",
     ["レストラン", "居酒屋", "カフェ", "バー", "ラーメン", "焼肉", "寿司", "中華料理"]),
]


def catalogue() -> dict:
    return {
        "groups": [
            {"key": key, "label": label, "terms": [{"jp": jp, "en": en, "hint": hint} for jp, en, hint in terms]}
            for key, label, terms in GROUPS
        ],
        "packs": [{"key": k, "label": l, "brief": b, "terms": t} for k, l, b, t in PACKS],
    }


def english_for(term: str) -> str:
    for _, _, terms in GROUPS:
        for jp, en, _ in terms:
            if jp == term:
                return en
    return ""
