"""Local tips keyed by country (inherited by its cities) or city; IDs derive from list position, so append only."""

from app.data.countries import COUNTRIES as _COUNTRIES

COUNTRY_TIPS: dict[str, list[dict]] = {
    "Vietnam": [
        {
            "category": "money",
            "title": "Cash is king — carry small notes",
            "content": "The Vietnamese dong comes in large numbers; many small shops, markets and taxis are cash-only. Withdraw from bank ATMs and keep small denominations for street food and rides.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Use Grab instead of hailing taxis",
            "content": "The Grab app (cars and motorbikes) shows the price up front, so you avoid meter tampering. If taking a street taxi, stick to Vinasun or Mai Linh.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Watch bags on the street",
            "content": "Drive-by bag-snatching by motorbike happens in big cities. Keep phones and bags on the side away from the road and don't text while walking near traffic.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Street food is safe — pick busy stalls",
            "content": "Vietnamese street food is a highlight. Choose stalls with high turnover and locals queuing; that's the freshness signal. Drink bottled or filtered water.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Remove shoes and dress modestly at temples",
            "content": "Take shoes off when entering temples and homes, and cover shoulders and knees at religious sites. Use both hands when giving or receiving something from elders.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Buy a local eSIM or SIM on arrival",
            "content": "Viettel, Mobifone and Vinaphone sell cheap tourist data SIMs at airports. An eSIM bought before you fly works the moment you land.",
            "is_essential": False,
        },
        {
            "category": "language",
            "title": "A few words go a long way",
            "content": "'Xin chào' (hello), 'cảm ơn' (thank you). English is common in tourist areas but limited elsewhere — a translation app helps.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "The country has three climates",
            "content": "North, central and south Vietnam have different seasons. Broadly, Nov–Apr is drier in the south; the central coast is best Feb–Aug; avoid the Sep–Nov storm season on the central coast.",
            "is_essential": False,
        },
    ],
    "Thailand": [
        {
            "category": "transport",
            "title": "Grab and metered taxis over tuk-tuks",
            "content": "Tuk-tuks are fun but overcharge tourists and may detour to commission shops. Use Grab or insist on the meter ('meter, please') in taxis.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Carry cash, watch ATM fees",
            "content": "Thai ATMs charge a fixed foreign-card fee (~220 THB) per withdrawal, so take out larger amounts less often. Cash is needed for markets and street stalls.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Never disrespect the monarchy or Buddha images",
            "content": "Insulting the royal family is a serious crime. Don't point feet at people or Buddha images, don't touch anyone's head, and dress modestly at temples.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Common scams: gem shops and 'closed' temples",
            "content": "Ignore strangers who say a temple is closed and offer a tuk-tuk tour — it ends at a gem or tailor shop. Agree all prices before getting in.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Street food is excellent and cheap",
            "content": "Thailand's street food is world-class. Pick busy stalls, and tell vendors 'mai phet' if you want it less spicy. Drink bottled water.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Sun and heat are intense",
            "content": "Stay hydrated, use high-SPF sunscreen, and pace yourself midday. Mosquito repellent is worth carrying, especially in the rainy season.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Cheap tourist SIMs everywhere",
            "content": "AIS, TrueMove and dtac sell tourist data SIMs at airports and 7-Elevens for a few dollars. Coverage is good even on islands.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Cool season is Nov–Feb",
            "content": "Nov–Feb is dry and comfortable. Mar–May is very hot; Jun–Oct is the rainy season — showers are short but the Andaman coast can be rough.",
            "is_essential": False,
        },
    ],
    "Singapore": [
        {
            "category": "transport",
            "title": "The MRT covers almost everywhere",
            "content": "Singapore's MRT and bus network is clean, cheap and efficient. Tap any contactless bank card or buy an EZ-Link card — no need for taxis most of the time.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Cards accepted nearly everywhere",
            "content": "Contactless payment works almost universally, including hawker centres. Carry a little cash for the smallest stalls.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Very safe — but strict laws",
            "content": "Crime is very low. However fines are heavy: no eating or drinking on the MRT, no littering, no jaywalking, and chewing gum is restricted. Drug laws are extremely severe.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Eat at hawker centres",
            "content": "Hawker centres serve cheap, excellent food. To reserve a table locals leave a packet of tissues on it — respect that custom.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Tap water is safe to drink",
            "content": "Singapore tap water meets WHO standards — refill your bottle freely. The heat and humidity are constant, so hydrate often.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Hot and humid all year",
            "content": "Singapore is warm and humid year-round with no real seasons. Feb–Apr is slightly drier; Nov–Jan sees more rain but showers are brief.",
            "is_essential": False,
        },
    ],
    "Japan": [
        {
            "category": "money",
            "title": "Carry cash despite the tech image",
            "content": "Japan is still cash-heavy — many small restaurants, shrines and shops don't take cards. 7-Eleven ATMs reliably accept foreign cards.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Get an IC card; consider the JR Pass",
            "content": "A Suica or Pasmo IC card works on trains, buses and convenience stores nationwide. If doing long intercity travel, price-check the Japan Rail Pass first.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Quiet trains, no tipping, no eating while walking",
            "content": "Keep phone calls off trains, don't tip (it can offend), and avoid eating while walking. Bow slightly as a greeting and thanks.",
            "is_essential": True,
        },
        {
            "category": "culture",
            "title": "Carry your own rubbish",
            "content": "Public bins are rare. Carry a small bag for your trash until you find one — often near convenience stores or stations.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Rent pocket Wi-Fi or buy an eSIM",
            "content": "Free public Wi-Fi is patchy. A data eSIM or a rented pocket Wi-Fi router keeps maps and translation working everywhere.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Spring and autumn are peak",
            "content": "Late Mar–Apr (cherry blossom) and Oct–Nov (autumn leaves) are beautiful but busy. Summer is hot and humid; winter is great for snow and onsen.",
            "is_essential": False,
        },
    ],
    "Malaysia": [
        {
            "category": "money",
            "title": "Carry ringgit cash for small spots",
            "content": "Cards are widely accepted in malls and chains, but hawker stalls, markets and small towns are cash-only. Bank ATMs give the best rate; tell your bank you're travelling.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Grab is the default ride app",
            "content": "Grab works nationwide and shows prices up front, avoiding metered-taxi disputes. In KL the LRT/MRT and KTM trains are cheap and beat the traffic.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Watch for bag-snatching on motorbikes",
            "content": "Drive-by snatch theft happens in cities — walk on the side away from the road and keep bags cross-body. Otherwise Malaysia is generally safe and easy.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Dress modestly; respect Muslim customs",
            "content": "Malaysia is majority Muslim. Cover shoulders and knees at mosques (robes are usually lent), use your right hand for giving and eating, and avoid public displays of affection.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Hawker centres and kopitiams are the heart of the food scene",
            "content": "Nasi lemak, char kway teow and roti canai are cheap and superb at hawker stalls. Tap water should be boiled or filtered — stick to bottled.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Cheap prepaid SIMs at the airport",
            "content": "Maxis, Celcom and Digi sell tourist data SIMs at airport kiosks and convenience stores. Coverage is strong in cities and along the peninsula.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Two monsoons, so timing depends on the coast",
            "content": "The west coast and islands (Penang, Langkawi) are best Dec–Apr; the east coast (Perhentians, Tioman) is best Mar–Oct and largely shuts in the Nov–Feb monsoon.",
            "is_essential": False,
        },
    ],
    "Indonesia": [
        {
            "category": "money",
            "title": "Cash in rupiah, and use bank ATMs only",
            "content": "Outside hotels and big restaurants, Indonesia runs on cash. Use ATMs attached to banks (BCA, Mandiri) to avoid skimming, and check the machine before inserting your card.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Gojek and Grab for rides everywhere",
            "content": "Gojek and Grab offer cars and motorbike taxis at fixed app prices — far easier than haggling. On Bali, scooter rental is common but requires care and an international permit.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Volcanoes, currents and traffic are the real risks",
            "content": "Heed volcano and tsunami advisories, never swim against rip currents on south-coast beaches, and ride scooters cautiously. Petty theft happens but violent crime against tourists is rare.",
            "is_essential": True,
        },
        {
            "category": "health",
            "title": "Mind 'Bali belly' and mosquito-borne illness",
            "content": "Drink only bottled or filtered water and be cautious with ice and raw produce. Dengue is present, so use repellent, especially at dawn and dusk.",
            "is_essential": False,
        },
        {
            "category": "culture",
            "title": "Respect temple dress codes and offerings",
            "content": "A sarong and sash are required at Balinese temples (usually provided or rented). Don't step on the small daily canang sari offerings left on pavements and doorsteps.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Telkomsel has the widest coverage",
            "content": "Telkomsel reaches the most islands; an eSIM bought before arrival saves queuing. Wi-Fi is good in Bali and Jakarta but patchy in remote areas.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Dry season is roughly Apr–Oct",
            "content": "The dry season (Apr–Oct) is best across most of the archipelago, with Jul–Aug the peak. The Nov–Mar wet season brings heavy afternoon downpours.",
            "is_essential": False,
        },
    ],
    "Philippines": [
        {
            "category": "money",
            "title": "Carry peso cash, especially on islands",
            "content": "Cards work in Manila and Cebu malls, but island provinces, ferries and small eateries are cash-only and ATMs can be scarce or empty. Stock up before heading remote.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Domestic flights and ferries link the islands",
            "content": "With 7,000+ islands, budget airlines (Cebu Pacific, AirAsia) and ferries are how you get around — book ahead. In cities, use Grab; jeepneys are cheap but confusing for newcomers.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Check advisories for parts of Mindanao",
            "content": "Most of the country is welcoming and safe, but parts of western/central Mindanao and the Sulu Sea carry official travel warnings. Watch belongings in crowded Manila areas.",
            "is_essential": True,
        },
        {
            "category": "language",
            "title": "English is widely spoken",
            "content": "English is an official language and spoken almost everywhere, making the Philippines one of Asia's easiest countries to navigate for English speakers.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Try the regional specialities",
            "content": "Adobo, sinigang, lechon and halo-halo are staples; Cebu is famous for its roast pork. Drink bottled water and be a little cautious with street food.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Globe and Smart prepaid SIMs",
            "content": "Globe and Smart sell tourist SIMs at airport arrival halls. Coverage is reliable in cities but thin on remote islands — download offline maps.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Dry season Dec–May; typhoons Jun–Nov",
            "content": "Dec–Feb is dry and cooler; Mar–May is hot. The Jun–Nov typhoon season can disrupt ferries and flights, so build slack into island-hopping plans.",
            "is_essential": False,
        },
    ],
    "Cambodia": [
        {
            "category": "money",
            "title": "The US dollar is everyday currency",
            "content": "Prices are quoted and paid in US dollars; Cambodian riel is used as 'change' for amounts under a dollar. Bring clean, untorn small-denomination USD notes — damaged bills are refused.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Tuk-tuks and ride apps in towns",
            "content": "Tuk-tuks are the main way around Phnom Penh and Siem Reap; the PassApp and Grab apps give fixed fares and save haggling. Agree the price before any non-app ride.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Bag-snatching and unexploded ordnance",
            "content": "Drive-by phone and bag snatching is common in Phnom Penh — keep bags away from the road. In rural areas stick to marked paths; landmines and UXO remain in some regions.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Dress respectfully at Angkor and temples",
            "content": "Cover shoulders and knees to enter Angkor temples and pagodas — it is enforced at Angkor Wat. Return the 'sampeah' (palms-together) greeting and don't touch people's heads.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Heat, water and mosquitoes",
            "content": "It gets very hot — hydrate and pace temple visits for early morning. Drink bottled water and use repellent; dengue and malaria exist in rural areas.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Cheap, fast data SIMs",
            "content": "Cellcard, Smart and Metfone sell inexpensive data SIMs with generous allowances; coverage is good around the main towns and Angkor.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Cool dry season is Nov–Feb",
            "content": "Nov–Feb is dry and relatively cool — the best time for Angkor. Mar–May is punishingly hot; Jun–Oct is the wet season with lush scenery and fewer crowds.",
            "is_essential": False,
        },
    ],
    "Laos": [
        {
            "category": "money",
            "title": "Cash-heavy — carry kip, and some USD or baht",
            "content": "Laos runs almost entirely on cash; ATMs exist in towns but have low withdrawal limits and can be unreliable. The kip is the local currency, but USD and Thai baht are sometimes accepted.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Slow roads — the new fast train helps",
            "content": "Mountain roads make bus journeys long and winding; the China–Laos railway now links Vientiane, Vang Vieng and Luang Prabang quickly and cheaply, so book train seats ahead.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Stick to marked paths — UXO risk",
            "content": "Laos is heavily contaminated with unexploded ordnance from past wars. Never wander off established trails in rural areas, and don't touch unidentified metal objects.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Be calm, modest and quiet",
            "content": "Lao culture values composure — avoid raised voices and public anger. Dress modestly, especially at temples and the Luang Prabang alms-giving, which tourists should watch quietly and from a distance.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Water, food hygiene and mosquitoes",
            "content": "Drink bottled or filtered water and be careful with street food in smaller towns. Dengue and malaria occur in rural areas — use repellent and consider a net.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Unitel and Lao Telecom SIMs",
            "content": "Local SIMs from Unitel or Lao Telecom are cheap and cover the main towns. Connections slow down in the mountains, so download maps offline.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Best Nov–Feb; avoid the March haze",
            "content": "Nov–Feb is cool and dry — ideal for travel. Mar–Apr brings heat and slash-and-burn smoke haze in the north; May–Oct is the green, rainy season.",
            "is_essential": False,
        },
    ],
    "Myanmar": [
        {
            "category": "money",
            "title": "Bring pristine US dollars; cards rarely work",
            "content": "International cards and ATMs are largely unusable due to sanctions, so bring enough USD cash for your whole trip — crisp, unfolded, unmarked bills only, as worn notes are rejected.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Check current advisories before travelling",
            "content": "Myanmar has ongoing armed conflict and instability; many areas are off-limits and conditions change fast. Read your government's travel advisory carefully and avoid restricted regions.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Domestic flights over long road journeys",
            "content": "Roads are slow and some overland routes are closed to foreigners; domestic flights link Yangon, Mandalay and Bagan. Confirm which routes are currently permitted.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Strict temple etiquette",
            "content": "Remove shoes and socks completely before entering pagoda grounds, not just the buildings. Dress modestly covering shoulders and knees, and never point your feet at Buddha images.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Telenor/MPT SIMs, but expect outages",
            "content": "Local SIMs are cheap, but internet shutdowns and restrictions are common. A VPN installed in advance is widely used; don't rely on constant connectivity.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Limited medical care — be self-sufficient",
            "content": "Healthcare is basic outside Yangon; carry a stocked first-aid kit and any medication you need. Drink only bottled water and ensure travel insurance covers medical evacuation.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Cool dry season is Nov–Feb",
            "content": "Nov–Feb is the comfortable, dry window. Mar–May is extremely hot, and Jun–Oct is the rainy season with heavy monsoon downpours.",
            "is_essential": False,
        },
    ],
    "Brunei": [
        {
            "category": "money",
            "title": "Brunei dollar — Singapore dollars also accepted",
            "content": "The Brunei dollar is pegged 1:1 to the Singapore dollar, and SGD notes are accepted interchangeably. Cards work in larger shops and hotels, but carry cash for markets and small eateries.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Renting a car is easiest",
            "content": "Public transport is sparse and infrequent, and there is no widespread ride-hailing. Most visitors hire a car or rely on hotel transfers and taxis arranged in advance.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Very safe, but laws are strict",
            "content": "Crime is very low. However Brunei enforces sharia-influenced law: alcohol is banned for sale (limited personal import only), dress modestly, and behave conservatively in public.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Respect Islamic customs",
            "content": "Cover shoulders and knees, remove shoes at mosques, use your right hand, and don't eat or drink in public during Ramadan daylight hours. Public displays of affection are frowned upon.",
            "is_essential": False,
        },
        {
            "category": "culture",
            "title": "Friday is the day of rest",
            "content": "Many businesses and offices close midday Friday for prayers, and the weekend is Friday and Sunday. Plan visits to mosques and attractions around prayer times.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "DST and imagine SIMs",
            "content": "Prepaid SIMs from DST or imagine are available at the airport and in malls. Coverage is good across the populated coastal strip.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Hot and humid year-round",
            "content": "Brunei is tropical all year. The drier months are roughly Feb–Apr; Oct–Jan sees the heaviest rain, though showers are usually short.",
            "is_essential": False,
        },
    ],
    "Timor-Leste": [
        {
            "category": "money",
            "title": "US dollars are the official currency",
            "content": "Timor-Leste uses the US dollar; small local centavo coins are used for change. ATMs are limited to Dili and unreliable, so bring enough clean USD cash, especially for travel outside the capital.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Rough roads — 4WD and microlets",
            "content": "Roads outside Dili are poor and journeys are slow; a 4WD with a driver is the practical choice for the districts. In Dili, shared 'microlet' minibuses and taxis get you around cheaply.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Generally calm, but come prepared",
            "content": "Timor-Leste is mostly peaceful, though occasional unrest occurs around political events. Infrastructure and emergency services are limited — travel with insurance and a self-sufficient mindset.",
            "is_essential": True,
        },
        {
            "category": "health",
            "title": "Malaria, dengue and limited care",
            "content": "Malaria and dengue are present — use repellent and consider prophylaxis. Medical facilities are very basic; carry a first-aid kit and ensure insurance covers evacuation to Darwin or Bali.",
            "is_essential": False,
        },
        {
            "category": "language",
            "title": "Tetum and Portuguese, some Indonesian",
            "content": "Tetum and Portuguese are official; many people also speak Indonesian, and English is limited outside Dili. A few Tetum phrases are warmly received.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Telkomcel and Telemor SIMs",
            "content": "Local SIMs from Telkomcel or Telemor are cheap but data is slow and patchy outside Dili. Download offline maps before heading into the districts.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Dry season is May–Nov",
            "content": "May–Nov is dry, with the best road conditions and diving visibility. The Dec–Apr wet season can wash out mountain roads.",
            "is_essential": False,
        },
    ],
    "Hong Kong": [
        {
            "category": "transport",
            "title": "Get an Octopus card for everything",
            "content": "The MTR metro is fast, cheap and reaches almost everywhere. An Octopus card (or contactless bank card) works on the MTR, buses, trams, the Star Ferry and in convenience stores.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Hong Kong dollars; cards widely accepted",
            "content": "Cards and Octopus are taken nearly everywhere, but keep some HKD cash for street markets, dai pai dong food stalls and older taxis. ATMs are plentiful.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Very safe — usual big-city caution",
            "content": "Hong Kong has low crime; just watch for pickpockets in crowded markets and on the MTR. Check for any current advisories before travelling.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Dim sum, cha chaan teng and street food",
            "content": "Yum cha (dim sum) is a must, and cha chaan teng diners serve cheap local classics. Tap water is treated and considered safe, though many locals still boil it.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Easy SIMs and widespread Wi-Fi",
            "content": "Prepaid data SIMs are sold cheaply at the airport and in 7-Elevens, and free Wi-Fi is common in malls, the MTR and public spaces.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Stand right on escalators; queue properly",
            "content": "Stand on the right of escalators so others can pass on the left, and queue orderly for transport and lifts. Eating is not allowed on the MTR.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Autumn (Oct–Dec) is the sweet spot",
            "content": "Oct–early Dec is dry, sunny and comfortable. Summer is hot, humid and the typhoon season; Jan–Feb can be cool and grey.",
            "is_essential": False,
        },
    ],
    "South Korea": [
        {
            "category": "transport",
            "title": "T-money card for seamless transit",
            "content": "Buy a rechargeable T-money card at any convenience store — it works on subways, buses and taxis nationwide. Seoul's subway is extensive, signed in English and very cheap.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Cards everywhere, but carry some won",
            "content": "South Korea is highly card-friendly, even for tiny purchases. Still keep some cash for traditional markets and small rural vendors; use Global ATMs (at banks, 7-Eleven) for foreign cards.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Very safe, day and night",
            "content": "Crime against tourists is very low and it's safe to walk at night. Take normal precautions in nightlife districts, and note that fire/medical emergencies are 119, police 112.",
            "is_essential": True,
        },
        {
            "category": "connectivity",
            "title": "Fast data SIMs and ubiquitous Wi-Fi",
            "content": "Korea has some of the world's fastest internet; pick up a tourist SIM or eSIM (KT, SKT, LG U+) at the airport. Free Wi-Fi is everywhere, including the subway.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Use two hands; mind your shoes and elders",
            "content": "Give and receive money and gifts with two hands, remove shoes when entering homes and many traditional restaurants, and let elders sit and eat first.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Banchan, BBQ and spicy staples",
            "content": "Meals come with free refillable banchan side dishes. Korean BBQ, bibimbap and stews are everywhere; tap water is safe and restaurants provide free filtered water.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Spring and autumn are ideal",
            "content": "Apr–Jun (blossoms) and Sep–Nov (autumn foliage) are mild and beautiful. Summer is hot, humid and includes a rainy season; winter is cold but good for skiing.",
            "is_essential": False,
        },
    ],
}

CITY_TIPS: dict[str, list[dict]] = {
    "Hanoi": [
        {
            "category": "transport",
            "title": "Crossing the road: walk slow and steady",
            "content": "Traffic won't stop for you, but it will flow around you. Step out at a steady, predictable pace — don't run or freeze — and motorbikes will avoid you.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Old Quarter 'train street' has restricted access",
            "content": "The famous train-track cafés are periodically closed by authorities for safety. Go with a café that has current access and never linger on the tracks.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Try egg coffee — a Hanoi original",
            "content": "Cà phê trứng (egg coffee) was invented here. Pair it with a bowl of bún chả, the city's signature grilled-pork noodle dish.",
            "is_essential": False,
        },
    ],
    "Ho Chi Minh City": [
        {
            "category": "safety",
            "title": "Phone-snatching hotspots in District 1",
            "content": "Drive-by snatching is common around Bui Vien and busy District 1 streets. Don't hold your phone out near the kerb; use a cross-body bag.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Grab bikes beat the traffic",
            "content": "For short hops, a GrabBike is faster and cheaper than a car in HCMC's dense traffic. Helmets are provided.",
            "is_essential": False,
        },
    ],
    "Bangkok": [
        {
            "category": "transport",
            "title": "BTS Skytrain and river boats skip the gridlock",
            "content": "Bangkok traffic is severe. The BTS Skytrain, MRT and Chao Phraya express boats are the fastest way across the city.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "The Grand Palace is open — ignore 'closed today'",
            "content": "Anyone outside saying the Grand Palace or a temple is closed for a holiday is running the gem-shop scam. Walk to the official entrance and check yourself.",
            "is_essential": True,
        },
    ],
    "Kuala Lumpur": [
        {
            "category": "transport",
            "title": "Don't confuse KL Sentral with KLCC",
            "content": "KL Sentral is the main transport hub; KLCC is the Petronas Towers area. The free GOKL city bus loops the centre, and the LRT/MRT spares you KL's heavy traffic.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Bukit Bintang touts and inflated bills",
            "content": "Around Bukit Bintang and Jalan Alor, ignore touts pushing clubs and check menu prices before ordering at seafood stalls — some bill 'market price' at tourist rates.",
            "is_essential": False,
        },
    ],
    "Bali": [
        {
            "category": "transport",
            "title": "Book Grab/Gojek away from the rank",
            "content": "Local taxi 'mafias' bar app rides at some beaches and tourist spots — order a Grab or Gojek a short walk away, or use the metered Blue Bird taxi.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Use bank ATMs, watch the money changers",
            "content": "Use ATMs at bank branches and decline machines offering odd rates. Authorised money changers should count in front of you — walk away from any that rush or distract you.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Monkeys at Ubud and Uluwatu grab loose items",
            "content": "At the Ubud Monkey Forest and Uluwatu temple, monkeys snatch sunglasses, phones and bags. Keep valuables zipped away and don't tease or feed them.",
            "is_essential": False,
        },
    ],
    "Seoul": [
        {
            "category": "transport",
            "title": "Subway exit numbers are your map",
            "content": "Seoul's subway exits are numbered and signed precisely — directions are usually given as 'Exit 6'. Use Naver Map or KakaoMap, as Google Maps walking/transit directions are limited in Korea.",
            "is_essential": True,
        },
        {
            "category": "culture",
            "title": "Free hanbok = free palace entry",
            "content": "Wearing a hanbok (rentable near Gyeongbokgung) gets you free admission to the major palaces. Many shops near the gates rent them by the hour.",
            "is_essential": False,
        },
    ],
}

COUNTRY_SUMMARIES: dict[str, str] = {
    "Vietnam": "Vietnam is rewarding and affordable, with superb food and friendly people. Carry cash, use Grab to avoid taxi overcharging, and stay alert to motorbike bag-snatching in the cities.",
    "Thailand": "Thailand is easy and welcoming for travellers, with brilliant street food and good transport. Use Grab or metered taxis, treat the monarchy and Buddhism with respect, and ignore strangers steering you to gem shops.",
    "Singapore": "Singapore is ultra-safe, clean and efficient — the MRT gets you almost anywhere and contactless payment works everywhere. Just respect the strict laws on littering, eating on transport and (especially) drugs.",
    "Japan": "Japan is safe, punctual and spotless, but still surprisingly cash-based and big on etiquette. Carry cash, get an IC card, keep quiet on trains, and don't tip.",
    "Malaysia": "Malaysia is diverse, easy and affordable, with brilliant hawker food and good transport links. Use Grab to get around, carry ringgit cash for stalls and markets, and dress modestly out of respect for local Muslim customs.",
    "Indonesia": "Indonesia spans thousands of islands, from Bali's temples to Jakarta's sprawl, and runs largely on cash. Use Gojek or Grab for rides, drink only bottled water, and respect temple dress codes and the daily offerings on the streets.",
    "Philippines": "The Philippines is friendly and English-speaking, with stunning islands reached by budget flights and ferries. Carry peso cash once you leave the cities, build slack into island-hopping for weather, and check advisories for parts of Mindanao.",
    "Cambodia": "Cambodia is warm, affordable and home to the magnificent Angkor temples. The US dollar is everyday currency (bring clean small notes), tuk-tuks and ride apps get you around, and you should stick to marked paths in rural areas due to landmine risk.",
    "Laos": "Laos is laid-back, mountainous and refreshingly unhurried, with the new fast train making travel between Vientiane, Vang Vieng and Luang Prabang easy. It is very cash-based, ATMs are limited, and you should never stray off marked paths because of unexploded ordnance.",
    "Myanmar": "Myanmar holds extraordinary temples and culture but is affected by ongoing conflict and instability — check travel advisories carefully before going. International cards rarely work, so bring enough pristine US dollars for your whole trip and expect internet restrictions.",
    "Brunei": "Brunei is small, wealthy, very safe and quietly conservative, with grand mosques and pristine rainforest. There is little public transport so hiring a car is easiest, alcohol sales are banned, and modest dress and conservative behaviour are expected.",
    "Timor-Leste": "Timor-Leste is one of Asia's least-visited countries, with empty beaches and superb diving but very basic infrastructure. It uses the US dollar with few reliable ATMs, roads outside Dili are rough, so travel self-sufficiently and with good insurance.",
    "Hong Kong": "Hong Kong is fast, safe and effortless to get around — an Octopus card covers the MTR, buses, trams and ferries. Cards are accepted almost everywhere, the food scene from dim sum to street stalls is superb, and autumn is the most pleasant time to visit.",
    "South Korea": "South Korea is ultra-modern, exceptionally safe and a joy to navigate, with a cheap, English-signed transit network and lightning-fast internet. Get a T-money card, use Naver or Kakao Maps instead of Google, and visit in spring or autumn for the best weather.",
}

# Reject keys absent from countries.py; both dicts must cover the same countries.
_VALID_COUNTRIES: set[str] = {c["name"] for c in _COUNTRIES}
_unknown = (set(COUNTRY_TIPS) | set(COUNTRY_SUMMARIES)) - _VALID_COUNTRIES
if _unknown:
    raise ValueError(
        f"tips.py references unknown countries: {sorted(_unknown)} "
        "— add them to app/data/countries.py"
    )
if set(COUNTRY_TIPS) != set(COUNTRY_SUMMARIES):
    raise ValueError(
        "tips.py: COUNTRY_TIPS and COUNTRY_SUMMARIES must cover the same countries"
    )
